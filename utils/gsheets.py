"""
Google Sheets service account utilities.
Uses Streamlit secrets for credentials.
"""
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from utils.constants import GSHEETS_SPREADSHEET_NAME, GSHEETS_WORKSHEET_INDEX


@st.cache_resource
def get_gspread_client():
    """Get authenticated gspread client using service account from secrets."""
    try:
        # Get service account info from secrets
        service_account_info = st.secrets["gcp_service_account"]
    except KeyError:
        raise ValueError(
            "Google Cloud service account credentials not found in Streamlit secrets. "
            "Add them under [gcp_service_account] in .streamlit/secrets.toml"
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_odometer_dataframe() -> pd.DataFrame:
    """Fetch odometer data from Google Sheets and return as DataFrame."""
    gc = get_gspread_client()
    sheet = gc.open(GSHEETS_SPREADSHEET_NAME)
    worksheet = sheet.get_worksheet(GSHEETS_WORKSHEET_INDEX)
    data = worksheet.get_all_values()

    if not data:
        return pd.DataFrame(columns=["time", "car_number", "odometer"])

    df = pd.DataFrame(data[1:], columns=["time", "car_number", "odometer"])
    return df


def clear_odometer_cache():
    """Clear the cached odometer data."""
    get_odometer_dataframe.clear()