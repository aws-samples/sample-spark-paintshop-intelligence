# SOP-ED02-001: Membrane Fouling — UF Rinse 1 (ED-02)

**Severity:** MEDIUM | **Tank:** ED-02 UF Rinse 1 | **Est. fix:** 60-120 mins | **Rev:** 2.6

## 1. Description

UF membrane fouling in ED-02 is indicated by rising solids and conductivity in the permeate,
or rising differential pressure across the UF module. Fouling reduces UF efficiency, causing
MEq acid buildup in ED-01 bath (SOP-ED01-002). Paint coagulation on membrane surface is the
primary fouling mechanism. The UF system requires chemical cleaning (CIP) every 3-6 months;
early fouling detection through ML monitoring extends intervals.

## 2. Sensor Thresholds

| Sensor | Normal | Warning | Alarm |
|--------|--------|---------|-------|
| solids_pct | 1.0-5.0 % | 5.0-7.0 % | > 7.0 % |
| conductivity_us_cm | 500-2000 | 2000-2500 | > 2500 |
| ph | 5.5-7.0 | | |

## 3. Corrective Action

| Condition | Action |
|-----------|--------|
| Solids 5-7% | Reduce throughput, schedule CIP within 48h |
| Solids > 7% | Initiate CIP immediately (SOP-ED-CIP-001, 4h process) |
| Delta pressure > 2 bar | Emergency CIP |

## 5. Verification

1. Solids 1.5-3.5%, permeate flow > 220 L/hr.
2. Record CIP date in UF maintenance log.

## 7. Related SOPs

- SOP-ED-CIP-001 (UF Chemical Clean), SOP-ED01-002 (MEq Acid).

---
Document owner: Process Engineering - Paint Shop | Rev 2.6 | Next review: 2026-04-01
