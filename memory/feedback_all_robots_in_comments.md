---
name: Include all robot names in multi-robot comments
description: Multi-robot AWL comment fields must list ALL station robots, not just the first two
type: feedback
---

When generating comments for fields that reference multiple robots (AB _26-_28, Aux_Cycle _61-_62), always use ALL robot names joined together, not just the first two.

**Why:** User tested with 3 robots and found only the first 2 appeared. The code was hardcoded to `r1, r2 = robot_names[0], robot_names[1]`.

**How to apply:** Use `" ".join(robot_names)` or `"-".join(robot_names)` depending on the field pattern. Never hardcode robot count assumptions.
