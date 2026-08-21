# SOP-PT05-002: High pH — Activation Tank (PT-05)

**Severity:** MEDIUM | **Tank:** PT-05 Activation | **Est. fix:** 20-30 mins | **Rev:** 1.9

## 1. Description

Elevated pH above 9.5 in the activation tank causes titanium colloid precipitation and bath
depletion. High pH is most commonly caused by alkaline carry-over from an overloaded or
malfunctioning PT-04 rinse. This fault must be resolved before titanium depletion occurs —
ML detects pH rise 20-30 minutes before titanium instruments show depletion.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| ph | 8.5-9.5 | 9.5-10.0 | > 10.0 |
| titanium_ppm | 0.5-2.5 | 0.4-0.5 | < 0.4 |

## 3. Immediate Actions

1. Investigate and resolve PT-04 contamination (SOP-PT04-001).
2. Increase PT-05 fresh water overflow to dilute alkaline contamination.
3. Do not add titanium replenisher while pH > 9.5 — it will precipitate immediately.

## 4. Corrective Action

| Condition | Action |
|-----------|--------|
| pH 9.5-10.0 | Increase overflow, check PT-04 |
| pH > 10.0 | Partial dump (20%), refill DI, address PT-04 source |

## 5. Verification

1. pH 8.8-9.2, then re-check titanium.
2. If titanium dropped: SOP-PT05-001.

## 6. Historical Data

- Total incidents: 8 | Avg resolution: 24 mins

## 7. Related SOPs

- SOP-PT04-001, SOP-PT05-001.

---
Document owner: Process Engineering - Paint Shop | Rev 1.9 | Next review: 2026-06-15
