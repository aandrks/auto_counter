"""
Fuel Counting Page - Streamlit UI for parsing fuel data and calculating consumption.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import hashlib
from io import BytesIO

from utils.constants import (
    DEFAULT_CARS_LIST, DEFAULT_NORM_DICT, SMALL_CARS_LIST,
    FUEL_REPORT_COLUMNS, MONTH_NAMES, FUEL_MONTH_LABEL_FORMAT,
)
from utils.gsheets import get_odometer_dataframe, clear_odometer_cache
from utils.odometer_logic import (
    parse_date_input,
    get_odometer_dicts,
    calculate_odometer_diff
)
from utils.fuel_logic import (
    extract_date_from_fuel_data,
    parse_fuel_excel,
    build_result_dataframe,
    build_car_name_mapping,
    build_parse_log,
    build_unknowns,
    SUMMARY_SKIP_STATUS,
    CAT_CAR_NO_CARD,
    CAT_CARD_NOT_FOUND,
    CAT_EMPTY_SLOT,
)
from utils.db import fetch_cards_mapping, fetch_car_name_map


def _hash_uploaded_files(files) -> str:
    """Stable signature (name + content) of uploaded files.

    Used to avoid re-reading the same files on every rerun and to detect when
    a genuinely new upload replaces the cached one in session_state.
    """
    h = hashlib.md5()
    for f in files:
        h.update(str(f.name).encode("utf-8"))
        h.update(f.getvalue())
    return h.hexdigest()


def _month_label(dt_date: datetime, months_back: int = 0) -> str:
    """Real month label for the odometer columns (0 = current, 1 = previous)."""
    year, month = dt_date.year, dt_date.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return FUEL_MONTH_LABEL_FORMAT.format(
        month=MONTH_NAMES[month - 1], year=year, num=f"{month:02d}.{year}"
    )


def _excel_with_widths(df: pd.DataFrame, width_by_label: dict) -> bytes:
    """Serialize a DataFrame to xlsx bytes, applying per-column widths (chars)."""
    from openpyxl.utils import get_column_letter

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
        ws = writer.sheets.get("Sheet1") or next(iter(writer.sheets.values()))
        for i, col_name in enumerate(df.columns, start=1):
            width = width_by_label.get(col_name)
            if width:
                ws.column_dimensions[get_column_letter(i)].width = width
    buf.seek(0)
    return buf.getvalue()


def main():
    st.title("⛽ Fuel Counting")
    st.markdown("Upload fuel Excel files to calculate consumption per vehicle.")

    # Sidebar inputs
    with st.sidebar:
        st.header("⚙️ Parameters")

        # Cars list: two lists
        list_choice = st.radio(
            "Car list",
            options=["Полный список", "Малый список"],
            horizontal=True
        )
        with st.expander("🚗 Car Lists", expanded=False):
            if list_choice == "Полный список":
                active_label = "Active: Полный список"
            else:
                active_label = "Active: Малый список"
            st.markdown(active_label)

            full_list_str = st.text_area(
                "Полный список (one per line)",
                value="\n".join(DEFAULT_CARS_LIST),
                height=200,
                help="Full list of cars."
            )
            small_list_str = st.text_area(
                "Малый список (one per line)",
                value="\n".join(SMALL_CARS_LIST),
                height=110,
                help="Short list of cars."
            )

        full_list = [c.strip() for c in full_list_str.split("\n") if c.strip()]
        small_list = [c.strip() for c in small_list_str.split("\n") if c.strip()]
        cars_list = full_list if list_choice == "Полный список" else small_list

        # Norms
        with st.expander("📏 Consumption Norms", expanded=False):
            norms_str = st.text_area(
                "Norms (JSON: car -> norm)",
                value=json.dumps(DEFAULT_NORM_DICT, ensure_ascii=False, indent=2),
                height=150
            )
            try:
                norm_dict = json.loads(norms_str)
            except json.JSONDecodeError:
                st.error("Invalid JSON for norms")
                norm_dict = DEFAULT_NORM_DICT

        st.divider()
        if st.button("🔄 Refresh Odometer Data", use_container_width=True):
            clear_odometer_cache()
            st.rerun()

        if st.button("🗑 Сбросить загруженные файлы", use_container_width=True):
            for _k in ("fuel_df_combined", "fuel_files_sig", "fuel_files_names"):
                st.session_state.pop(_k, None)
            st.rerun()

    # Main content - file upload (single uploader for both files)
    st.subheader("📁 Upload Fuel Data Files")
    st.markdown("Upload **two Excel files** with fuel data (hold Ctrl/Cmd to select both).")

    files = st.file_uploader(
        "Fuel Excel files",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key="fuel_files"
    )

    # Keep uploaded data in session_state: st.file_uploader drops its files when
    # its page is left (e.g. switching to Cards DB and back), but session_state
    # survives page switches within the same browser session.
    new_files = bool(files) and len(files) >= 2
    have_saved = "fuel_df_combined" in st.session_state
    if not new_files and not have_saved:
        st.info(f"👆 Uploaded {len(files) if files else 0} of 2 files. Please upload both Excel files to proceed.")
        return

    # Process files
    try:
        if new_files:
            for _f in files:
                _f.seek(0)
            files_sig = _hash_uploaded_files(files)
            if st.session_state.get("fuel_files_sig") != files_sig:
                with st.spinner("Reading Excel files..."):
                    dfs = [pd.read_excel(f) for f in files]
                    df_combined = pd.concat(dfs, ignore_index=True)
                st.session_state["fuel_df_combined"] = df_combined
                st.session_state["fuel_files_sig"] = files_sig
                st.session_state["fuel_files_names"] = [f.name for f in files]
            else:
                df_combined = st.session_state["fuel_df_combined"]
            st.success(f"Loaded {len(files)} files, {len(df_combined)} rows total")
        else:
            # No files in the uploader (page was re-entered) - reuse saved data.
            df_combined = st.session_state["fuel_df_combined"]
            names = ", ".join(st.session_state.get("fuel_files_names", []))
            st.info(
                "♻️ Показаны результаты по ранее загруженным файлам"
                + (f": {names}" if names else "")
                + ". Загрузите новые файлы, чтобы пересчитать."
            )

        # Extract date from fuel data
        dt_date = extract_date_from_fuel_data(df_combined)
        st.info(f"📅 Detected period: **{dt_date.strftime('%B %Y')}** ({dt_date.strftime('%d.%m.%Y')})")

        # Load cards mapping - try Supabase first, fallback to secrets
        try:
            cards_mapping = fetch_cards_mapping()  # {card: [car_n_92/95, car_n_ДТ]} for matching
            car_name_map = fetch_car_name_map()    # {car_n: car_s} for display
            st.info(f"Loaded {len(cards_mapping)} card mappings from Supabase")
        except Exception as e:
            st.warning(f"⚠️ Supabase недоступна ({e}), использую маппинг из secrets")
            try:
                cards_mapping = dict(st.secrets["cards_mapping"])
                car_name_map = build_car_name_mapping(cards_mapping)
                st.info(f"Loaded {len(cards_mapping)} card mappings from secrets")
            except KeyError:
                st.error("Cards mapping not found in secrets")
                return

        # Fetch odometer data from Google Sheets
        with st.spinner("Loading odometer data from Google Sheets..."):
            df_od = get_odometer_dataframe()

        if df_od.empty:
            st.error("No odometer data from Google Sheets")
            return

        # Process odometer data
        odo_now, odo_prev = get_odometer_dicts(df_od, dt_date)
        od_diff = calculate_odometer_diff(odo_now, odo_prev)

        # Parse fuel data
        with st.spinner("Parsing fuel data..."):
            dict_fuel, dict_diesel = parse_fuel_excel(df_combined, cards_mapping)

        # Build result with car name mapping
        result_df = build_result_dataframe(
            dict_fuel, dict_diesel,
            odo_now, odo_prev, od_diff,
            cars_list=cars_list,
            norm_dict=norm_dict,
            car_name_map=car_name_map
        )

        # Display results - main table with all columns.
        # Names/formats/widths come from FUEL_REPORT_COLUMNS (utils/constants.py).
        month_labels = {
            "month_now": _month_label(dt_date, 0),
            "month_prev": _month_label(dt_date, 1),
        }
        display_cols = [c["key"] for c in FUEL_REPORT_COLUMNS]
        col_labels = {
            c["key"]: c["label"].format(**month_labels) for c in FUEL_REPORT_COLUMNS
        }
        column_config = {}
        for c in FUEL_REPORT_COLUMNS:
            if c["format"]:
                column_config[c["key"]] = st.column_config.NumberColumn(
                    col_labels[c["key"]], format=c["format"]
                )
            else:
                column_config[c["key"]] = st.column_config.TextColumn(
                    col_labels[c["key"]], width="medium"
                )

        st.dataframe(
            result_df[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config=column_config,
        )

        # Downloads use the same display labels as headers
        report_df = result_df[display_cols].rename(columns=col_labels)
        width_by_label = {col_labels[c["key"]]: c.get("width") for c in FUEL_REPORT_COLUMNS}

        # Download buttons
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            csv = report_df.to_csv(index=False).encode('utf-8')
            filename = f"fuel_report_{dt_date.strftime('%m_%Y')}.csv"
            st.download_button(
                "📥 Download CSV",
                csv,
                filename,
                "text/csv",
                use_container_width=True
            )
        with col_dl2:
            excel_bytes = _excel_with_widths(report_df, width_by_label)
            st.download_button(
                "📥 Download Excel",
                excel_bytes,
                f"fuel_report_{dt_date.strftime('%m_%Y')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        # Parsing log (diagnostics)
        parse_log = build_parse_log(
            df_combined,
            cards_mapping,
            car_name_map=car_name_map,
            period=dt_date.strftime("%d.%m.%Y"),
        )
        log_skipped = int((parse_log["Статус"] == SUMMARY_SKIP_STATUS).sum())
        log_problems = int(
            ((parse_log["Статус"] != "OK") & (parse_log["Статус"] != SUMMARY_SKIP_STATUS)).sum()
        )

        with st.expander("🧾 Лог парсинга топлива (диагностика)", expanded=False):
            st.caption(
                f"Строк «Итого по»: **{len(parse_log)}**"
                + (f" · пропущено итоговых: **{log_skipped}**" if log_skipped else "")
                + (f" · с проблемами: **{log_problems}**" if log_problems else "")
                + ". Здесь видно, какая карта и сколько литров к какому авто приписаны."
            )
            st.dataframe(parse_log, use_container_width=True, hide_index=True)

            log_buffer = BytesIO()
            parse_log.to_excel(log_buffer, index=False)
            log_buffer.seek(0)

            col_log1, col_log2 = st.columns(2)
            with col_log1:
                st.download_button(
                    "📥 Скачать лог (xlsx)",
                    log_buffer,
                    f"fuel_parse_log_{dt_date.strftime('%m_%Y')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            with col_log2:
                if st.button("💾 Сохранить лог в logs/", use_container_width=True):
                    logs_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
                    )
                    os.makedirs(logs_dir, exist_ok=True)
                    path = os.path.join(
                        logs_dir,
                        f"fuel_parse_log_{dt_date.strftime('%Y_%m_%d_%H%M%S')}.xlsx",
                    )
                    parse_log.to_excel(path, index=False)
                    st.success(f"Лог сохранён в файл: `{path}`")

        # Unknowns for the Cards DB fill-in table (cards/cars missing in the
        # reference). Stored in session_state so the Cards DB page shows the same
        # list within this browser session.
        fuel_liters = {}
        for _d in (dict_fuel, dict_diesel):
            for _car, _v in _d.items():
                fuel_liters[_car] = fuel_liters.get(_car, 0.0) + _v["liters"]

        fillin_df, reference_df = build_unknowns(
            parse_log, result_df, cards_mapping, car_name_map, fuel_liters,
            candidate_cars=set(result_df["Car_number"]) | set(odo_now) | set(odo_prev),
        )
        st.session_state["fuel_unknowns"] = {
            "fillin": fillin_df,
            "reference": reference_df,
            "period": dt_date.strftime("%d.%m.%Y"),
        }

        # Single consolidated warning: cars without a card first, then cards
        # without a car. Filling happens on the Cards DB page.
        if len(fillin_df) or len(reference_df):
            no_card = fillin_df[fillin_df["Категория"] == CAT_CAR_NO_CARD]
            no_car = fillin_df[
                fillin_df["Категория"].isin([CAT_CARD_NOT_FOUND, CAT_EMPTY_SLOT])
            ]
            lines = ["⚠️ **Требуют заполнения в справочнике** (вкладка Cards DB):"]
            if len(no_card):
                lines.append(
                    "- **Авто без карты:** "
                    + ", ".join(str(c) for c in no_card["car_n"])
                )
            if len(no_car):
                items = []
                for _, _r in no_car.iterrows():
                    _t = "ДТ" if int(_r["f_type"]) == 1 else "92/95"
                    _lit = f", {_r['Литры']:.2f} л" if pd.notna(_r["Литры"]) else ""
                    items.append(f"{_r['card']} ({_t}{_lit})")
                lines.append("- **Карты без авто:** " + "; ".join(items))
            if len(reference_df):
                lines.append(
                    f"- Справочно: {len(reference_df)} записей без расхода/без топлива "
                    "— там же, во вкладке Cards DB."
                )
            st.warning("\n".join(lines))

    except Exception as e:
        st.error(f"Error processing files: {str(e)}")
        st.exception(e)


if __name__ == "__main__":
    main()