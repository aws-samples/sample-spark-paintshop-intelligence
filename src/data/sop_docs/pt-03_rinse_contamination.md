# SOP-PT03-001: Rinse Contamination — First Rinse Tank (PT-03)

**Severity:** MEDIUM | **Tank:** PT-03 Rinse 1 | **Est. fix:** 15-25 mins | **Rev:** 2.1

## 1. Description

Contamination of the first rinse is indicated by rising conductivity above 100 uS/cm, signalling
carry-over of alkaline cleaner from PT-02. Contaminated rinse fails to remove residual cleaning
chemicals, which then interfere with the activation step in PT-05. Titanium activation is strongly
inhibited by alkaline cleaner residues above 50 ppm. Downstream effect: coarse phosphate crystals,
reduced coating weight in PT-06.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 20-100 | 100-200 | > 200 uS/cm |
| ph | 6.5-8.5 | 8.5-9.5 | > 9.5 |
| rinse_flow | 8.0-15.0 L/min | 6.0-8.0 | < 6.0 |

## 3. Immediate Actions

1. Increase fresh water flow to maximum (cascade rinse mode).
2. Check PT-02 spray nozzle pressure — excessive carry-over often due to nozzle blockage causing flooding.
3. Verify PT-03 overflow drain is open and flowing.

## 4. Corrective Action

| Condition | Action | Duration |
|-----------|--------|----------|
| Conductivity 100-200 | Increase flow rate to 15 L/min | Until conductivity < 80 |
| Conductivity > 200 | Full dump and refill with fresh DI water | 20 mins |
| Rinse flow < 6 | Check and clear flow control valve | Maintenance call |

## 5. Verification

1. Conductivity < 80 uS/cm, pH 6.8-7.5.
2. Check PT-05 titanium reading — should not drop below 0.8 ppm.

## 6. Historical Data

- Total incidents: 18 | Avg resolution: 18 mins
- JPH impact: -5 JPH

## 7. Related SOPs

- If PT-05 titanium affected: SOP-PT05-001.
- Flow control fault: SOP-PT03-FLOW-001.

---
Document owner: Process Engineering - Paint Shop | Rev 2.1 | Next review: 2026-05-01
