"""
Cards Admin Page - Cards DB display and editing (auth required).
Access via st.navigation (3rd page). Login with password (streamlit-authenticator).
Features:
  - Display of the whole cards table from Supabase
  - Add a card for a car by its car number (three digits) + fuel type
  - Inline editing, deletion, and search filter
Table format: [Card, Car_n (matching), Car_s (display), Type] where Type is 0 (92/95) or 1 (ДТ).
"""
import re
from collections.abc import Mapping

import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth

from utils.db import (
    fetch_all_cards, insert_card, update_card, delete_card,
    seed_from_local_json, clear_cards_cache
)
from utils.cards_transform import extract_car_number, ALLOWED_F_TYPE

DEL_COL = "_Удалить"

F_TYPE_LABELS = {0: "0 · 92/95", 1: "1 · ДТ"}


def f_type_fmt(t: int) -> str:
    return f"{t} · {'92/95' if t == 0 else 'ДТ'}"


def _to_plain(obj):
    """Recursively convert st.secrets (Mapping-based Secrets objects) into plain
    dicts/lists. streamlit-authenticator mutates the credentials dict, and
    st.secrets objects do not support item assignment - hence deep plain
    conversion is required (Secrets is a Mapping, not a dict subclass)."""
    if isinstance(obj, Mapping):
        return {str(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    return obj


def get_authenticator():
    """Create authenticator from secrets config."""
    try:
        credentials = _to_plain(st.secrets["credentials"])
        cookie = _to_plain(st.secrets["cookie"])
    except (KeyError, TypeError):
        return None, None

    if "usernames" not in credentials:
        st.error("В [credentials] отсутствует секция usernames. Проверьте .streamlit/secrets.toml")
        return None

    authenticator = stauth.Authenticate(
        credentials,
        cookie.get("name", "cards_admin_cookie"),
        cookie.get("key", "some_signature_key"),
        cookie.get("expiry_days", 30),
    )
    return authenticator, cookie


def _render_unknowns_section(existing_rows: list):
    """Fill-in table for cards/cars missing in the reference.

    Data comes from the last fuel calculation (pages/fuel_counting.py stores it in
    st.session_state['fuel_unknowns']). Filled rows are inserted into the DB.
    """
    data = st.session_state.get("fuel_unknowns")
    if not data:
        st.info(
            "ℹ️ Нет данных о неизвестных. Загрузите файлы топлива на странице "
            "**Fuel Counting** — список карт/авто для заполнения появится здесь."
        )
        return

    fillin = data.get("fillin")
    reference = data.get("reference")
    period = data.get("period", "")

    st.markdown("### 🧩 Неизвестные из расчёта топлива")
    st.caption(
        (f"Период: {period}. " if period else "")
        + "Заполните нужные поля и нажмите «Сохранить в DB». Сохраняются только строки, "
          "где указаны и номер карты, и номер авто."
    )

    if fillin is None or not len(fillin):
        st.success("✅ Все карты и авто распознаны — заполнять нечего.")
    else:
        edit_src = fillin.copy()
        edit_src["f_type"] = edit_src["f_type"].astype(int).map(F_TYPE_LABELS)
        edited = st.data_editor(
            edit_src,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=["Категория", "Литры"],
            column_config={
                "Категория": st.column_config.TextColumn("Причина", width="medium"),
                "card": st.column_config.TextColumn("Номер карты", width="medium"),
                "car_n": st.column_config.TextColumn("Номер авто (3 цифры)", width="small"),
                "f_type": st.column_config.SelectboxColumn(
                    "Тип топлива", options=list(F_TYPE_LABELS.values()), width="small"
                ),
                "car_s": st.column_config.TextColumn(
                    "Название авто (необязательно)", width="large"
                ),
                "Литры": st.column_config.NumberColumn("Литры", format="%.2f"),
            },
            key="unknowns_editor",
        )
        if st.button("💾 Сохранить в DB", type="primary", key="save_unknowns"):
            _save_unknowns(edited, existing_rows)

    if reference is not None and len(reference):
        with st.expander(
            f"📋 Справочно: без расхода / без топлива ({len(reference)})", expanded=False
        ):
            st.caption("Данные уже есть в БД — это диагностика (мэппинг/одометрия).")
            st.dataframe(
                reference,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "f_type": st.column_config.NumberColumn("f_type", width="small"),
                    "Литры": st.column_config.NumberColumn("Литры", format="%.2f"),
                },
            )


def _save_unknowns(edited, existing_rows: list):
    """Insert filled unknowns into the DB (skip incomplete/duplicate rows)."""
    existing = {(str(r["card"]), int(r["f_type"])) for r in existing_rows}
    inserted = already = skipped = 0
    for rec in edited.to_dict(orient="records"):
        card = str(rec.get("card") or "").strip()
        car_n = str(rec.get("car_n") or "").strip()
        label = str(rec.get("f_type") or "").strip()
        f_type = 0 if label.startswith("0") else (1 if label.startswith("1") else None)
        car_s = str(rec.get("car_s") or "").strip()

        if not card or not car_n or f_type is None or not re.fullmatch(r"\d{1,4}", car_n):
            skipped += 1
            continue
        if (card, f_type) in existing:
            already += 1
            continue
        try:
            insert_card(card, car_n, car_s or car_n, f_type)
            inserted += 1
        except Exception as e:
            st.error(f"Ошибка сохранения карты {card}: {e}")

    msg = f"Сохранено в DB: добавлено {inserted}"
    if already:
        msg += f", уже было: {already}"
    if skipped:
        msg += f", пропущено (не заполнено): {skipped}"
    st.success(msg)
    clear_cards_cache()
    st.rerun()


def main():
    st.title("💳 Cards DB")
    st.markdown("База данных карт → автомобиль (Supabase). Редактирование и добавление доступно после входа.")

    # --- Supabase config check ---
    supabase_ready = True
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except (KeyError, TypeError):
        supabase_ready = False
        st.error(
            "Supabase не настроен. Добавьте [supabase] (url, key) в .streamlit/secrets.toml "
            "и выполните SQL из db_schema.sql в Supabase SQL Editor."
        )

    # --- Authentication gate (password required for this page) ---
    # Note: in streamlit-authenticator 0.4.2 login(location='main') renders the
    # form and returns None; the widget writes the result into session_state.
    authenticator, cookie = get_authenticator()
    if authenticator is None:
        st.error(
            "Авторизация не настроена. Добавьте [credentials] и [cookie] в .streamlit/secrets.toml"
        )
        return

    authenticator.login(location="main")

    auth_status = st.session_state.get("authentication_status")

    if auth_status is False:
        st.error("Неверное имя пользователя или пароль")
        return
    if auth_status is None:
        st.info("🔒 Введите имя пользователя и пароль для доступа к базе данных карт")
        return

    # --- Logged in ---
    name = st.session_state.get("name", "")
    username = st.session_state.get("username", "")
    st.sidebar.markdown(f"👤 **{name}** (@{username})")
    authenticator.logout("Logout", location="main")

    if not supabase_ready:
        return

    # --- Load current rows ---
    try:
        rows = fetch_all_cards()
    except Exception as e:
        st.error(f"Ошибка загрузки данных из Supabase: {e}")
        return

    if not rows:
        st.warning("Таблица cards пуста. Используйте форму добавления ниже или кнопку миграции.")
        rows = []

    # --- Add / update card form: by car number (three digits) + fuel type ---
    with st.expander("➕ Добавить карту для авто (по номеру авто)", expanded=False):
        with st.form("add_card_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
            new_card = c1.text_input("Номер карты", placeholder="7005830003442001")
            new_car_n = c2.text_input("Номер авто (3 цифры)", placeholder="977", max_chars=4)
            new_f_type = c3.selectbox(
                "Тип топлива",
                options=[0, 1],
                format_func=f_type_fmt,
            )
            new_car_s = c4.text_input(
                "Название авто для таблицы (необязательно)",
                placeholder="Sollers Argo (977)",
            )
            submitted = st.form_submit_button("➕ Добавить карту", type="primary")

    if submitted:
        card = new_card.strip()
        car_n = new_car_n.strip()
        if not card or not car_n:
            st.warning("Заполните номер карты и номер авто.")
        elif not re.fullmatch(r"\d{1,4}", car_n):
            st.warning("Номер авто должен состоять из цифр (обычно 3, например 977).")
        else:
            car_s = new_car_s.strip() or car_n
            # Always insert a NEW row (no update of existing card rows).
            duplicate = any(
                str(r["card"]) == card and int(r["f_type"]) == new_f_type for r in rows
            )
            try:
                created = insert_card(card, car_n, car_s, new_f_type)
                created = created[0] if isinstance(created, list) and created else created
                if created:
                    rows.append(created)
                st.success(f"Добавлена карта **{card}** → **{car_s}** "
                           f"({f_type_fmt(new_f_type)})")
                if duplicate:
                    st.info("Запись для этой карты и типа уже существовала — добавлена новая; "
                            "в расчётах учитывается последняя.")
                clear_cards_cache()
            except Exception as e:
                st.error(f"Ошибка сохранения: {e}")

    # --- Unknowns from the last fuel calculation (fill-in → save to DB) ---
    _render_unknowns_section(rows)

    # --- Search filter ---
    search = st.text_input(
        "🔍 Фильтр: номер карты / номер авто / название",
        placeholder="напр. 977 или FORD",
    )

    # --- Build dataframe for display/editing ---
    df = pd.DataFrame(rows, columns=["id", "card", "car_n", "car_s", "f_type"])
    if search:
        mask = (
            df["card"].astype(str).str.contains(search, case=False, na=False)
            | df["car_n"].astype(str).str.contains(search, case=False, na=False)
            | df["car_s"].astype(str).str.contains(search, case=False, na=False)
        )
        df = df[mask]
    df["f_type"] = df["f_type"].astype(int).map(F_TYPE_LABELS)  # friendly labels 0|1
    df.insert(0, DEL_COL, False)  # UI-only delete marker

    st.markdown("### Справочник карт")
    st.caption(
        f"Всего записей: **{len(rows)}**"
        + (f" · показано: **{len(df)}**" if search else "")
        + ". Изменяйте значения прямо в таблице, новые строки добавляются внизу, "
          "для удаления отметьте галочку слева. В конце нажмите «Сохранить изменения»."
    )

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            DEL_COL: st.column_config.CheckboxColumn(DEL_COL, width="small"),
            "id": st.column_config.NumberColumn(disabled=True),
            "card": st.column_config.TextColumn("Card", width="medium"),
            "car_n": st.column_config.TextColumn("Car_n", width="small"),
            "car_s": st.column_config.TextColumn("Car_s", width="large"),
            "f_type": st.column_config.SelectboxColumn(
                "Type", options=["0 · 92/95", "1 · ДТ"], width="small"
            ),
        },
        key="cards_editor",
    )

    col_save, col_seed = st.columns([1, 2])
    with col_save:
        save_clicked = st.button("💾 Сохранить изменения", type="primary", use_container_width=True)
    with col_seed:
        seed_clicked = st.button(
            "🌱 Миграция из car_cards.json (заменит все данные)", use_container_width=True
        )

    # --- Save edited data ---
    if save_clicked:
        original = {int(r["id"]): r for r in rows}
        stats = {"inserted": 0, "updated": 0, "deleted": 0, "skipped": 0}
        errors = []

        for record in edited.to_dict(orient="records"):
            rid = record.get("id")
            rid = None if pd.isna(rid) else int(rid)
            card = str(record.get("card") or "").strip()
            car_s = str(record.get("car_s") or "").strip()
            f_label = str(record.get("f_type") or "").strip()
            f_type = 0 if f_label.startswith("0") else (1 if f_label.startswith("1") else None)
            mark_del = bool(record.get(DEL_COL, False))

            # Validation
            if not card or f_type is None:
                stats["skipped"] += 1
                continue
            if car_s:
                # Keep car_n in sync: if empty or differs from current, re-derive from car_s
                car_n = str(record.get("car_n") or "").strip() or extract_car_number(car_s)
            else:
                car_n = str(record.get("car_n") or "").strip()
            if not car_s and not car_n:
                stats["skipped"] += 1
                continue

            # Delete marked rows
            if mark_del:
                if rid is not None and rid in original:
                    delete_card(rid)
                    stats["deleted"] += 1
                continue

            if rid is None:
                # New row
                insert_card(card, car_n, car_s, f_type)
                stats["inserted"] += 1
            elif rid in original and (
                original[rid]["card"] != card
                or original[rid]["car_n"] != car_n
                or original[rid]["car_s"] != car_s
                or original[rid]["f_type"] != f_type
            ):
                update_card(rid, card, car_n, car_s, f_type)
                stats["updated"] += 1

        msg = (
            f"Готово: добавлено {stats['inserted']}, обновлено {stats['updated']}, "
            f"удалено {stats['deleted']}"
            + (f", пропущено {stats['skipped']}" if stats["skipped"] else "")
        )
        if errors:
            for err in errors:
                st.warning(err)
        st.toast(msg, icon="💾")
        st.success(msg)
        clear_cards_cache()
        st.rerun()

    # --- One-time seed from local JSON ---
    if seed_clicked:
        try:
            count = seed_from_local_json("car_cards.json")
            st.success(f"Загружено {count} записей из car_cards.json")
            clear_cards_cache()
            st.rerun()
        except FileNotFoundError:
            st.error("Файл car_cards.json не найден в корне проекта")
        except Exception as e:
            st.error(f"Ошибка миграции: {e}")


if __name__ == "__main__":
    main()