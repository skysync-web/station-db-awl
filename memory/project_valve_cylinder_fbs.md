---
name: Valve Cylinder FB structure
description: FB assignments for valve cylinders - CYL1, CYL2_5 (Valve_Cylinder_2_5), CYL6_9 (FB239 Valve_Cylinder_6_9)
type: project
---

Valve cylinder FBs in FB_OUTPUT generation:
- **CYL1** ("Valve_Cylinder_1"): always generated for every valve, handles the first unit/cylinder
- **CYL2_5** ("Valve_Cylinder_2_5"): generated when valve has >1 unit, handles units 2-5 (letters B-E)
- **CYL6_9** (FB239, "Valve_Cylinder_6_9"): generated when valve has >5 units, handles units 6-9 (letters F-I)

**Why:** User confirmed that stations can have valves with more than 5 actuators, requiring a third FB call.

**How to apply:** In `generate_fb_output()`, when `len(units) > 5`, declare CYL6_9 instance and generate its MANAGEMENT/CALL section after CYL2_5. TIO_D slots for CYL6_9 start after CYL2_5 slots. Visu suffix for CYL6_9 uses `ext_{n}B` (vs CYL2_5 uses `ext_{n}A`).
