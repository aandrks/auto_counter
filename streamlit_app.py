"""
Main Streamlit application entry point.
Run with: streamlit run streamlit_app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Auto Counter",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Navigation
pg = st.navigation([
    st.Page("pages/odometers_check.py", title=" Odometers Check", icon="📊"),
    st.Page("pages/fuel_counting.py", title=" Fuel Counting", icon="⛽"),
    st.Page("pages/cards_admin.py", title=" Cards DB", icon="💳"),
])

pg.run()