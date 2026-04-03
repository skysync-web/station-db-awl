---
name: Robot name must match station prefix
description: Robot name validation must check that first 3 digits match the station number
type: feedback
---

Robot names must not only match the pattern `\d{3}R\d{2}` but the first 3 digits must equal the station's 3-digit number.

**Why:** User found that entering "035R01" was accepted for station "040". Cross-validation between station and robot config is required.

**How to apply:** In `_validate_robot_name()`, after regex match, check `name[:3] == station_prefix`. Show specific error "Must start with {station_prefix}" if mismatch.
