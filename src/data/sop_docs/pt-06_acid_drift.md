# SOP-PT06-001: Free Acid Drift — Zinc Phosphate Tank (PT-06)

**Severity:** HIGH | **Tank:** PT-06 Zinc Phosphate | **Est. fix:** 40-50 mins | **Rev:** 3.1

## 1. Description

Free acid drift occurs when the free acid point value in the zinc phosphate bath rises above the
upper control limit of 1.5 points. This causes over-etching of the steel substrate, non-uniform
phosphate crystal formation, thin coating weight, and significantly reduced corrosion resistance.
Bodies processed through an out-of-spec PT-06 bath exhibit corrosion under paint within 12-18
months in field conditions. All bodies processed during the fault window must be quarantined.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm (triggers SOP) |
|--------|--------|---------|----------------------|
| free_acid_pts | 0.5-1.5 | 1.5-1.8 | > 1.8 pts |
| total_acid_pts | 18-24 | 24-26 | > 26 pts |
| conductivity_us_cm | 2000-4000 | 4000-4200 | > 4200 uS/cm |
| zinc_g_per_l | 1.0-1.8 | 0.9-1.0 | < 0.9 g/L |

ML anomaly detection flags this fault 47 minutes before alarm threshold during the warning-phase
drift, providing a preventive intervention window.

## 3. Immediate Actions (First 10 Minutes)

1. **Notify line supervisor and halt body loading into PT-06.** Do not stop bodies already in the
   bath — complete their cycle. Stop loading at the entry conveyor. Estimated hold: 8-10 mins.
2. **Take a manual titration sample.** Draw 100mL from mid-depth. Titrate for free acid and total
   acid. If titration disagrees with sensors by > 0.3 pts, escalate to maintenance for sensor
   recalibration (see SOP-PT06-SENSOR-001).
3. **Check zinc concentration.** If zinc_g_per_l < 1.0, treat zinc depletion first (SOP-PT06-002)
   before dosing for acid correction. Do not dose acid corrector if zinc is depleted.

## 4. Corrective Chemical Dosing

**Safety:** Wear chemical-resistant gloves, safety glasses, acid-resistant apron. Phosphate
concentrate pH 1.5. Have eyewash station accessible.

| Condition | Chemical | Dose | Method |
|-----------|----------|------|--------|
| Free acid 1.8-2.2 pts | Phosphate concentrate (Bonder 958) | 1.5L per 1000L bath | Dosing pump over 15 mins, agitate |
| Free acid > 2.2 pts | Phosphate concentrate (Bonder 958) | 2.5L per 1000L bath | Dosing pump over 20 mins, agitate |
| Conductivity > 4200 | Partial bath dump + DI water | 5% bath volume | Drain 5%, refill with DI water + replenish salts |
| Total acid > 26 pts | Sodium carbonate (neutraliser) | 0.8 kg per 1000L | Dissolve in 10L DI water first, add slowly |

## 5. Verification Before Resuming Production

5. Wait 15 minutes after dosing (bath homogenisation with agitation running).
6. Take second titration: free acid 0.8-1.2 pts, total acid 19-22 pts. If still out of spec,
   repeat dose at 50% and re-verify after 10 mins.
7. ML anomaly score must drop below 0.3 for 3 consecutive readings (15 seconds).
   Conductivity must be below 3800 uS/cm.
8. Run one test steel panel before production bodies. Send to lab: coating weight target
   1.8-3.5 g/m2, crystal morphology check. Do not resume until lab confirms.

## 6. Historical Data (Last 12 Months)

- Total incidents: 7 | Avg resolution: 42 mins | Bodies quarantined: 34 | Bodies scrapped: 6
- Most common root cause: Zinc depletion cascade (4/7)
- Recommended technician: T-04 (Rajesh Kumar) — fastest resolution 28 mins
- JPH impact: -17 JPH during hold | FBO impact: 35-50 mins delay

## 7. Related SOPs

- zinc_g_per_l < 0.9: Follow SOP-PT06-002 (Zinc Depletion) first, return to this SOP.
- conductivity > 4500 not responding: SOP-PT06-005 (Bath Dump & Rebuild) — 4 hours.
- Sensor conflict > 0.3 pts: SOP-PT06-SENSOR-001 (Sensor Recalibration).
- Escalate to shift supervisor: free acid > 3.0 pts or resolution > 60 minutes.

---
Document owner: Process Engineering - Paint Shop | Rev 3.1 | Next review: 2026-05-20
