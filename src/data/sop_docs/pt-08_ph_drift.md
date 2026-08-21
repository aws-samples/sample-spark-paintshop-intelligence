# SOP-PT08-003: pH Drift — Nano-Seal Tank (PT-08)

**Severity:** HIGH | **Tank:** PT-08 Nano-Seal | **Est. fix:** 30-45 mins | **Rev:** 2.1

## 1. Description

PT-08 nano-seal bath must be maintained at pH 4.0-5.0 for effective zirconic acid conversion
coating. pH drift above 5.5 indicates bath dilution or alkaline drag-in from PT-07, causing
incomplete passivation and reduced corrosion resistance. pH drift below 3.7 indicates acid
overdose or loss of buffer capacity. Either condition compromises e-coat adhesion at the
downstream PT-08 → ED-01 interface. ML detects pH trend 10 minutes before alarm threshold.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| ph | 4.0-5.0 | 5.0-5.5 or 3.7-4.0 | > 5.5 or < 3.7 |
| concentration_pct | 0.3-1.2 % | 0.25-0.3 % | < 0.25 % |
| temperature_c | 25-35°C | 35-40°C | > 40°C |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| pH 5.0-5.5 | Add fluoboric acid 40%: 80mL per 10,000L, wait 5 mins, re-check |
| pH > 5.5 | Add fluoboric acid 40%: 150mL per 10,000L; inspect PT-07 for alkaline carry-over |
| pH 3.7-4.0 | Add ammonium carbonate 10%: 100mL per 10,000L, monitor |
| pH < 3.7 | Add ammonium carbonate 10%: 200mL per 10,000L; check dosing pump for runaway |
| Concentration also low | Dose Bonderite NT-1 per SOP-PT08-001 simultaneously |

## 4. Root Cause Investigation

1. Check PT-07 conductivity — alkaline drag-in from contaminated PT-07 rinse raises PT-08 pH.
2. Check dosing pump calibration — fluoboric acid pump over-stroke lowers pH.
3. Inspect pH probe — nano-seal bath is aggressive; probe fouling causes false-high readings.
4. Verify bath age — bath older than 90 days tends to lose buffer capacity.

## 5. Verification

1. pH 4.2-4.8 for 15 consecutive minutes.
2. Concentration 0.4-0.8% confirmed by titration.
3. Adhesion tape test on test coupon — crosshatch score GT0/GT1.

## 6. Historical Data

- Total incidents: 5 | Avg resolution: 38 mins
- Root cause: PT-07 alkaline carry-over (3/5), dosing pump calibration (2/5)

## 7. Related SOPs

- SOP-PT08-001 (Passivation Failure), SOP-PT07-002 (PT-07 Rinse Contamination).

---
Document owner: Process Engineering - Paint Shop | Rev 2.1 | Next review: 2026-06-01
