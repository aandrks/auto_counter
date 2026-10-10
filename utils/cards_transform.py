"""
Pure transformation logic between car_cards.json structure and DB rows.
No streamlit/supabase dependencies - safe to import from standalone scripts.

JSON structure (verbatim from car_cards.json):
    {card: [car_for_92/95, car_for_ДТ]}
    - position 0 -> f_type 0 (92/95 benzin)
    - position 1 -> f_type 1 (ДТ diesel)
    - "" empty slot -> no row created

DB row schema: card (text), car_n (text, for matching), car_s (text, for display), f_type (0|1)
"""
import re

ALLOWED_F_TYPE = [0, 1]


def extract_car_number(name: str) -> str:
    """
    Extract numeric car number from display name for matching.
    Mirrors original extract_number() behavior:
    - last number inside parentheses wins ("Sollers Argo (977)" -> "977")
    - supports any digit count ("Tenet (2650)" -> "2650")
    - fallback: whole string stripped ("358" -> "358")
    """
    if not name:
        return ""
    matches = re.findall(r'\((\d+)\)', str(name))
    return matches[-1] if matches else str(name).strip()


def rows_from_json_dict(data: dict) -> list[dict]:
    """
    Pure transformation: car_cards.json structure -> DB rows.
    Returns list of dicts: [{'card', 'car_n', 'car_s', 'f_type'}]
    """
    rows = []
    for card, names in data.items():
        if not isinstance(names, list):
            continue
        # position 0 -> f_type 0 (92/95), position 1 -> f_type 1 (ДТ)
        slots = [
            (0, names[0] if len(names) > 0 else ""),
            (1, names[1] if len(names) > 1 else ""),
        ]
        for f_type, name in slots:
            if name == "":
                continue
            rows.append({
                "card": card,
                "car_n": extract_car_number(name),
                "car_s": name,
                "f_type": f_type,
            })
    return rows


def mapping_from_rows(rows: list[dict], value_key: str = "car_s") -> dict:
    """
    Pure transformation: DB rows -> mapping {card: [value_for_92/95, value_for_ДТ]}.
    Value is taken from the given column (car_n for odometer matching, car_s for display).
    Last row wins on duplicates (same as JSON behavior).
    """
    mapping: dict = {}
    for row in rows:
        card = str(row["card"])
        if card not in mapping:
            mapping[card] = ["", ""]
        idx = 0 if int(row["f_type"]) == 0 else 1
        mapping[card][idx] = row[value_key]
    return mapping


def car_name_map_from_rows(rows: list[dict]) -> dict:
    """
    Build display mapping from DB rows: {car_n: car_s}.
    Used to show full car names while matching by car number.
    Last row wins on duplicate car_n.
    """
    names: dict = {}
    for row in rows:
        car_n = row.get("car_n")
        car_s = row.get("car_s")
        if car_n and car_s:
            names[car_n] = car_s
    return names