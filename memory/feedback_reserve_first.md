---
name: RESERVE-first pattern for AWL generation
description: All auto-generated AWL sections must default to RESERVE before overwriting specific comments
type: feedback
---

All auto-generated sections must first set every comment to "RESERVE", then overwrite only the necessary fields.

**Why:** User caught that generated AWL files had stale/missing comments in fields that should have been blank. The RESERVE-first approach ensures no leftover data leaks through.

**How to apply:** Every `auto_gen_*()` function must call `make_reserve_dict()` at the start before setting any specific comments. Sections: O_I, AB, A_I, RQM, RQT, Aux_Cycle, Mem_Cycle, MG, TIO_D.
