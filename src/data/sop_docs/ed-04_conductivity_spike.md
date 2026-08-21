# SOP-ED04-002: Conductivity Spike — Final DI Rinse (ED-04)

**Severity:** MEDIUM | **Tank:** ED-04 DI Final Rinse | **Est. fix:** 20-30 mins | **Rev:** 1.8

## 1. Description

Sudden conductivity spikes (> 5 uS/cm increase within 10 minutes) in ED-04 differ from gradual
resin exhaustion (SOP-ED04-001). Spikes indicate bypass of the DI resin bed, sudden
contamination from ED-03 carry-over, or a cracked resin cartridge letting through untreated
water. Spikes are detected by ML 5-8 minutes before they exceed the 20 uS/cm warning threshold.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 1-20 | 20-30 | > 30 uS/cm |

Rate-of-change alarm: > 5 uS/cm per 10 minutes triggers investigation.

## 3. Immediate Actions

1. Check DI bypass valve position — should be fully closed.
2. Inspect resin cartridge housing for cracks or seal failure.
3. Check ED-03 rinse conductivity — if elevated, source is upstream carry-over.

## 4. Corrective Action

| Condition | Action |
|-----------|--------|
| Bypass valve fault | Close valve, verify seal, call maintenance |
| Cartridge crack | Emergency replacement (SOP-ED04-001 procedure) |
| Carry-over from ED-03 | SOP-ED03-001 |

## 5. Verification

1. Conductivity < 12 uS/cm with no rate-of-change trend.
2. Confirm source of spike resolved — do not resume production if source unknown.

## 7. Related SOPs

- SOP-ED04-001 (DI Resin Exhaustion), SOP-ED03-001.

---
Document owner: Process Engineering - Paint Shop | Rev 1.8 | Next review: 2026-08-01
