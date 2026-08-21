# SOP-ED04-003: Rinse Contamination — DI Water Final Rinse (ED-04)

**Severity:** HIGH | **Tank:** ED-04 DI Water Final Rinse | **Est. fix:** 30-50 mins | **Rev:** 2.2

## 1. Description

ED-04 is the final DI water rinse before e-coated bodies enter the oven. Conductivity must
remain below 20 uS/cm to prevent residual ions from causing finish defects (popping, cratering,
adhesion loss) during baking. Contamination above 20 uS/cm indicates DI resin exhaustion,
upstream carry-over from ED-03, or DI water supply failure. This is the last quality gate before
the oven — bodies that pass through contaminated ED-04 cannot be reworked after baking.
ML detects conductivity rise 8 minutes before the 20 uS/cm alarm threshold.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 1-20 | 20-50 | > 50 uS/cm |
| ph | 5.5-7.5 | 5.0-5.5 or 7.5-8.0 | < 5.0 or > 8.0 |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Conductivity 20-50 | Halt body loading; check DI resin status (SOP-ED04-002) |
| Conductivity > 50 | Halt body loading immediately; check ED-03 carry-over AND resin |
| DI resin OK | Source is upstream — investigate ED-03 (SOP-ED03-002) |
| DI resin exhausted | Replace resin (SOP-ED04-002, 4h process); divert bodies to hold area |
| pH outside 5.0-8.0 | Resin is contaminated or bypassed; replace immediately |

## 4. Root Cause Investigation

1. **Check DI resin conductivity first** — most common cause. Resin exhaustion causes sudden
   conductivity step-change rather than gradual drift.
2. Check ED-03 conductivity — gradual contamination drift usually traces to ED-03 carry-over.
3. Verify DI water supply header pressure — low pressure reduces dilution flow through resin beds.
4. Inspect inlet solenoid valves — stuck-open valve can allow un-deionised tap water bypass.

## 5. Verification

1. Conductivity < 15 uS/cm for 30 consecutive minutes (strict — this is the final gate).
2. pH 6.0-7.0.
3. Inspect 3 bodies from first post-clearance batch for surface defects before resuming full production.

## 6. Historical Data

- Total incidents: 8 | Avg resolution: 42 mins (excl. resin replacement)
- Root cause: DI resin exhaustion (5/8), ED-03 carry-over (3/8)
- Bodies quarantined due to contamination: 14 total

## 7. Related SOPs

- SOP-ED04-002 (DI Resin Exhaustion), SOP-ED03-002 (ED-03 Rinse Contamination).

---
Document owner: Process Engineering - Paint Shop | Rev 2.2 | Next review: 2026-06-01
