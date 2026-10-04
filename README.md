# Auto Counter - Streamlit App

Streamlit web interface for two vehicle fleet management tools:
1. **Odometers Check** - Find vehicles missing odometer data for a given month
2. **Fuel Counting** - Parse fuel Excel files and calculate consumption per vehicle

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure secrets
Copy the template and fill in your values:
```bash
cp .streamlit/secrets.toml .streamlit/secrets.local.toml
# Edit .streamlit/secrets.local.toml with your actual credentials
```

**Required secrets:**
- `gcp_service_account` - Google Cloud service account JSON for Sheets API
- `car_phones` - Car number → phone mapping for notifications
- `cards_mapping` - Fuel card → car mapping for fuel parsing

### 3. Google Cloud Setup
1. Create a Google Cloud project
2. Enable **Google Sheets API** and **Google Drive API**
3. Create a Service Account (IAM → Service Accounts)
4. Download JSON key
5. Share your Google Sheet ("форма_пробег_информация") with the service account email
6. Copy the JSON values to `.streamlit/secrets.toml`

### 4. Run the app
```bash
streamlit run streamlit_app.py
```

## 📁 Project Structure
```
auto_counter/
├── streamlit_app.py          # Main entry point with navigation
├── requirements.txt          # Python dependencies
├── .streamlit/
│   └── secrets.toml          # Secrets template (copy to secrets.local.toml)
├── utils/
│   ├── constants.py          # Shared constants (car list, norms)
│   ├── gsheets.py            # Google Sheets service account client
│   ├── odometer_logic.py     # Core odometer calculation logic
│   └── fuel_logic.py         # Core fuel parsing & calculation logic
└── pages/
    ├── odometers_check.py    # Page 1: Check missing odometer data
    └── fuel_counting.py      # Page 2: Parse fuel data & calculate consumption
```

## 🔧 Features

### Odometers Check Page
- Select month/year to check
- Fetches data from Google Sheets automatically
- Shows vehicles missing data in current & previous periods
- Displays phone numbers for quick contact
- Copy-paste ready car number lists

### Fuel Counting Page
- Upload two Excel fuel data files
- Auto-detects reporting period from file content
- Fetches odometer data from Google Sheets for same period
- Calculates consumption (L/100km) per vehicle
- Flags abnormal consumption (>3 L/100km from norm)
- Export results to CSV/Excel

## 🔐 Secrets Reference

### gcp_service_account
Full service account JSON from Google Cloud. All fields required.

### car_phones
```toml
[car_phones]
"709" = "+7 999 123 45 67"
"664" = "+7 999 123 45 68"
```

### cards_mapping
Maps fuel card numbers to [gasoline_car, diesel_car] pairs:
```toml
[cards_mapping]
"1234567890" = ["709 (Газ)", "709 (ДТ)"]
```

The car number is extracted from parentheses (e.g., "709" from "709 (Газ)").

## 📝 Notes

- All calculation algorithms preserved from original Colab scripts
- Odometer date ranges: current period (dt-10 to dt+18), previous (dt-40 to dt-14)
- Fuel parsing uses "Итого по" rows with minimum numeric value
- Abnormal threshold: >3 L/100km deviation from norm
- Data cached for 5 minutes (configurable in `gsheets.py`)

## 🐛 Troubleshooting

**"Google Cloud service account credentials not found"**
- Ensure `.streamlit/secrets.toml` exists with `gcp_service_account` section
- Restart Streamlit after adding secrets

**"No data retrieved from Google Sheets"**
- Check service account has access to the spreadsheet
- Verify spreadsheet name matches "форма_пробег_информация"
- Check worksheet index (0 = first sheet)

**Date parsing issues**
- Fuel files must contain text like "с 01.01.2024 по" for period detection
- Odometer timestamps must be parseable (dd/mm/yyyy or similar)