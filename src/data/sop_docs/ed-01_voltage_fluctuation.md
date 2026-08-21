# SOP-ED01-007: Voltage Fluctuation — E-Coat Bath (ED-01)

**Severity:** MEDIUM | **Tank:** ED-01 E-Coat Bath | **Est. fix:** 20-35 mins | **Rev:** 2.0

## 1. Description

Voltage fluctuation outside 200-350V range affects film thickness uniformity and throwing power.
Low voltage (< 180V) causes under-deposition — thin film in recessed areas. High voltage (> 380V)
causes film rupture (craters), pinholes and substrate damage on sharp edges. Voltage regulation
is performed by the rectifier system; fluctuations indicate rectifier fault or bath conductivity
change.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| voltage_v | 200-350 V | 180-200 or 350-380 V | < 180 or > 380 V |
| conductivity_us_cm | 1200-1800 | | |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Voltage < 180V | Check rectifier set-point, check bath conductivity |
| Voltage > 380V | Reduce rectifier output, check for conductivity drop |
| Unstable ±20V | Rectifier maintenance call (SOP-ED01-RECT-001) |

## 5. Verification

1. Voltage stable ±10V from set-point for 15 minutes.
2. Film thickness check on first post-correction body.

## 7. Related SOPs

- SOP-ED01-RECT-001 (Rectifier Maintenance), SOP-ED01-005 (Conductivity).

---
Document owner: Process Engineering - Paint Shop | Rev 2.0 | Next review: 2026-08-01
