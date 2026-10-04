"""
Fuel Counting Page - Streamlit UI for parsing fuel data and calculating consumption.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import json

from utils.constants import DEFAULT_CARS_LIST, DEFAULT_NORM_DICT
from utils.gsheets import get_odometer_dataframe, clear_odometer_cache
from utils.odometer_logic import (
    parse_date_input,
    get_odometer_dicts,
    calculate_odometer_diff
)
from utils.fuel_logic import (
    extract_date_from_fuel_data,
    load_cards_mapping,
    parse_fuel_excel,
    build_result_dataframe,
    build_car_name_mapping
)


def main():
    st.title("⛽ Fuel Counting")
    st.markdown("Upload fuel Excel files to calculate consumption per vehicle.")

    # Sidebar inputs
    with st.sidebar:
        st.header("⚙️ Parameters")

        # Cars list
        with st.expander("🚗 Car List", expanded=False):
            cars_list_str = st.text_area(
                "Car numbers (one per line)",
                value="\n".join(DEFAULT_CARS_LIST),
                height=150
            )
            cars_list = [c.strip() for c in cars_list_str.split("\n") if c.strip()]

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

    # Main content - file upload
    st.subheader("📁 Upload Fuel Data Files")
    st.markdown("Upload **two Excel files** with fuel data (as in original workflow).")

    col1, col2 = st.columns(2)
    with col1:
        file1 = st.file_uploader("First Excel file", type=["xlsx", "xls"], key="fuel_file1")
    with col2:
        file2 = st.file_uploader("Second Excel file", type=["xlsx", "xls"], key="fuel_file2")

    if not file1 or not file2:
        st.info("👆 Please upload both Excel files to proceed.")
        return

    # Process files
    try:
        with st.spinner("Reading Excel files..."):
            df1 = pd.read_excel(file1)
            df2 = pd.read_excel(file2)
            df_combined = pd.concat([df1, df2], ignore_index=True)

        st.success(f"Loaded {len(df1)} + {len(df2)} = {len(df_combined)} rows")

        # Extract date from fuel data
        dt_date = extract_date_from_fuel_data(df_combined)
        st.info(f"📅 Detected period: **{dt_date.strftime('%B %Y')}** ({dt_date.strftime('%d.%m.%Y')})")

        # Load cards mapping from secrets
        try:
            cards_mapping = dict(st.secrets["cards_mapping"])
            st.info(f"Loaded {len(cards_mapping)} card mappings from secrets")
        except KeyError:
            st.error("Cards mapping not found in secrets")
            return

        # Build car name mapping for display
        car_name_map = build_car_name_mapping(cards_mapping)

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

        # Display results - main table with all columns
        display_cols = ["Car", "Result", "Fuel", "Odometer", "Month2", "Month1"]
        st.dataframe(
            result_df[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Car": st.column_config.TextColumn("Car", width="medium"),
                "Result": st.column_config.NumberColumn("Result", format="%.2f"),
                "Fuel": st.column_config.NumberColumn("Fuel", format="%.1f"),
                "Odometer": st.column_config.NumberColumn("Odometer", format="%d"),
                "Month2": st.column_config.NumberColumn("Month2", format="%d"),
                "Month1": st.column_config.NumberColumn("Month1", format="%d"),
            }
        )

        # Download buttons
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            csv = result_df[display_cols].to_csv(index=False).encode('utf-8')
            filename = f"fuel_report_{dt_date.strftime('%m_%Y')}.csv"
            st.download_button(
                "📥 Download CSV",
                csv,
                filename,
                "text/csv",
                use_container_width=True
            )
        with col_dl2:
            from io import BytesIO
            excel_buffer = BytesIO()
            result_df[display_cols].to_excel(excel_buffer, index=False)
            excel_buffer.seek(0)
            st.download_button(
                "📥 Download Excel",
                excel_buffer,
                f"fuel_report_{dt_date.strftime('%m_%Y')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    except Exception as e:
        st.error(f"Error processing files: {str(e)}")
        st.exception(e)


if __name__ == "__main__":
    main()