# SOP-PT06-003: Accelerator Depletion — Zinc Phosphate Tank (PT-06)

**Severity:** MEDIUM | **Tank:** PT-06 Zinc Phosphate | **Est. fix:** 25-35 mins | **Rev:** 2.5

## 1. Description

The nitrite accelerator (oxidising agent) maintains the redox potential needed for rapid
phosphate crystallisation. Depletion below 2.0 points slows the reaction, causing extended
coating time, excessive sludge formation, and coarse crystal morphology. Low accelerator
often co-occurs with zinc depletion as both are consumed by the phosphating reaction.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| accelerator_pts | 2.5-4.5 | 2.0-2.5 | < 2.0 pts |
| free_acid_pts | 0.5-1.5 | 1.5-1.8 | > 1.8 |

## 3. Immediate Actions

1. Reduce conveyor speed by 15% to compensate for slower reaction rate.
2. Test accelerator by nitrite Merckoquant strips or permanganate titration.
3. Simultaneously check zinc — if both depleted, add accelerator first, then zinc.

## 4. Corrective Chemical Dosing

| Condition | Dose |
|-----------|------|
| Accelerator 2.0-2.5 pts | 0.8L sodium nitrite solution (5%) per 10,000L |
| Accelerator < 2.0 pts | 1.5L sodium nitrite solution per 10,000L |

## 5. Verification

1. Accelerator 2.8-3.5 pts.
2. Sludge rake — increased sludge expected, confirm sludge pump running.
3. Test panel — crystal size < 10 microns under microscope.

## 6. Historical Data

- Total incidents: 9 | Avg resolution: 29 mins
- JPH impact: -8 JPH

## 7. Related SOPs

- Zinc co-depletion: SOP-PT06-002.
- Sludge excess: SOP-PT06-SLUDGE-001.

---
Document owner: Process Engineering - Paint Shop | Rev 2.5 | Next review: 2026-06-01
