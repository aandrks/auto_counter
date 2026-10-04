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