---
name: AWL Generator Project Overview
description: Python tkinter app that generates Siemens Step7 v5.7 AWL files for Global DB blocks from a template (db11.AWL)
type: project
---

Building a Python tkinter GUI application that generates Siemens Step7 v5.7 AWL files for Global DB blocks.

**Why:** User needs to configure station DBs (DB11-DB30) by changing only the comment sections of a standard AWL template, while preserving exact field names, data types, array sizes, and initial values.

**How to apply:**
- Template file: `Source/db11.AWL` (3419 lines) — never modify structure, only comments
- AWL files must be Latin-1 encoded
- All auto-generated sections (O_I, AB, A_I, RQM, RQT, Aux_Cycle, Mem_Cycle, MG, TIO_D) must first be set to "RESERVE" then specific fields overwritten
- Station naming: 3-digit number + type (T/TT/LIFT/R) + 2-digit suffix
- Robot naming: must match `\d{3}R\d{2}` AND first 3 digits must match station number
- Valve islands: BM01/BM02, up to 10 valves per island, actuator types: Clamp, Shift Pin, Swivel Unit, Linear Unit
- YV naming format: `{island_num:02d}YV{valve_num:02d}` (e.g., 01YV01, 02YV01)
- Key sections with robot comments: AB(_24-_28), RQT(_22-_29), Aux_Cycle(_02,_03,_46,_47,_61,_62), Mem_Cycle(_17,_21,_25,_29), TIO_D(_11,_12)
- Multi-robot comments must include ALL robot names (joined with space or dash depending on field)
- App file: `Source/app.py` (~1351 lines)
