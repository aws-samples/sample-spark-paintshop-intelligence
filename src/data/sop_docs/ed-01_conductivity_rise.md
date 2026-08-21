# SOP-ED01-005: Conductivity Rise — E-Coat Bath (ED-01)

**Severity:** MEDIUM | **Tank:** ED-01 E-Coat Bath | **Est. fix:** 25-35 mins | **Rev:** 2.3

## 1. Description

Conductivity above 1800 uS/cm in the e-coat bath indicates ionic contamination from metal
ions (Zn, Fe, Mn) carrying over from PT-07, or electrolyte buildup from the electrodeposition
process. High conductivity reduces current efficiency, increases energy consumption and causes
film defects. UF permeate removal is the primary control.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 1200-1800 | 1800-2000 | > 2000 uS/cm |
| ph | 5.8-6.2 | | |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Conductivity 1800-2000 | Increase UF permeate 30%, add DI water makeup |
| Conductivity > 2000 | Halt, check UF, add DI water 5% bath volume |

## 5. Verification

1. Conductivity < 1700 uS/cm.
2. Rectifier amperage at normal levels.

## 7. Related SOPs

- SOP-ED-UF-001, SOP-PT07-001 (upstream contamination source).

---
Document owner: Process Engineering - Paint Shop | Rev 2.3 | Next review: 2026-05-01
