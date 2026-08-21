# SOP-PT07-001: Rinse Contamination — Post-Phosphate Rinse (PT-07)

**Severity:** MEDIUM | **Tank:** PT-07 Post-Rinse | **Est. fix:** 15-20 mins | **Rev:** 2.3

## 1. Description

PT-07 is the post-phosphate rinse that removes residual phosphate bath chemicals before the
passivation (nano-seal) step. Contamination above 200 uS/cm indicates phosphate carry-over
which interferes with nano-seal adhesion in PT-08. Phosphate residues under the nano-seal
cause adhesion blistering in service. ML detects conductivity trend 15 minutes before alarm.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 50-200 | 200-400 | > 400 uS/cm |
| ph | 6.0-8.0 | 5.5-6.0 or 8.0-9.0 | < 5.5 or > 9.0 |
| rinse_flow | 8.0-15.0 L/min | 6.0-8.0 | < 6.0 |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Conductivity 200-400 | Increase flow to maximum, check PT-06 drag-out |
| Conductivity > 400 | Partial dump 25%, DI refill, check spray nozzle coverage |

## 5. Verification

1. Conductivity < 180 uS/cm, pH 6.5-7.5.
2. Check PT-08 nano-seal pH — should not be affected.

## 7. Related SOPs

- SOP-PT08-001 (Passivation Failure) if PT-07 contamination prolonged.
- Flow fault: SOP-PT07-FLOW-001.

---
Document owner: Process Engineering - Paint Shop | Rev 2.3 | Next review: 2026-05-15
