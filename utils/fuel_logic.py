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
    """Check if fuel type is gasoline (vs diesel).

    Only the row label (text before the first ':') is inspected: money amounts
    may coincidentally contain the digits '92'/'95' (e.g. 29530.8) and must not
    affect the fuel-type classification.
    """
    label = row_str.split(":")[0]
    return any(x in label for x in ["95", "92", "Аи"])


# Summary rows ('Итого по карте:' / 'Итого по отчету:') duplicate the
# per-fuel 'Итого по ...' totals and are skipped when counting liters.
# Markers are matched as substrings of the row label: in real xls the label
# cell is often not the first one (e.g. "nan … 29530.8 Итого по карте:").
SUMMARY_MARKERS = ("по карте", "по отчету", "по отчёту")
SUMMARY_SKIP_STATUS = "Итоговая строка, в расчёт не берётся"

# Statuses of the diagnostics log (build_parse_log) that denote a record needing
# attention. Kept as constants because they are reused to build the Cards DB
# fill-in table (build_unknowns).
STATUS_CARD_NOT_FOUND = "Карта не найдена в справочнике"
STATUS_EMPTY_SLOT = "Авто не указано для этого типа топлива"
STATUS_NO_NUMBERS = "Нет чисел в строке"
STATUS_NO_CARD_ABOVE = "Нет карты выше по файлу"
STATUS_UNKNOWN_TYPE = "Тип топлива не распознан"


def fuel_row_label(row_str: str) -> str:
    """Label text of a row before the first ':'."""
    return str(row_str).split(":")[0].strip()


def is_summary_total(row_str: str) -> bool:
    """True for redundant summary rows that duplicate per-fuel totals."""
    label = fuel_row_label(row_str).lower()
    return any(marker in label for marker in SUMMARY_MARKERS)


def fuel_type(row_str: str) -> str:
    """Fuel type for a row: '92/95', 'ДТ' or 'неизвестен' (from the label)."""
    label = fuel_row_label(row_str).lower()
    if any(x in label for x in ["95", "92", "аи"]):
        return "92/95"
    if any(x in label for x in ["дт", "диз"]):
        return "ДТ"
    return "неизвестен"


def _row_numeric_values(row) -> list:
    """Numeric values of a row (same rule as parse_fuel_excel)."""
    vals = []
    for x in row:
        if pd.notna(x):
            s = str(x).replace(',', '.')
            if re.match(r'^\d+\.?\d*$', s):
                vals.append(float(s))
    return vals


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

        # Process fuel totals; skip redundant summary rows
        if 'Итого по' in row_str and current_card and not is_summary_total(row_str):
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


def build_parse_log(
    df: pd.DataFrame,
    cards_mapping: dict,
    car_name_map: dict = None,
    period: str = "",
) -> pd.DataFrame:
    """
    Build a diagnostics log of fuel parsing - one row per 'Итого по ...' line.

    This does NOT change parsing itself (parse_fuel_excel is untouched): it walks
    the same detection rules and records every decision for verification.

    Columns: Период, № строки, Карта, Литры, Тип, Авто(номер), Авто(название),
    Статус, Исходная строка.

    Statuses: 'OK', 'Карта не найдена в справочнике', 'Нет чисел в строке',
    'Нет карты выше по файлу', 'Тип топлива не распознан',
    'Авто не указано для этого типа топлива',
    SUMMARY_SKIP_STATUS ('Итоговая строка, в расчёт не берётся').

    Edge-case rows (everything except 'OK' and the summary status) should be
    surfaced to the user (st.warning on the page).
    """
    if car_name_map is None:
        car_name_map = {}

    log_rows = []
    current_card = ""

    for idx, row in df.iterrows():
        row_str = " ".join([str(x) for x in row.tolist()])

        # Detect card number (same rule as parse_fuel_excel)
        if 'Карта' in row_str:
            card = extract_card_number(row_str)
            if card:
                current_card = card

        # Process fuel totals (log both parsed and unparsed 'Итого по' rows)
        if 'Итого по' in row_str:
            ftype = fuel_type(row_str)
            entry = {
                'Период': period,
                '№ строки': int(idx) + 1,
                'Карта': current_card,
                'Литры': None,
                'Тип': ftype,
                'Авто(номер)': '',
                'Авто(название)': '',
                'Статус': 'OK',
                'Исходная строка': str(row_str).strip(),
            }

            # Summary rows ('Итого по карте' / 'Итого по отчету') duplicate the
            # per-fuel totals and are not counted into any car.
            if is_summary_total(row_str):
                numeric_vals = _row_numeric_values(row)
                entry['Литры'] = min(numeric_vals) if numeric_vals else None
                entry['Тип'] = '—'
                entry['Статус'] = SUMMARY_SKIP_STATUS
                log_rows.append(entry)
                continue

            if not current_card:
                entry['Статус'] = STATUS_NO_CARD_ABOVE
                log_rows.append(entry)
                continue

            numeric_vals = _row_numeric_values(row)
            if not numeric_vals:
                entry['Статус'] = STATUS_NO_NUMBERS
                log_rows.append(entry)
                continue

            entry['Литры'] = min(numeric_vals)  # same as original logic

            is_gas = is_gasoline(row_str)
            if current_card not in cards_mapping:
                entry['Статус'] = STATUS_CARD_NOT_FOUND
            else:
                car_names = cards_mapping[current_card]
                target_name = car_names[0] if is_gas else car_names[1]
                clean_name = extract_number(target_name)
                entry['Авто(номер)'] = clean_name
                entry['Авто(название)'] = car_name_map.get(
                    clean_name, target_name if target_name != "Unknown" else ""
                )
                if not clean_name:
                    entry['Статус'] = STATUS_EMPTY_SLOT
                elif ftype == 'неизвестен':
                    entry['Статус'] = STATUS_UNKNOWN_TYPE
                else:
                    entry['Статус'] = 'OK'

            log_rows.append(entry)

    return pd.DataFrame(log_rows, columns=[
        'Период', '№ строки', 'Карта', 'Литры', 'Тип',
        'Авто(номер)', 'Авто(название)', 'Статус', 'Исходная строка',
    ])


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


# ---------------------------------------------------------------------------
# Unknowns for the Cards DB fill-in table
# ---------------------------------------------------------------------------
CAT_CARD_NOT_FOUND = "Карта не в справочнике"
CAT_EMPTY_SLOT = "Нет авто для типа топлива"
CAT_CAR_NO_CARD = "Нет карты у авто"
CAT_NO_RESULT = "Расход не посчитан (нет одометрии)"
CAT_NO_FUEL = "Нет топлива за период"

# Category order used everywhere (warning + Cards DB table):
# cars without a card come first, cards without a car after them.
UNKNOWN_CATEGORY_ORDER = [
    CAT_CAR_NO_CARD,
    CAT_CARD_NOT_FOUND,
    CAT_EMPTY_SLOT,
    CAT_NO_RESULT,
    CAT_NO_FUEL,
]

# Columns shared by the fill-in and reference tables.
UNKNOWN_COLUMNS = ["Категория", "card", "car_n", "f_type", "car_s", "Литры"]


def _fuel_type_to_int(ftype: str) -> int:
    """Map a log fuel type ('92/95' / 'ДТ') to f_type (0 = 92/95, 1 = ДТ)."""
    return 1 if "дт" in str(ftype).lower() else 0


def _car_cards(cards_mapping: dict, car_n: str) -> str:
    """Comma-joined card numbers that reference the given car number."""
    found = []
    for card, slots in cards_mapping.items():
        for slot in slots:
            for part in str(slot).split(" / "):
                if extract_number(part) == car_n:
                    found.append(card)
                    break
    return ", ".join(found)


def build_unknowns(
    parse_log: pd.DataFrame,
    result_df: pd.DataFrame,
    cards_mapping: dict,
    car_name_map: dict,
    fuel_liters: dict,
    candidate_cars=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the two diagnostics tables for the Cards DB page.

    Returns (fillin, reference):
    - fillin    - rows that are missing a value and can be saved to the DB:
                  a card without a car (unknown card / empty slot) or
                  a car without a card.
    - reference - diagnostics for cars whose consumption could not be computed
                  (fuel present but no odometer) or that have a card but no fuel.

    Both use UNKNOWN_COLUMNS. ``f_type`` follows the DB convention
    (0 = 92/95, 1 = ДТ). Categories are ordered by UNKNOWN_CATEGORY_ORDER.
    """
    if candidate_cars is None:
        candidate_cars = set()
    candidate_cars = {str(c) for c in candidate_cars}

    mapped_cars = set()
    for slots in cards_mapping.values():
        for slot in slots:
            for part in str(slot).split(" / "):
                n = extract_number(part)
                if n:
                    mapped_cars.add(n)

    fuel_cars = {str(c) for c, v in fuel_liters.items() if v}

    # --- Cards without a car: unknown cards and empty slots for the fuel type ---
    fillin = []
    problem = parse_log[
        parse_log["Статус"].isin([STATUS_CARD_NOT_FOUND, STATUS_EMPTY_SLOT])
    ]
    if len(problem):
        grouped = (
            problem.groupby(["Карта", "Тип"], dropna=False)["Литры"]
            .sum()
            .reset_index()
        )
        for _, r in grouped.iterrows():
            card = r["Карта"]
            statuses = set(problem.loc[problem["Карта"] == card, "Статус"])
            category = (
                CAT_CARD_NOT_FOUND
                if STATUS_CARD_NOT_FOUND in statuses
                else CAT_EMPTY_SLOT
            )
            liters = r["Литры"]
            fillin.append({
                "Категория": category,
                "card": str(card),
                "car_n": "",
                "f_type": _fuel_type_to_int(r["Тип"]),
                "car_s": "",
                "Литры": round(float(liters), 2) if pd.notna(liters) else None,
            })

    # --- Cars without a card ---
    for car in sorted(candidate_cars, key=lambda x: (len(x), x)):
        if car in mapped_cars or not re.fullmatch(r"\d{1,4}", car):
            continue
        liters = fuel_liters.get(car, 0.0)
        fillin.append({
            "Категория": CAT_CAR_NO_CARD,
            "card": "",
            "car_n": car,
            "f_type": 0,
            "car_s": car_name_map.get(car, ""),
            "Литры": round(float(liters), 2) if liters else None,
        })

    fillin_df = pd.DataFrame(fillin, columns=UNKNOWN_COLUMNS)
    if len(fillin_df):
        fillin_df["_ord"] = fillin_df["Категория"].map(
            {c: i for i, c in enumerate(UNKNOWN_CATEGORY_ORDER)}
        )
        fillin_df = fillin_df.sort_values("_ord").drop(columns="_ord").reset_index(drop=True)

    # --- Reference: no consumption (fuel but no odometer) ---
    reference = []
    if {"Fuel", "Result", "Car_number"}.issubset(result_df.columns):
        for _, r in result_df.iterrows():
            if pd.notna(r["Fuel"]) and pd.isna(r["Result"]):
                car = str(r["Car_number"])
                reference.append({
                    "Категория": CAT_NO_RESULT,
                    "card": _car_cards(cards_mapping, car),
                    "car_n": car,
                    "f_type": 0,
                    "car_s": r.get("Car", ""),
                    "Литры": round(float(r["Fuel"]), 2),
                })

    # --- Reference: has a card but no fuel for the period ---
    for car in sorted((candidate_cars & mapped_cars) - fuel_cars, key=lambda x: (len(x), x)):
        reference.append({
            "Категория": CAT_NO_FUEL,
            "card": _car_cards(cards_mapping, car),
            "car_n": car,
            "f_type": 0,
            "car_s": car_name_map.get(car, ""),
            "Литры": None,
        })

    reference_df = pd.DataFrame(reference, columns=UNKNOWN_COLUMNS)
    return fillin_df, reference_df