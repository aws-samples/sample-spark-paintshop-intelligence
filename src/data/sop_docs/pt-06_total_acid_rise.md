# SOP-PT06-004: Total Acid Rise — Zinc Phosphate Tank (PT-06)

**Severity:** MEDIUM | **Tank:** PT-06 Zinc Phosphate | **Est. fix:** 30-40 mins | **Rev:** 2.2

## 1. Description

Total acid above 26 points indicates accumulation of iron phosphate by-products and phosphoric
acid concentration. Total acid rise degrades bath efficiency and is a leading indicator of
imminent free acid drift. Iron loading from high-throughput periods is the most common cause.
ML correlation shows total acid rise precedes free acid alarm by 35-60 minutes.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| total_acid_pts | 18-24 | 24-26 | > 26 pts |
| free_acid_pts | 0.5-1.5 | 1.5-1.8 | > 1.8 |
| conductivity_us_cm | 2000-4000 | 4000-4200 | > 4200 |

## 3. Immediate Actions

1. Increase sludge withdrawal rate — open sludge purge valve to lower iron phosphate load.
2. Check free acid simultaneously — if already at warning level, treat SOP-PT06-001 first.
3. Partial bath dump if total acid > 28 pts.

## 4. Corrective Action

| Condition | Action |
|-----------|--------|
| Total acid 24-26 | Increase sludge purge + add fresh replenisher to dilute |
| Total acid > 26 | Partial dump 8% + refill with fresh make-up water + replenisher |
| Iron > 3 g/L (ICP) | Bath dump and rebuild (SOP-PT06-REBUILD-001) |

## 5. Verification

1. Total acid 19-23 pts.
2. Check free acid — confirm not elevated after bath adjustment.

## 6. Historical Data

- Total incidents: 6 | Avg resolution: 35 mins
- JPH impact: -10 JPH

## 7. Related SOPs

- SOP-PT06-001 (Free Acid Drift), SOP-PT06-SLUDGE-001.

---
Document owner: Process Engineering - Paint Shop | Rev 2.2 | Next review: 2026-07-01
