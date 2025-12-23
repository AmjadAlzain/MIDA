import pandas as pd

excel_path = 'EXEMPTION MIDA FOR 755 NEW.xlsx'
excel_file = pd.ExcelFile(excel_path)
sheet = excel_file.sheet_names[0]
df = pd.read_excel(excel_file, sheet_name=sheet, header=None, nrows=15)

print(f"Sheet: {sheet}")
print("Row 12 (index 12):")
print(df.iloc[12].tolist())
print("Row 13 (index 13):")
print(df.iloc[13].tolist())
