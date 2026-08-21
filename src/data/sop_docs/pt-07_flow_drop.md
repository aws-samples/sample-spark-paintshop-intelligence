# SOP-PT07-002: Flow Drop — Post-Phosphate Rinse (PT-07)

**Severity:** LOW | **Tank:** PT-07 Post-Rinse | **Est. fix:** 15-25 mins | **Rev:** 1.5

## 1. Description

Reduced flow rate in PT-07 below 6 L/min decreases the rinsing efficiency, equivalent to
increasing conductivity contamination. Flow drops are typically caused by blocked spray nozzles
from phosphate scale, control valve restriction, or pump degradation.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| rinse_flow | 8.0-15.0 L/min | 6.0-8.0 | < 6.0 |
| conductivity_us_cm | 50-200 | 200-400 | > 400 |

## 3. Corrective Action

1. Check and clear spray nozzles — phosphate scale common, use 5% HCl flush.
2. Verify flow control valve position (should be >70% open at target flow).
3. If pump: check pressure gauge — pump degradation shows as flow drop with normal pressure.

## 5. Verification

1. Flow > 9 L/min, conductivity trending down.

## 7. Related SOPs

- Conductivity elevated: SOP-PT07-001.

---
Document owner: Process Engineering - Paint Shop | Rev 1.5 | Next review: 2026-09-01
