# SOP-ED03-002: Rinse Contamination — UF Rinse 2 (ED-03)

**Severity:** MEDIUM | **Tank:** ED-03 UF Rinse 2 | **Est. fix:** 25-40 mins | **Rev:** 2.0

## 1. Description

ED-03 is the second UF permeate rinse stage. It provides a cleaner dilution than ED-02 and
bridges toward the final DI rinse (ED-04). Contamination above 800 uS/cm indicates carry-over
from ED-02 or UF permeate quality degradation. Elevated conductivity in ED-03 directly degrades
ED-04 DI water quality and increases ion load on the DI resin beds, shortening resin life.
ML detects conductivity trend 10 minutes before the 800 uS/cm alarm.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 200-800 | 800-1200 | > 1200 |
| solids_pct | 0.2-1.5 % | 1.5-2.5 % | > 2.5 % |
| ph | 5.5-7.0 | 5.0-5.5 | < 5.0 |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Conductivity 800-1200 | Increase fresh UF permeate supply to ED-03 by 20% |
| Conductivity > 1200 | Dump 30% ED-03 volume, refill with fresh UF permeate; check ED-02 |
| Solids > 2.5% | Inspect UF permeate source — check ED-02 status (SOP-ED02-003) |
| pH < 5.0 | Trace to ED-02; dilute with DI water 10% |

## 4. Root Cause Investigation

1. Check ED-02 conductivity — ED-03 contamination is almost always upstream in ED-02.
2. Verify UF system differential pressure — rising dp indicates membrane fouling.
3. Check production rate — high throughput increases carry-over from bath.
4. Inspect cascade overflow valve between ED-02 and ED-03 — blockage restricts dilution flow.

## 5. Verification

1. Conductivity < 700 uS/cm for 20 consecutive minutes.
2. Solids < 1.0%, pH 5.5-7.0.
3. Confirm ED-04 conductivity remains < 20 uS/cm — no downstream impact.

## 6. Historical Data

- Total incidents: 4 | Avg resolution: 35 mins
- Root cause: ED-02 carry-over (3/4), UF permeate degradation (1/4)

## 7. Related SOPs

- SOP-ED02-003 (ED-02 Rinse Contamination), SOP-ED04-001 (Conductivity Spike — ED-04).

---
Document owner: Process Engineering - Paint Shop | Rev 2.0 | Next review: 2026-06-01
