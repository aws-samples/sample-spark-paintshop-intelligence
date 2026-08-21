# SOP-PT06-002: Zinc Depletion — Zinc Phosphate Tank (PT-06)

**Severity:** HIGH | **Tank:** PT-06 Zinc Phosphate | **Est. fix:** 35-50 mins | **Rev:** 3.3

## 1. Description

Zinc depletion below 0.9 g/L causes thin, incomplete phosphate coating or bare metal areas.
The zinc ion is consumed by the phosphating reaction; high throughput periods and high acid
conditions accelerate consumption. Zinc-depleted baths produce thin, powdery coatings with
poor adhesion that fail adhesion tape tests. All bodies processed must be quarantined. This
fault is the most common root cause of downstream acid drift (SOP-PT06-001).

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| zinc_g_per_l | 1.0-1.8 | 0.9-1.0 | < 0.9 g/L |
| free_acid_pts | 0.5-1.5 | 1.5-1.8 | > 1.8 |
| accelerator_pts | 2.5-4.5 | 2.0-2.5 | < 2.0 |

## 3. Immediate Actions

1. Halt body loading immediately.
2. ICP analysis preferred; if not available, use Titrifix Zn colorimetric test.
3. Check accelerator simultaneously — zinc depletion often co-occurs with accelerator depletion.

## 4. Corrective Chemical Dosing

| Condition | Chemical | Dose |
|-----------|----------|------|
| Zinc 0.9-1.0 g/L | Zinc phosphate replenisher (Granodine 958-Z) | 3 kg per 10,000L |
| Zinc < 0.9 g/L | Granodine 958-Z + zinc oxide | 5 kg + 0.5 kg per 10,000L |
| Accelerator co-depletion | Add 1L nitrite accelerator per 10,000L after zinc correction |

## 5. Verification

1. Zinc 1.1-1.5 g/L by ICP or Titrifix.
2. Run test panel — coating weight 1.8-3.5 g/m2, uniform grey appearance.
3. Check for free acid rise after zinc correction — re-titrate.

## 6. Historical Data

- Total incidents: 11 | Avg resolution: 44 mins | Bodies quarantined: 67
- Cost per incident: ~€3,800 including quarantine and rework
- JPH impact: -17 JPH | FBO impact: 40-55 mins

## 7. Related SOPs

- If acid also elevated: SOP-PT06-001 (Acid Drift).
- After zinc correction, check PT-05 titanium depletion risk.

---
Document owner: Process Engineering - Paint Shop | Rev 3.3 | Next review: 2026-05-20
