"""
Supabase database utilities for cards storage.
Table schema: id, card (text), car_n (text, matching), car_s (text, display), f_type (0|1)
"""
import streamlit as st
from supabase import create_client, Client

from utils.cards_transform import (
    mapping_from_rows, rows_from_json_dict, car_name_map_from_rows, ALLOWED_F_TYPE
)


def get_supabase_client() -> Client:
    """Get Supabase client from secrets."""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except (KeyError, TypeError):
        raise ValueError(
            "Supabase credentials not found in secrets. "
            "Add [supabase] section with url and key to .streamlit/secrets.toml"
        )
    return create_client(url, key)


def fetch_all_cards() -> list[dict]:
    """Fetch all card rows from Supabase, ordered by id.
    Returns list of dicts: [{'id', 'card', 'car_n', 'car_s', 'f_type'}]
    """
    sb = get_supabase_client()
    response = sb.table("cards").select("*").order("id").execute()
    return response.data or []


@st.cache_data(ttl=120, show_spinner=False)
def fetch_all_cards_cached() -> list[dict]:
    """Cached version of fetch_all_cards (for Fuel Counting page reads)."""
    return fetch_all_cards()


def clear_cards_cache():
    """Clear cached cards data (call after admin edits)."""
    fetch_all_cards_cached.clear()


def fetch_cards_mapping() -> dict:
    """
    Fetch cards from Supabase and build the mapping consumed by the
    (unchanged) fuel parsing algorithm:
        {card: [car_n_for_92/95, car_n_for_ДТ]}
    Matching against odometer data uses car_n (the numeric car number),
    exactly as designed. Display names come via fetch_car_name_map().
    """
    rows = fetch_all_cards_cached()
    return mapping_from_rows(rows, value_key="car_n")


def fetch_car_name_map() -> dict:
    """
    Fetch display mapping {car_n: car_s} from Supabase.
    Used by build_result_dataframe to show full car names while
    matching by car_n.
    """
    rows = fetch_all_cards_cached()
    return car_name_map_from_rows(rows)


def insert_card(card: str, car_n: str, car_s: str, f_type: int) -> dict:
    """Insert one card row."""
    sb = get_supabase_client()
    response = sb.table("cards").insert(
        {"card": card, "car_n": car_n, "car_s": car_s, "f_type": int(f_type)}
    ).execute()
    return response.data


def update_card(row_id: int, card: str, car_n: str, car_s: str, f_type: int) -> dict:
    """Update one card row by id."""
    sb = get_supabase_client()
    response = sb.table("cards").update(
        {"card": card, "car_n": car_n, "car_s": car_s, "f_type": int(f_type)}
    ).eq("id", row_id).execute()
    return response.data


def delete_card(row_id: int) -> dict:
    """Delete one card row by id."""
    sb = get_supabase_client()
    response = sb.table("cards").delete().eq("id", row_id).execute()
    return response.data


def bulk_replace_all(rows: list[dict]) -> None:
    """Replace entire table content (used by seed)."""
    sb = get_supabase_client()
    sb.table("cards").delete().neq("id", 0).execute()  # delete everything
    if rows:
        sb.table("cards").insert(rows).execute()


def seed_from_local_json(json_path: str = "car_cards.json") -> int:
    """
    Seed database from local car_cards.json file (one-time migration).
    Keeps values verbatim as written in JSON (including 'None').
    Empty strings '' are skipped. Returns number of inserted rows.
    """
    import json as _json
    with open(json_path, "r", encoding="utf-8") as f:
        data = _json.load(f)

    rows = rows_from_json_dict(data)
    if rows:
        bulk_replace_all(rows)
    return len(rows)