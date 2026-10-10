"""
Shared constants for both modules.
These can be overridden via Streamlit secrets.
"""

# Default car list - can be overridden in secrets.toml
DEFAULT_CARS_LIST = [
    '709', '664', '647', '945', '830', '586', '072', '774', '311', '020',
    '273', '252', '977', '930', '587', '358', '582', '913', '697', '633',
    '333', '558', '947', '380', '121', '934', '213', '862', '497', '057',
    '970', '428', '614', '923', '895'
]

# Small car list (alternative)
SMALL_CARS_LIST = ['273', '311', '072', '977', '757', '2650']

# Default norms dictionary - can be overridden in secrets.toml
DEFAULT_NORM_DICT = {
    '709': 14, '664': 22, '647': 22, '945': 11, '830': 11, '586': 14, '072': 13,
    '774': 22, '311': 11, '020': 14, '273': 11, '252': 14, '977': 14, '930': 13,
    '587': 15, '358': 14, '582': 11, '913': 13, '697': 12, '633': 12, '333': 12,
    '558': 12, '947': 12, '380': 12, '121': 12, '934': 12, '213': 13, '862': 11,
    '497': 12, '057': 12, '970': 11, '428': 12, '614': 12, '923': 12, '895': 12
}

# Google Sheets configuration
GSHEETS_SPREADSHEET_NAME = "форма_пробег_информация"
GSHEETS_WORKSHEET_INDEX = 0

# Columns of the Fuel Counting report.
# Each entry is a dict: {"key", "label", "format", "width"}
#   key    - internal column from build_result_dataframe() (DO NOT rename it)
#   label  - header shown on screen and in CSV/Excel. May use the placeholders
#            {month_now} / {month_prev} which are replaced with real month names
#            (e.g. "Сентябрь 2026" / "Август 2026").
#   format - number format for on-screen display ("%.2f" / "%.1f" / "%d") or
#            None for text
#   width  - column width (in characters) for the exported Excel file
# To rename -> edit "label"; reorder -> move the dict; hide -> delete the dict.
# Available keys: Car, Result, Fuel, Odometer, Month1, Month2, Car_number, Type,
#                 Card, Abnormal
FUEL_REPORT_COLUMNS = [
    {"key": "Car",      "label": "Авто",          "format": None,   "width": 28},
    {"key": "Result",   "label": "Расход",        "format": "%.2f", "width": 12},
    {"key": "Fuel",     "label": "Топливо (мес)", "format": "%.1f", "width": 14},
    {"key": "Odometer", "label": "Одометр (мес)", "format": "%d",   "width": 14},
    {"key": "Month2",   "label": "{month_prev}",  "format": "%d",   "width": 14},
    {"key": "Month1",   "label": "{month_now}",   "format": "%d",   "width": 14},
]

# Month names for the auto-labeled odometer columns ({month_now}/{month_prev}).
# Replace with English names (e.g. "January", ...) if needed.
MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

# Template of the auto month label. Placeholders: {month}, {year}, {num} (MM.YYYY).
FUEL_MONTH_LABEL_FORMAT = "{month} {year}"