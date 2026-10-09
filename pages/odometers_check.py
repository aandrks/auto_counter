"""
Odometers Check Page - Streamlit UI for checking missing odometer data.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar

from utils.constants import DEFAULT_CARS_LIST, SMALL_CARS_LIST
from utils.gsheets import get_odometer_dataframe, clear_odometer_cache
from utils.odometer_logic import (
    parse_date_input,
    get_odometer_dicts,
    find_missing_cars,
    format_missing_cars_output,
    get_missing_cars_simple
)


# Month names in Russian
MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def load_car_phones() -> dict:
    """Load car phone numbers from secrets."""
    try:
        return dict(st.secrets["car_phones"])
    except KeyError:
        st.warning("Car phone numbers not configured in secrets. Using empty dict.")
        return {}


def main():
    st.title("📊 Odometers Check")
    st.markdown("Check which vehicles are missing odometer data for a given month.")

    # Calculate default: last month
    today = datetime.now()
    if today.month == 1:
        default_month = 12
        default_year = today.year - 1
    else:
        default_month = today.month - 1
        default_year = today.year

    # Sidebar inputs
    with st.sidebar:
        st.header("⚙️ Parameters")

        # Month selector with names
        month_options = {name: i+1 for i, name in enumerate(MONTH_NAMES)}
        selected_month_name = st.selectbox(
            "Month",
            options=MONTH_NAMES,
            index=default_month - 1
        )
        month = month_options[selected_month_name]

        # Year selector
        year = st.selectbox(
            "Year",
            range(2020, 2030),
            index=default_year - 2020
        )

        st.divider()

        # Cars list management: two lists
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
                help="Full list of cars to check."
            )
            small_list_str = st.text_area(
                "Малый список (one per line)",
                value="\n".join(SMALL_CARS_LIST),
                height=110,
                help="Short list of cars to check."
            )

        full_list = [c.strip() for c in full_list_str.split("\n") if c.strip()]
        small_list = [c.strip() for c in small_list_str.split("\n") if c.strip()]
        cars_list = full_list if list_choice == "Полный список" else small_list

        # Refresh button
        if st.button("🔄 Refresh Data", use_container_width=True):
            clear_odometer_cache()
            st.rerun()

    # Main content
    try:
        dt_date = parse_date_input(month, year)
        st.info(f"📅 Checking data for **{dt_date.strftime('%B %Y')}** (last day: {dt_date.strftime('%d.%m.%Y')})")

        # Fetch data
        with st.spinner("Loading odometer data from Google Sheets..."):
            df_od = get_odometer_dataframe()

        if df_od.empty:
            st.error("No data retrieved from Google Sheets. Check connection and spreadsheet.")
            return

        st.success(f"Loaded {len(df_od)} records from Google Sheets")

        # Process odometer data
        odo_now, odo_prev = get_odometer_dicts(df_od, dt_date)

        # Find missing cars
        missing_current, missing_previous = find_missing_cars(cars_list, odo_now, odo_prev)

        # Load phone numbers
        car_phones = load_car_phones()

        # Show phone warnings grouped
        missing_all = missing_current + missing_previous
        missing_phones = []
        for car in missing_all:
            if not car_phones.get(car):
                missing_phones.append(car)
        if missing_phones:
            st.warning(f"⚠️ Телефон для автомобилей {', '.join(missing_phones)} не найден в secrets")

        # Small metrics text
        st.caption(f"Cars with data: {len(odo_now)}  |  Cars missing data: {len(missing_current)}")

        # Missing car numbers (read-only, for copy)
        if missing_current:
            missing_cars_str = ", ".join(missing_current)
            st.text_area("Missing cars:", missing_cars_str, height=68, disabled=True)

        # Copy phone numbers for missing cars (st.code has built-in copy button)
        if missing_current:
            phones_output = format_missing_cars_output(missing_current, car_phones)
            if phones_output and phones_output != "Все автомобили имеют данные ✅" and phones_output != "Телефонов для указанных автомобилей не найдено":
                st.code(phones_output, language=None)

        # Build full table: [Car, Odometer, Phone] for ALL cars
        table_rows = []
        for car in cars_list:
            display_name = car  # Just car number for this table
            odometer = odo_now.get(car)
            phone = car_phones.get(car, "")
            table_rows.append({
                "Car": display_name,
                "Odometer": odometer if odometer is not None else "",
                "Phone": phone
            })

        df_table = pd.DataFrame(table_rows)
        
        # Display table with custom column widths
        st.dataframe(
            df_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Car": st.column_config.TextColumn("Car", width="small"),
                "Odometer": st.column_config.NumberColumn("Odometer", format="%d", width="medium"),
                "Phone": st.column_config.TextColumn("Phone", width="large"),
            }
        )

        with st.expander("🔍 View Full Google Sheets Data", expanded=False):
            st.dataframe(df_od, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.exception(e)


if __name__ == "__main__":
    main()