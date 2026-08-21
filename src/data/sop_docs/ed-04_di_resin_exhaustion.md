# SOP-ED04-001: DI Resin Exhaustion — Final DI Rinse (ED-04)

**Severity:** MEDIUM | **Tank:** ED-04 DI Water Final Rinse | **Est. fix:** 30-45 mins | **Rev:** 2.4

## 1. Description

The final DI water rinse removes all ionic contamination before curing. Resin exhaustion is
indicated by conductivity rising above 20 uS/cm. At > 50 uS/cm, ionic contamination on the
e-coat surface survives the oven cure and creates osmotic blistering during corrosion exposure.
Bodies processed at > 30 uS/cm must be quarantined for adhesion testing. Resin cartridge
replacement is required — typical life is 400,000 litres.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 1-20 | 20-30 | > 30 uS/cm |
| ph | 5.5-7.5 | 7.5-8.0 | > 8.0 |

## 3. Immediate Actions

1. Check DI resin bed conductivity at inlet and outlet — > 5 uS/cm delta indicates exhaustion.
2. Switch to standby DI resin cartridge (if available).
3. If no standby, order emergency resin replacement — 4h lead time.

## 4. Corrective Action

| Condition | Action |
|-----------|--------|
| Conductivity 20-30 | Switch to standby DI cartridge |
| Conductivity > 30 | Halt production, mandatory cartridge replacement |
| Conductivity > 50 | Quarantine all bodies since last reading < 20 uS/cm |

## 5. Verification

1. Conductivity < 15 uS/cm.
2. pH 6.0-7.0.
3. Check standing water on body after rinse — should sheet off with no visible contamination.

## 6. Historical Data

- Total incidents: 5 | Avg resolution: 38 mins | Bodies quarantined: 15
- Cartridge life average: 410,000L | Replacement cost: €1,800
- JPH impact: -15 JPH during halt

## 7. Related SOPs

- Emergency resin order: SOP-ED04-RESIN-ORDER.
- Post-replacement flush: SOP-ED04-FLUSH-001.

---
Document owner: Process Engineering - Paint Shop | Rev 2.4 | Next review: 2026-03-15
