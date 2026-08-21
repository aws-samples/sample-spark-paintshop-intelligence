# SOP-ED01-003: pH Drift — E-Coat Bath (ED-01)

**Severity:** HIGH | **Tank:** ED-01 E-Coat Bath | **Est. fix:** 30-45 mins | **Rev:** 3.0

## 1. Description

E-coat bath pH must be held at 5.8-6.2 for proper paint solubilisation and film deposition.
pH below 5.6 causes excessive film roughness and decreased throw power into recessed areas.
pH above 6.4 causes over-solubilisation, reducing film build and causing sagging defects.
pH drift is usually secondary to MEq acid buildup (low pH) or amine overdose (high pH).

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| ph | 5.8-6.2 | 5.6-5.8 or 6.2-6.5 | < 5.6 or > 6.5 |
| meq_acid | 18-32 | 32-36 | > 36 |
| solids_pct | 18-22 % | 17-18 | < 17 |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| pH < 5.6 | Investigate MEq acid (SOP-ED01-002), add DMEA amine 150mL per 10,000L |
| pH 5.6-5.8 | Add DMEA 80mL per 10,000L, monitor |
| pH > 6.5 | No amine addition, increase UF permeate withdrawal |
| pH 6.2-6.5 | Increase UF permeate 20% |

## 5. Verification

1. pH 5.85-6.15 for 20 consecutive minutes.
2. Film test on coupon — film thickness 20-22 microns, gloss normal.

## 6. Historical Data

- Total incidents: 7 | Avg resolution: 35 mins
- Root cause: MEq acid cascade (5/7), amine dosing error (2/7)

## 7. Related SOPs

- SOP-ED01-002 (MEq Acid), SOP-ED01-004 (Solids Depletion).

---
Document owner: Process Engineering - Paint Shop | Rev 3.0 | Next review: 2026-04-01
