# SOP-ED01-004: Solids Depletion — E-Coat Bath (ED-01)

**Severity:** HIGH | **Tank:** ED-01 E-Coat Bath | **Est. fix:** 35-55 mins | **Rev:** 2.9

## 1. Description

Bath solids (non-volatile matter) below 17% indicates paint resin depletion relative to carrier
solvent. This reduces film build per pass — at 15% solids, film thickness is 40% below target.
Solids depletion occurs through normal consumption and is accelerated by high throughput, UF
membrane losses, and temperature-induced precipitation. Replenishment is with ED paint paste.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| solids_pct | 18-22 % | 17-18 % | < 17 % |
| conductivity_us_cm | 1200-1800 | 1800-2000 | > 2000 |

## 3. Corrective Action

| Condition | Chemical | Dose |
|-----------|----------|------|
| Solids 17-18% | ED paint paste (Cathoguard 800) | 25 kg per 0.5% deficit per 10,000L |
| Solids < 17% | Cathoguard 800 + check UF losses | 50 kg per 10,000L |

## 5. Verification

1. Solids 19-21% by NVM oven test (2h at 105°C).
2. Film thickness 20-24 microns on first body.

## 6. Historical Data

- Total incidents: 6 | Avg resolution: 48 mins | Cost per incident: ~€6,200 (paint paste)

## 7. Related SOPs

- SOP-ED01-001 (Temperature), SOP-ED01-002 (MEq Acid).

---
Document owner: Process Engineering - Paint Shop | Rev 2.9 | Next review: 2026-04-15
