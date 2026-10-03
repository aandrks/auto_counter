
import pandas as pd
import json
import re
from google.colab import files, drive
from datetime import datetime, timedelta
import calendar

!pip install gspread pandas -q

import pandas as pd
import gspread
from google.colab import auth
from google.auth import default

log_no_data_cars = []
log_values = []

date = ""
dt_date = None

dict_fuel = {}
dict_diesel = {}
drive.mount('/content/drive')

date = input("Input month and year in %m.%Y format for month you want to read data for: ")
month, year = map(int, date.split('.'))
# Get the last day of the month
last_day = calendar.monthrange(year, month)[1]
dt_date = datetime.strptime(f"{last_day}.{date}", "%d.%m.%Y")
print(dt_date)

def get_file_odometers():

  auth.authenticate_user()
  creds, _ = default()
  gc = gspread.authorize(creds)
  sheet = gc.open("форма_пробег_информация")
  worksheet = sheet.get_worksheet(0)
  data = worksheet.get_all_values()
  # print(data)
  # df = pd.DataFrame(data)
  df = pd.DataFrame(data[1:], columns = ["time", "car_number", "odometer"])
  print(df)
  return df

df_od = get_file_odometers()
print(df_od)


with open("my_a/car_phone.json", encoding="utf-8") as f:
  car_numbers = json.load(f)   #getting phone numbers as a dictionary here


def get_odometers():
  print(f"!!! Получаю данные за {dt_date.strftime("%B, %Y")}")
  cars = [
'709', '664', '647', '945', '830', '586', '072', '774', '311', '020',
'273', '252', '977', '930', '587', '358', '582', '913', '697', '633',
'333', '558', '947', '380', '121', '934', '213', '862', '497', '057',
'970', '428', '614', '923', '895'
]
  # print(difference)
  # dict = {}
  dict1 = {}
  dict2 = {}
  log = []
  # month = 12
  # d = date(2025, month - 1, 20)
  # d1 = date(2025, month, 20)
  # print(d)
  df = df_od
  print(df)
  a = []
  t = True
  d1 = dt_date - timedelta(days = 10)
  d2 = dt_date + timedelta(days = 15)
  d3 = dt_date - timedelta(days = 40)
  d4 = dt_date - timedelta(days = 14)
  print(d1)
  print(d2)
  for i, s in df.iterrows():
      # print(s)
      a.append(s['car_number'])
      t = pd.to_datetime(s['time'], format = "%d/%m/%Y %H:%M:%S")
      print(t)
      try:
        if((t > d1) and (t < d2)):
            print("Okay")
            print(s)
            try:
                print(s['car_number'], s['odometer'])
                # dict[s['car_number']] = s['odometer']
                dict1[s['car_number']] = s['odometer']
            except:
                print(s['car_number'], s['odometer'])
                log.append(s)
        elif((t > d3) and (t < d4)):
            dict2[s['car_number']] = s['odometer']
        else:
          print("Okaynodate")
          print(f"{t} > {d1} and {t} < {d2}")
      except TypeError:
        print("Nan")


  # print(dict)
  print("two dictionaries")
  print(dict1)
  print(dict2)

  dict1_result = {}
  dict2_result = {}
  d1_cars = []
  d2_cars = []
  # difference of two months data
  dict1 = {k.strip(): v for k, v in dict1.items()}
  for k, v in dict1.items():
    try:
      dict1_result[k.strip()] = int(v)
      d1_cars.append(k)
    except(ValueError):
      log_values.append([k, v, "2"])
  dict2 = {k.strip(): v for k, v in dict2.items()}
  for k, v in dict2.items():
    try:
      dict2_result[k.strip()] = int(v)
      d2_cars.append(k)
    except(ValueError):
      log_values.append([k, v, "1"])
  common_keys = set(dict1_result) & set(dict2_result)
  result_dict = {k: int(dict1_result[k]) - int(dict2_result[k]) for k in common_keys}
  print("result dictionary")
  print(result_dict)

  print(log)
  # current = list(dict.keys())
  difference_last = [i for i in cars if i not in d2_cars]
  difference_current = [i for i in cars if i not in d1_cars]
  # print(difference)
  # log_no_data_cars = difference

  print("has data")
  print(f"период с {d1} по {d2}")
  print(f"Получено от {d1_cars}")
  print(f"Нет данных по автомобилям {difference_current} (в период с {d1} по {d2})")
  print("")
  print("Номера авто не прилавших:")
  for car1 in difference_current:
    print(f"{car_numbers[car1]}, ")
  print("")
  log_no_data_cars.append(f"no data for {difference_current} (в период с {d1} по {d2})")
  print(f"период с {d3} по {d4}")
  print(f"Получено от {d2_cars}")
  print(f"Нет данных по автомобилям {difference_last} (в период с {d3} по {d4})")
  log_no_data_cars.append(f"no data for {difference_current} (в период с {d3} по {d4})")
  return result_dict

get_odometers()