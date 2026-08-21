# SOP-PT06-006: Temperature Deviation — Zinc Phosphate Tank (PT-06)

**Severity:** MEDIUM | **Tank:** PT-06 Zinc Phosphate | **Est. fix:** 20-35 mins | **Rev:** 2.0

## 1. Description

PT-06 temperature must be held at 40-50°C for optimal phosphating kinetics. Low temperature
(< 40°C) slows reaction rate, causing thin coating and extended process time. High temperature
(> 50°C) accelerates acid consumption, promotes sludge formation and increases free acid drift
risk. Both deviations affect phosphate crystal structure and coating quality.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| temperature_c | 40-50°C | 38-40°C or 50-53°C | < 38°C or > 53°C |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Temp < 38°C | Switch to heat mode, increase steam, reduce conveyor speed 10% |
| Temp > 53°C | Emergency cooling, check HX bypass valve |
| Temp variation > 3°C within hour | Investigate HX cycling — possible valve fault |

## 5. Verification

1. Temperature 43-47°C stable for 10 mins.
2. Check acid levels — temperature changes affect acid equilibrium.

## 7. Related SOPs

- Temperature low + acid high: SOP-PT06-001.
- HX fault: SOP-PT06-HX-001.

---
Document owner: Process Engineering - Paint Shop | Rev 2.0 | Next review: 2026-08-01
