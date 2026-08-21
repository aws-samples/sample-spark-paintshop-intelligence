# SOP-ED01-002: MEq Acid Buildup — E-Coat Bath (ED-01)

**Severity:** HIGH | **Tank:** ED-01 E-Coat Bath | **Est. fix:** 40-55 mins | **Rev:** 3.1

## 1. Description

Milliequivalent acid (MEq acid) rises due to electrochemical acid generation during ED coating.
Above 35 MEq/kg, the bath becomes too acidic for proper resin neutralisation, causing film
roughness, loss of gloss, and blistering. MEq acid above 40 causes electrolyte concentration
imbalance that permanently destabilises the bath chemistry. Ultrafiltration (UF) permeate
removal is the primary control mechanism — UF malfunction is the most common root cause.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| meq_acid | 18-32 MEq/kg | 32-36 MEq/kg | > 36 MEq/kg |
| ph | 5.8-6.2 | 5.6-5.8 | < 5.6 |
| conductivity_us_cm | 1200-1800 | 1800-2000 | > 2000 |
| solids_pct | 18-22 % | 17-18 | < 17 |

## 3. Immediate Actions

1. Check UF system status — verify permeate flow rate > 200 L/hr.
2. If UF is normal, increase permeate withdrawal rate.
3. If UF has low flow, call maintenance (SOP-ED-UF-001).
4. Reduce voltage by 10% to slow acid generation rate.

## 4. Corrective Action

| Condition | Action |
|-----------|--------|
| MEq 32-36 | Double UF permeate rate + add amine neutraliser (DMEA) 200mL per 10,000L |
| MEq > 36 | Halt production, UF maximum, amine 400mL per 10,000L |
| MEq > 40 | Emergency bath dump 15% + deionised water replacement |

## 5. Verification

1. MEq acid 22-28 MEq/kg.
2. pH 5.9-6.1.
3. Film test — gloss > 85 GU at 60° angle, Ra < 0.5 microns.

## 6. Historical Data

- Total incidents: 4 | Avg resolution: 48 mins | Bodies quarantined: 19
- Root cause: UF membrane fouling (3/4), excessive amine loss (1/4)
- Cost per incident: ~€3,700

## 7. Related SOPs

- UF malfunction: SOP-ED-UF-001.
- pH follow-up: SOP-ED01-003.

---
Document owner: Process Engineering - Paint Shop | Rev 3.1 | Next review: 2026-03-15
