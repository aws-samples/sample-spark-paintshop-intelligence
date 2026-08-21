# SOP-PT08-001: Passivation Failure — Nano-Seal Tank (PT-08)

**Severity:** HIGH | **Tank:** PT-08 Nano-Seal | **Est. fix:** 35-50 mins | **Rev:** 2.8

## 1. Description

The nano-seal (zirconic acid passivation) forms a conversion coating that bridges phosphate
and primer, providing corrosion inhibition and promoting e-coat adhesion. Passivation failure
is indicated by pH drift outside 4.0-5.0 or concentration below 0.3%, causing incomplete
conversion coating. Bodies with failed passivation exhibit adhesion loss in salt spray testing
within 500h (spec is > 1000h). This is a critical-quality gate fault.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| ph | 4.0-5.0 | 5.0-5.5 or 3.7-4.0 | > 5.5 or < 3.7 |
| concentration_pct | 0.3-1.2 % | 0.25-0.3 % | < 0.25 % |
| temperature_c | 25-35°C | 35-40°C | > 40°C |

## 3. Immediate Actions

1. Halt body loading — passivation failure bodies cannot be easily reworked.
2. Titrate concentration with conductimetric method or Spectroquant zirconium test.
3. Check pH probe calibration — passivation bath is aggressive to probes.

## 4. Corrective Chemical Dosing

| Condition | Chemical | Dose |
|-----------|----------|------|
| Concentration < 0.3% | Bonderite NT-1 concentrate | 2L per 10,000L per 0.1% deficit |
| pH > 5.0 | Fluoboric acid 40% | 100mL per 10,000L, re-check after 10 mins |
| pH < 3.7 | Ammonium carbonate 10% | 200mL per 10,000L |

## 5. Verification

1. pH 4.2-4.8, concentration 0.4-0.8%.
2. Adhesion tape test on nano-sealed coupon — crosshatch score GT0/GT1.
3. Check e-coat adhesion test panel (if available from previous run).

## 6. Historical Data

- Total incidents: 3 | Avg resolution: 45 mins | Bodies quarantined: 28
- Root cause: pH probe drift (2/3), concentration rundown (1/3)
- Cost per incident: ~€5,200 (adhesion test failure + quarantine)

## 7. Related SOPs

- pH probe drift: SOP-PT08-SENSOR-001.
- Temperature > 40°C: check HX (SOP-PT08-HX-001).

---
Document owner: Process Engineering - Paint Shop | Rev 2.8 | Next review: 2026-02-15
