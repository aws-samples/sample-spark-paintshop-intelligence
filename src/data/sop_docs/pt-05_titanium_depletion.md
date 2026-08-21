# SOP-PT05-001: Titanium Depletion — Activation Tank (PT-05)

**Severity:** HIGH | **Tank:** PT-05 Activation | **Est. fix:** 30-45 mins | **Rev:** 3.0

## 1. Description

The activation tank conditions the steel surface with titanium colloid nucleation sites that
promote fine, dense phosphate crystal formation in PT-06. Titanium depletion below 0.5 ppm causes
formation of coarse, sparse phosphate crystals (Hopeite instead of Scholzite), resulting in porous
coating, poor adhesion, and corrosion initiation sites. This is one of the highest-consequence
faults in the phosphating line — bodies with coarse phosphate must be stripped and reprocessed.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| titanium_ppm | 0.5-2.5 ppm | 0.4-0.5 ppm | < 0.4 ppm |
| ph | 8.5-9.5 | 9.5-10.0 | > 10.0 |
| temperature_c | 25-35°C | 35-38°C | > 38°C |

## 3. Immediate Actions

1. Halt body loading — activation failure has high downstream quality impact.
2. Test titanium concentration by photometric method (Spectroquant Ti kit).
3. Check pH — alkaline carry-over from PT-04 above pH 9.5 precipitates titanium colloid.
   If pH is cause, address PT-04 first (SOP-PT04-001).

## 4. Corrective Chemical Dosing

| Condition | Chemical | Dose |
|-----------|----------|------|
| Ti 0.4-0.5 ppm | Fixodine Ti (Chemetall) | 2.5 kg per 10,000L |
| Ti < 0.4 ppm | Fixodine Ti | 4 kg per 10,000L, re-test after 20 mins |
| pH > 9.5 simultaneously | Address PT-04 carry-over first, then dose Ti |

## 5. Verification

1. Titanium > 0.8 ppm by photometric test.
2. pH 8.8-9.2.
3. Run activation test on steel coupon: under microscope, nucleation sites should appear as fine
   uniform blue-grey coating. Coarse or absent coating — do not resume.

## 6. Historical Data

- Total incidents: 5 | Avg resolution: 38 mins | Bodies stripped: 14
- Root cause: PT-04 alkaline carry-over (3/5), dosing pump failure (2/5)
- JPH impact: -20 JPH | FBO impact: 40-55 mins | Cost per incident: ~€2,400

## 7. Related SOPs

- pH cause: SOP-PT04-001 first.
- Dosing pump failure: SOP-PT05-PUMP-001.
- Downstream impact: SOP-PT06-001 (increased acid drift risk 2h after Ti depletion).

---
Document owner: Process Engineering - Paint Shop | Rev 3.0 | Next review: 2026-03-01
