# SOP-PT02-001: Alkalinity Depletion — Main Cleaner Tank (PT-02)

**Severity:** HIGH | **Tank:** PT-02 Main Cleaner | **Est. fix:** 30-40 mins | **Rev:** 2.7

## 1. Description

The main cleaner (PT-02) is the primary degreasing stage for heavy soils. Alkalinity depletion
below 10.0 pts causes failure to saponify vegetable oils and insufficient emulsification of mineral
oils. Heavy-soil bodies processed through depleted PT-02 carry through to PT-06, causing bath
contamination and accelerated acid drift. This is a high-severity event requiring immediate action.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| free_alkalinity | 10.0-16.0 pts | 8.0-10.0 pts | < 8.0 pts |
| total_alkalinity | 14.0-22.0 pts | 12.0-14.0 pts | < 12.0 pts |
| ph | 11.5-12.5 | 11.0-11.5 | < 11.0 |
| temperature_c | 55-65°C | 52-55°C | < 52°C |

## 3. Immediate Actions (First 10 Minutes)

1. Halt body loading — PT-02 depletion has downstream cascade risk. Notify shift supervisor.
2. Titrate free and total alkalinity immediately.
3. Check skimmer operation — floating oil layer accelerates alkalinity consumption.

## 4. Corrective Chemical Dosing

| Condition | Chemical | Dose | Method |
|-----------|----------|------|--------|
| Free alk 8-10 pts | Ridoline 1573 concentrate | 3L per 1000L | Circulate 15 mins |
| Free alk < 8 pts | Ridoline 1573 + caustic soda | 4L + 1.5L per 1000L | Caustic first, then Ridoline |
| Oil content visible | Activate overflow skimmer | — | Run skimmer 20 mins before dosing |

## 5. Verification

1. Free alkalinity 11-14 pts, total alkalinity 16-20 pts.
2. No visible oil sheen on surface.
3. Spray nozzle pressure at target 1.2-1.8 bar.

## 6. Historical Data (Last 12 Months)

- Total incidents: 9 | Avg resolution: 35 mins | Bodies recycled: 22
- JPH impact: -12 JPH | FBO impact: 25-40 mins

## 7. Related SOPs

- After PT-02 fault, inspect PT-06 acid levels: SOP-PT06-001.
- Skimmer fault: SOP-PT02-SKIM-001.

---
Document owner: Process Engineering - Paint Shop | Rev 2.7 | Next review: 2026-04-15
