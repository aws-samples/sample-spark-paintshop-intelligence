# SOP-PT02-002: High Temperature — Main Cleaner Tank (PT-02)

**Severity:** MEDIUM | **Tank:** PT-02 Main Cleaner | **Est. fix:** 20-30 mins | **Rev:** 1.8

## 1. Description

PT-02 temperature exceeding 65°C causes excessive evaporation, concentrate breakdown and foaming.
High temperature can also cause partial saponification of lubricants that reforms as scale on
spray nozzles, reducing cleaning efficiency over time. Temperature excursions above 70°C risk
thermal denaturation of biocide additives requiring full bath replacement.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| temperature_c | 55-65°C | 65-68°C | > 68°C |
| ph | 11.5-12.5 | 12.5-12.8 | > 12.8 |

## 3. Immediate Actions

1. Switch heat exchanger to cooling mode immediately.
2. If temperature > 68°C, stop steam supply and open cold water bypass valve.
3. Do not dose chemicals while temperature is above spec — wait until below 65°C.

## 4. Corrective Action

| Condition | Action |
|-----------|--------|
| Temp 65-68°C | Switch HX to cooling, reduce steam valve to 20% |
| Temp > 68°C | Emergency cooling: open cold water bypass + reduce conveyor speed |
| Temp > 70°C | Halt production, check HX control valve malfunction |

## 5. Verification

1. Temperature stabilised at 57-63°C for 10 consecutive minutes.
2. No foaming observed in tank.
3. Check spray nozzle patterns — clear if foaming occurred.

## 6. Historical Data

- Total incidents: 4 | Avg resolution: 22 mins
- Root cause: Heat exchanger control valve failure (3/4)

## 7. Related SOPs

- HX control valve fault: SOP-PT02-HX-001.
- Post-temperature check alkalinity: SOP-PT02-001.

---
Document owner: Process Engineering - Paint Shop | Rev 1.8 | Next review: 2026-07-01
