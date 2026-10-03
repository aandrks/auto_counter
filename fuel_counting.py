import pandas as pd
import json
import re
from google.colab import files, drive
from datetime import datetime, timedelta

!pip install gspread pandas openpyxl -q

import pandas as pd
import gspread
from google.colab import auth
from google.auth import default

log_no_data_cars = []
log_values = []
unknown_cards = []
dict_fuel = {}
dict_diesel = {}

# cars_list = ['273', '311', '072', '977', '757', '2650']
cars_list = [
        '709', '664', '647', '945', '830', '586', '072', '774', '311', '020',
        '273', '252', '977', '930', '587', '358', '582', '913', '697', '633',
        '333', '558', '947', '380', '121', '934', '213', '862', '497', '057',
        '970', '428', '614', '923', '895'
    ]

norm_dict = {
    '709': 14, '664': 22, '647': 22, '945': 11, '830': 11, '586': 14, '072': 13,
    '774': 22, '311': 11, '020': 14, '273': 11, '252': 14, '977': 14, '930': 13,
    '587': 15, '358': 14, '582': 11, '913': 13, '697': 12, '633': 12, '333': 12,
    '558': 12, '947': 12, '380': 12, '121': 12, '934': 12, '213': 13, '862': 11,
    '497': 12, '057': 12, '970': 11, '428': 12, '614': 12, '923': 12, '895': 12
}

drive.mount('/content/drive', force_remount=True)
with open("/content/drive/MyDrive/fuel_results/cards.json", "r", encoding="utf-8") as f:
    cards_json = json.load(f)

def upload_and_read_excel():
    uploaded1 = files.upload()
    uploaded2 = files.upload()
    df1 = pd.read_excel(list(uploaded1.keys())[0])
    df2 = pd.read_excel(list(uploaded2.keys())[0])
    return pd.concat([df1, df2], ignore_index=True)

df = upload_and_read_excel()
str_df = df.to_string(index=False)

def get_file_odometers():
    auth.authenticate_user()
    creds, _ = default()
    gc = gspread.authorize(creds)
    sheet = gc.open("форма_пробег_информация")
    worksheet = sheet.get_worksheet(0)
    data = worksheet.get_all_values()
    return pd.DataFrame(data[1:], columns=["time", "car_number", "odometer"])

df_od = get_file_odometers()

def extract_date(s):
    a = re.findall(r"с (\d{2}.\d{2}.\d{4}) по", s)
    return a[0] if a else datetime.now().strftime("%d.%m.%Y")

date_str = extract_date(str_df)
dt_date = datetime.strptime(date_str, "%d.%m.%Y")

def get_odometer_dicts():
    d1, d2 = dt_date - timedelta(days=10), dt_date + timedelta(days=18)
    d3, d4 = dt_date - timedelta(days=40), dt_date - timedelta(days=14)
    odo_now, odo_prev = {}, {}
    for _, row in df_od.iterrows():
        try:
            t = pd.to_datetime(row['time'], dayfirst=True)
            car = str(row['car_number']).strip()
            val = int(row['odometer'])
            if d1 < t < d2: odo_now[car] = val
            elif d3 < t < d4: odo_prev[car] = val
        except: continue
    return odo_now, odo_prev

odo_now_dict, odo_prev_dict = get_odometer_dicts()
od_diff_dict = {car: odo_now_dict[car] - odo_prev_dict.get(car, 0) for car in odo_now_dict}

def extract_number(s):
    if not s: return ""
    finds = re.findall(r'\((\d{3})\)', str(s))
    return finds[-1] if finds else str(s).strip()

# Main data extraction
current_card = ""
for _, row in df.iterrows():
    row_str = " ".join([str(x) for x in row.tolist()])
    if 'Карта' in row_str:
        match = re.search(r'Карта:\s*(\d+)', row_str)
        if match: current_card = match.group(1)

    if 'Итого по' in row_str and current_card:
        numeric_vals = [float(x) for x in row if pd.notna(x) and str(x).replace('.','',1).isdigit()]
        if not numeric_vals: continue
        fuel_val = min(numeric_vals)
        car_names = cards_json.get(current_card, ["Unknown", "Unknown"])

        is_gas = any(x in row_str for x in ["95", "92", "Аи"])
        target_name = car_names[0] if is_gas else car_names[1]
        target_dict = dict_fuel if is_gas else dict_diesel

        clean_name = extract_number(target_name)
        if clean_name not in target_dict:
            target_dict[clean_name] = {'liters': 0, 'types': set(), 'cards': set()}

        target_dict[clean_name]['liters'] += fuel_val
        target_dict[clean_name]['types'].add(row_str.split(':')[0].strip())
        target_dict[clean_name]['cards'].add(current_card)

final_rows = []
for car in cars_list:
    f_data = dict_fuel.get(car, {'liters': 0, 'types': set(), 'cards': set()})
    d_data = dict_diesel.get(car, {'liters': 0, 'types': set(), 'cards': set()})

    total_liters = f_data['liters'] + d_data['liters']
    all_cards = ", ".join(f_data['cards'] | d_data['cards'])
    all_types = ", ".join(f_data['types'] | d_data['types'])

    odo_now = odo_now_dict.get(car)
    odo_prev = odo_prev_dict.get(car)
    distance = od_diff_dict.get(car)

    consumption = round((total_liters / distance * 100), 2) if distance and distance > 0 else None

    final_rows.append({
        "Car": car, "Result": consumption, "Fuel": total_liters, "Odometer": distance,
        "Car_number": car, "Month1": odo_now, "Month2": odo_prev, "Type": all_types, "Card": all_cards
    })

result = pd.DataFrame(final_rows)
result['Abnormal'] = result.apply(lambda r: '1' if pd.notna(r['Result']) and abs(r['Result'] - norm_dict.get(str(r['Car_number']), 0)) > 3 else '', axis=1)

path_out = f"/content/drive/MyDrive/fuel_results/final_report_{dt_date.strftime('%m_%Y')}.xlsx"
result.to_excel(path_out, index=False)
print(f"✅ Данные записаны (всего машин: {len(result)}): {path_out}")