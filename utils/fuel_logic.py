"""
Core fuel counting logic - extracted from original fuel_counting.py.
Algorithms preserved exactly as in original.
"""
import pandas as pd
import re
import json
from datetime import datetime
from utils.constants import DEFAULT_CARS_LIST, DEFAULT_NORM_DICT
from utils.odometer_logic import (
    parse_odometer_time, get_odometer_dicts, calculate_odometer_diff
)


def extract_date_from_fuel_data(df: pd.DataFrame) -> datetime:
    """Extract date from fuel data text (pattern: 'с DD.MM.YYYY по')."""
    str_df = df.to_string(index=False)
    a = re.findall(r"с (\d{2}.\d{2}.\d{4}) по", str_df)
    if a:
        return datetime.strptime(a[0], "%d.%m.%Y")
    return datetime.now()


def load_cards_mapping(cards_json_str: str) -> dict:
    """Load card to car mapping from JSON string."""
    return json.loads(cards_json_str)


def extract_card_number(row_str: str) -> str | None:
    """Extract card number from row string."""
    match = re.search(r'Карта:\s*(\d+)', row_str)
    return match.group(1) if match else None


def extract_number(s: str) -> str:
    """Extract 3-digit number from parentheses or return stripped string."""
    if not s:
        return ""
    finds = re.findall(r'\((\d{3})\)', str(s))
    return finds[-1] if finds else str(s).strip()


def is_gasoline(row_str: str) -> bool:
    """Check if fuel type is gasoline (vs diesel)."""
    return any(x in row_str for x in ["95", "92", "Аи"])


def parse_fuel_excel(df: pd.DataFrame, cards_mapping: dict) -> tuple[dict, dict]:
    """
    Parse fuel data from Excel dataframe.
    Returns: (dict_fuel, dict_diesel) with structure:
    {car_number: {'liters': float, 'types': set, 'cards': set}}
    """
    dict_fuel = {}
    dict_diesel = {}
    current_card = ""

    for _, row in df.iterrows():
        row_str = " ".join([str(x) for x in row.tolist()])

        # Detect card number
        if 'Карта' in row_str:
            card = extract_card_number(row_str)
            if card:
                current_card = card

        # Process fuel totals
        if 'Итого по' in row_str and current_card:
            # Find numeric values in row
            numeric_vals = []
            for x in row:
                if pd.notna(x):
                    s = str(x).replace(',', '.')
                    if re.match(r'^\d+\.?\d*$', s):
                        numeric_vals.append(float(s))

            if not numeric_vals:
                continue

            fuel_val = min(numeric_vals)  # Original logic uses min
            car_names = cards_mapping.get(current_card, ["Unknown", "Unknown"])

            is_gas = is_gasoline(row_str)
            target_name = car_names[0] if is_gas else car_names[1]
            target_dict = dict_fuel if is_gas else dict_diesel

            clean_name = extract_number(target_name)
            if clean_name not in target_dict:
                target_dict[clean_name] = {'liters': 0, 'types': set(), 'cards': set()}

            target_dict[clean_name]['liters'] += fuel_val
            target_dict[clean_name]['types'].add(row_str.split(':')[0].strip())
            target_dict[clean_name]['cards'].add(current_card)

    return dict_fuel, dict_diesel


def build_car_name_mapping(cards_mapping: dict) -> dict:
    """
    Build mapping from car number to full name from cards_mapping.
    Returns dict like {"977": "Sollers Argo (977)", "020": "Sollers Argo (020)"}
    """
    car_name_map = {}
    for card, (gas_name, diesel_name) in cards_mapping.items():
        # Extract car numbers and full names from both gas and diesel entries
        for name in [gas_name, diesel_name]:
            if not name or name == "None":
                continue
            # Handle multiple cars separated by " / "
            for part in name.split(" / "):
                part = part.strip()
                if not part:
                    continue
                # Extract car number from parentheses
                import re
                matches = re.findall(r'\((\d{3})\)', part)
                for car_num in matches:
                    if car_num not in car_name_map:
                        car_name_map[car_num] = part
    return car_name_map


def build_result_dataframe(
    dict_fuel: dict,
    dict_diesel: dict,
    odo_now_dict: dict,
    odo_prev_dict: dict,
    od_diff_dict: dict,
    cars_list: list = None,
    norm_dict: dict = None,
    car_name_map: dict = None
) -> pd.DataFrame:
    """Build final result DataFrame with consumption calculations.
    
    All available data is shown:
    - Fuel: total liters (0 if no fuel data)
    - Month1/Month2: odometer readings if they exist
    - Odometer: distance (Month1 - Month2) if both exist
    - Result: consumption (L/100km) only if fuel > 0 and odometer > 0
    """
    if cars_list is None:
        cars_list = DEFAULT_CARS_LIST
    if norm_dict is None:
        norm_dict = DEFAULT_NORM_DICT
    if car_name_map is None:
        car_name_map = {}

    final_rows = []
    for car in cars_list:
        f_data = dict_fuel.get(car, {'liters': 0, 'types': set(), 'cards': set()})
        d_data = dict_diesel.get(car, {'liters': 0, 'types': set(), 'cards': set()})

        total_liters = f_data['liters'] + d_data['liters']
        all_cards = ", ".join(f_data['cards'] | d_data['cards'])
        all_types = ", ".join(f_data['types'] | d_data['types'])

        odo_now = odo_now_dict.get(car)
        odo_prev = odo_prev_dict.get(car)
        
        # Calculate distance only if both readings exist
        distance = None
        if odo_now is not None and odo_prev is not None:
            distance = odo_now - odo_prev
            if distance < 0:
                distance = None  # Invalid negative distance

        # Consumption only if we have fuel AND valid distance
        consumption = None
        if distance is not None and distance > 0 and total_liters > 0:
            consumption = round((total_liters / distance * 100), 2)

        # Get full car name from mapping, fallback to car number
        display_name = car_name_map.get(car, car)

        final_rows.append({
            "Car": display_name,
            "Result": consumption,
            "Fuel": total_liters if total_liters > 0 else None,  # None if no fuel data
            "Odometer": distance,
            "Car_number": car,
            "Month1": odo_now,
            "Month2": odo_prev,
            "Type": all_types,
            "Card": all_cards
        })

    result = pd.DataFrame(final_rows)

    # Add abnormal flag only for rows with consumption data
    def check_abnormal(row):
        if pd.notna(row['Result']):
            norm = norm_dict.get(str(row['Car_number']), 0)
            return '1' if abs(row['Result'] - norm) > 3 else ''
        return ''

    result['Abnormal'] = result.apply(check_abnormal, axis=1)
    return result