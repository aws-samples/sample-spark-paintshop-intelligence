# SOP-ED02-003: Rinse Contamination — UF Rinse 1 (ED-02)

**Severity:** MEDIUM | **Tank:** ED-02 UF Rinse 1 | **Est. fix:** 30-45 mins | **Rev:** 2.0

## 1. Description

ED-02 is the first UF permeate rinse after the e-coat bath. It recovers drag-out paint from
bodies before the DI rinse stages. Contamination is indicated by conductivity above 2500 uS/cm
or solids exceeding the UF permeate spec, suggesting breakthrough from the e-coat bath or
reverse carry-over from ED-03. High conductivity in ED-02 causes insufficient paint recovery,
increasing bath loading and COD in wastewater. ML detects conductivity trend 12 minutes before
the 2500 uS/cm alarm.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 500-2000 | 2000-2500 | > 2500 |
| solids_pct | 1.0-5.0 % | 5.0-7.0 % | > 7.0 % |
| ph | 5.5-7.0 | 5.0-5.5 | < 5.0 |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Conductivity 2000-2500 | Increase UF permeate flow 15%, check ED-01 bath loading |
| Conductivity > 2500 | Partial dump 20% ED-02 volume, refill with fresh UF permeate |
| Solids > 7% | Check UF membrane integrity (SOP-ED02-001); initiate CIP if fouled |
| pH < 5.0 | Check for acid carry-over from ED-01; add DI water dilution |

## 4. Root Cause Investigation

1. Check UF membrane status — fouled membranes allow paint solids to pass into permeate.
2. Verify UF permeate flow rate — reduced flow reduces dilution capacity.
3. Inspect ED-01 bath loading — high throughput increases drag-out per body.
4. Check ED-03 level — overfill in ED-03 can cause reverse carry-over into ED-02.

## 5. Verification

1. Conductivity < 2000 uS/cm for 20 consecutive minutes.
2. Solids 1.5-4.0%, pH 5.5-7.0.
3. Check ED-03 for downstream impact — conductivity should remain < 800 uS/cm.

## 6. Historical Data

- Total incidents: 6 | Avg resolution: 40 mins
- Root cause: UF membrane fouling (4/6), ED-01 bath overload (2/6)

## 7. Related SOPs

- SOP-ED02-001 (Membrane Fouling), SOP-ED01-002 (MEq Acid Buildup).

---
Document owner: Process Engineering - Paint Shop | Rev 2.0 | Next review: 2026-06-01
