# SOP-PT06-005: Conductivity Spike — Zinc Phosphate Tank (PT-06)

**Severity:** MEDIUM | **Tank:** PT-06 Zinc Phosphate | **Est. fix:** 20-30 mins | **Rev:** 1.7

## 1. Description

Conductivity spikes above 4200 uS/cm indicate excessive dissolved salt concentration, typically
from accumulated iron ions, fluoride buildup, or carry-over from inadequate rinsing in PT-04.
High conductivity accelerates acid drift and reduces bath stability. The sensor provides a
real-time indicator of overall bath ionic strength.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 2000-4000 | 4000-4200 | > 4200 uS/cm |
| free_acid_pts | 0.5-1.5 | 1.5-1.8 | > 1.8 |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Conductivity 4000-4200 | Partial bath dump 5%, refill DI water |
| Conductivity > 4200 | Dump 10%, refill + check PT-04 rinse quality |
| > 4500 not responding | SOP-PT06-REBUILD-001 |

## 5. Verification

1. Conductivity < 3800 uS/cm.
2. Check free acid — often elevated after conductivity spike.

## 7. Related SOPs

- SOP-PT06-001 (Acid Drift), SOP-PT04-001.

---
Document owner: Process Engineering - Paint Shop | Rev 1.7 | Next review: 2026-06-01
