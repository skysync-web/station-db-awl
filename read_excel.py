import pandas as pd
import sys

path = r"C:\Users\HP\Desktop\Claude Workspace\Station DB AWL Generation\Source\Exported_Excel.xlsx"
xls = pd.ExcelFile(path)
print("Sheets:", xls.sheet_names)

for s in xls.sheet_names:
    df = pd.read_excel(xls, s, header=None)
    print(f"\n=== {s} (rows={len(df)}, cols={len(df.columns)}) ===")
    for i, row in df.iterrows():
        vals = [str(v) if pd.notna(v) else "" for v in row]
        line = " | ".join(vals)
        print(f"  {i}: {line}")
