"""
Core odometer calculation logic - shared between both modules.
Extracted from original scripts without modification to algorithms.
"""
import pandas as pd
from datetime import datetime, timedelta
import calendar
from utils.constants import DEFAULT_CARS_LIST


def parse_date_input(month: int, year: int) -> datetime:
    """Parse month/year input to get last day of month as datetime."""
    last_day = calendar.monthrange(year, month)[1]
    return datetime.strptime(f"{last_day}.{month}.{year}", "%d.%m.%Y")


def get_date_ranges(dt_date: datetime) -> tuple:
    """
    Calculate the two date ranges for odometer comparison.
    Returns: (d1, d2, d3, d4) where:
    - d1 to d2: current period (dt_date - 10 days to dt_date + 15 days in original, +18 in fuel)
    - d3 to d4: previous period (dt_date - 40 days to dt_date - 14 days)
    """
    d1 = dt_date - timedelta(days=10)
    d2 = dt_date + timedelta(days=18)  # Using fuel_counting's +18
    d3 = dt_date - timedelta(days=40)
    d4 = dt_date - timedelta(days=14)
    return d1, d2, d3, d4


def parse_odometer_time(time_str: str) -> datetime | None:
    """Parse time string from Google Sheets to datetime."""
    try:
        # Try multiple formats
        for fmt in ["%d/%m/%Y %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
            try:
                return pd.to_datetime(time_str, format=fmt)
            except ValueError:
                continue
        # Fallback to pandas auto-detection
        return pd.to_datetime(time_str, dayfirst=True)
    except Exception:
        return None


def get_odometer_dicts(df_od: pd.DataFrame, dt_date: datetime) -> tuple[dict, dict]:
    """
    Extract odometer readings for two periods from the dataframe.
    Returns: (odo_now_dict, odo_prev_dict)
    """
    d1, d2, d3, d4 = get_date_ranges(dt_date)
    odo_now, odo_prev = {}, {}

    for _, row in df_od.iterrows():
        try:
            t = parse_odometer_time(row['time'])
            if t is None:
                continue
            car = str(row['car_number']).strip()
            val = int(row['odometer'])
            if d1 < t < d2:
                odo_now[car] = val
            elif d3 < t < d4:
                odo_prev[car] = val
        except (ValueError, KeyError, TypeError):
            continue

    return odo_now, odo_prev


def calculate_odometer_diff(odo_now: dict, odo_prev: dict) -> dict:
    """Calculate difference between current and previous odometer readings."""
    return {car: odo_now[car] - odo_prev.get(car, 0) for car in odo_now}


def find_missing_cars(cars_list: list, odo_now: dict, odo_prev: dict) -> tuple[list, list]:
    """
    Find cars missing data in current and previous periods.
    Returns: (missing_current, missing_previous)
    """
    d1_cars = list(odo_now.keys())
    d2_cars = list(odo_prev.keys())

    missing_current = [car for car in cars_list if car not in d1_cars]
    missing_previous = [car for car in cars_list if car not in d2_cars]

    return missing_current, missing_previous


def format_missing_cars_output(missing_cars: list, car_phones: dict) -> str:
    """
    Format missing cars with phone numbers for copy-paste.
    
    Output format: phone numbers separated by ", " (no trailing comma).
    Cars without phone numbers are skipped (warnings handled by caller).
    
    Returns:
        String of phone numbers joined by comma and space.
    """
    
    if not missing_cars:
        return "Все автомобили имеют данные ✅"

    phones = []
    for car in missing_cars:
        phone = car_phones.get(car)
        if phone:
            phones.append(phone)

    # Join with ", " - no trailing comma
    if phones:
        return ", ".join(phones)
    else:
        return "Телефонов для указанных автомобилей не найдено"


def get_missing_cars_simple(missing_cars: list) -> str:
    """Get simple comma-separated list of missing car numbers."""
    if not missing_cars:
        return ""
    return ", ".join(missing_cars)