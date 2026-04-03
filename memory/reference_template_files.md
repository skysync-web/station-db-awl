---
name: Key project files and references
description: Locations of template AWL, Excel reference, and utility scripts for the AWL generator project
type: reference
---

- `Source/db11.AWL` — Template AWL file (3419 lines), the structure source for all generated DBs
- `Source/Exported_Excel.xlsx` — Single sheet "DataBlock" with 1597 rows showing field names, types, initial values, and comments
- `Source/app.py` — Main application with GUI and AWL generation logic
- `Source/read_excel.py` — Utility to dump Excel contents for analysis
- `Source/check_syntax.py` — Python syntax checker for app.py
