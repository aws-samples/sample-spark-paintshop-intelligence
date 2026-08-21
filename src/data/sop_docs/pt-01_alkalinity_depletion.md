# SOP-PT01-001: Alkalinity Depletion — Hot Pre-Clean Tank (PT-01)

**Severity:** MEDIUM | **Tank:** PT-01 Hot Pre-Clean | **Est. fix:** 25-35 mins | **Rev:** 2.4

## 1. Description

Alkalinity depletion in the hot pre-clean tank occurs when free alkalinity drops below 8.0 points,
reducing cleaning efficiency. Insufficient cleaning leaves residual oils, stamping lubricants and
metal fines on the body surface. Downstream zinc phosphate quality is critically dependent on
complete soil removal — inadequate cleaning causes crystal irregularities in PT-06 and adhesion
failures in the e-coat layer. Contaminated bodies must be recycled through PT-01.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| free_alkalinity | 8.0-14.0 pts | 6.0-8.0 pts | < 6.0 pts |
| ph | 11.0-12.0 | 10.5-11.0 | < 10.5 |
| temperature_c | 50-60°C | 47-50°C | < 47°C |
| conductivity_us_cm | 5000-12000 | 4500-5000 | < 4500 |

## 3. Immediate Actions (First 10 Minutes)

1. Reduce conveyor speed by 20% to extend PT-01 dwell time while replenishing.
2. Take manual Titrett alkalinity sample — draw 10mL, titrate with 0.1N HCl to pH 8.3 endpoint.
3. Check bath temperature — if below 50°C, verify heat exchanger operation before dosing.

## 4. Corrective Chemical Dosing

| Condition | Chemical | Dose | Method |
|-----------|----------|------|--------|
| Free alk 6-8 pts | Alkaline cleaner concentrate (Ridoline 265) | 2L per 1000L bath | Add direct, circulate 10 mins |
| Free alk < 6 pts | Ridoline 265 + sodium hydroxide 50% | 3L + 1L per 1000L | Add separately, 5 min apart |

## 5. Verification Before Resuming Normal Speed

1. Re-titrate: free alkalinity 9-12 pts, pH 11.2-11.8.
2. Conduct break water test on steel coupon — water must sheet off uniformly (no beading).
3. ML score below 0.25 for 5 consecutive readings.

## 6. Historical Data (Last 12 Months)

- Total incidents: 12 | Avg resolution: 28 mins | Bodies recycled: 18
- Most common root cause: High soil load (weekend restart, 8/12)
- JPH impact: -8 JPH | FBO impact: 20-30 mins

## 7. Related SOPs

- pH < 10.5 with correct alkalinity: SOP-PT01-SENSOR-001 (pH Probe Calibration).
- Temperature < 47°C: SOP-PT01-HX-001 (Heat Exchanger Fault).

---
Document owner: Process Engineering - Paint Shop | Rev 2.4 | Next review: 2026-06-01
