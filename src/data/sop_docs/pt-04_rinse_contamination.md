# SOP-PT04-001: Rinse Contamination — Second Rinse Tank (PT-04)

**Severity:** MEDIUM | **Tank:** PT-04 Rinse 2 | **Est. fix:** 15-25 mins | **Rev:** 2.0

## 1. Description

PT-04 second rinse contamination from PT-03 carryover raises conductivity above 80 uS/cm. PT-04
serves as the final buffer before activation, and must deliver clean, near-neutral water. Residual
alkalinity entering PT-05 destabilises the titanium colloid, causing premature precipitation and
bath depletion. Conductivity monitoring provides 15-20 minute early warning before activation impact.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| conductivity_us_cm | 10-80 | 80-150 | > 150 uS/cm |
| ph | 6.5-8.0 | 8.0-9.0 | > 9.0 |

## 3. Immediate Actions

1. Increase DI water flow on PT-04 to maximum.
2. Check PT-03 conductivity simultaneously — if both elevated, source is PT-02 carry-over.
3. Inspect and clear any blockage in the overflow weir.

## 4. Corrective Action

| Condition | Action |
|-----------|--------|
| Conductivity 80-150 | Double fresh water flow, run 15 mins |
| Conductivity > 150 | Partial dump (30%), refill with DI water |

## 5. Verification

1. Conductivity < 60 uS/cm, pH 6.8-7.2.
2. Verify PT-05 titanium is within spec before resuming.

## 6. Historical Data

- Total incidents: 14 | Avg resolution: 20 mins

## 7. Related SOPs

- Upstream cause: SOP-PT03-001.
- Downstream impact: SOP-PT05-001.

---
Document owner: Process Engineering - Paint Shop | Rev 2.0 | Next review: 2026-05-01
