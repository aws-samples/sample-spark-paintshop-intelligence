# Detected Fault Classes

The XGBoost classifier recognises **9 fault classes** across the 12 tanks. Each detected fault triggers an automated root-cause analysis report and job rescheduling.

## Pre-Treatment Line (PT-01 – PT-08)

| Fault Class | Affected Tank(s) | Severity | What Is Detected | Production Impact | Est. Fix |
|-------------|-----------------|----------|-----------------|-------------------|----------|
| `alkalinity_depletion` | PT-01 Hot Pre-Clean, PT-02 Main Cleaner | HIGH | Free alkalinity drops below 8 points — degreasing chemicals consumed faster than replenishment | Oils and soils remain on metal; phosphate coat will not bond correctly, leading to paint adhesion failures | 25–40 min |
| `rinse_contamination` | PT-03 Rinse 1, PT-04 Rinse 2, PT-07 Post-Rinse | MEDIUM | Conductivity rises above 80–100 µS/cm due to carry-over of cleaner or phosphate chemicals | Chemical cross-contamination degrades downstream bath chemistry and produces uneven phosphate crystal structure | 15–25 min |
| `titanium_depletion` | PT-05 Activation | HIGH | Titanium colloid concentration falls below nucleation threshold; bath pH climbs above 9.5 | Surface lacks activation nuclei — zinc phosphate crystals grow coarse or incomplete, reducing corrosion protection | 30–45 min |
| `acid_drift` | PT-06 Zinc Phosphate | HIGH | Free acid point rises outside 0.8–1.2 range, indicating bath imbalance | Thin or powdery phosphate coating; accelerated sludge build-up and possible flash rust on bare metal | 40–50 min |
| `zinc_depletion` | PT-06 Zinc Phosphate | HIGH | Zinc ion concentration drops below 0.9 g/L | Incomplete phosphate layer with bare metal spots; direct corrosion risk under e-coat | 35–50 min |
| `accelerator_depletion` | PT-06 Zinc Phosphate | MEDIUM | Nitrite accelerator (oxidising agent) falls below effective redox threshold | Slow phosphating kinetics — longer cycle times required or under-coated parts proceed to e-coat | 25–35 min |
| `ph_drift` | PT-08 Nano-Seal | MEDIUM | Bath pH drifts outside 4.0–5.0 operating window for zirconic acid conversion | Nano-seal conversion coating fails to form — loss of the bridging layer between phosphate and e-coat primer | 20–30 min |

## ElectroDeposition Line (ED-01 – ED-04)

| Fault Class | Affected Tank(s) | Severity | What Is Detected | Production Impact | Est. Fix |
|-------------|-----------------|----------|-----------------|-------------------|----------|
| `temperature_creep` | ED-01 E-Coat Bath | HIGH | Bath temperature climbs above 32 °C (normal: 28–30 °C) | Resin coagulation, reduced film build, surface pitting — parts must be stripped and re-coated | 30–45 min |
| `meq_acid_buildup` | ED-01 E-Coat Bath | HIGH | Milliequivalent acid rises due to electrochemical acid generation during deposition | pH imbalance disrupts solubilisation of paint resin; uneven film thickness and poor throwing power into recesses | 40–55 min |
| `rinse_contamination` | ED-02 UF Rinse 1, ED-03 UF Rinse 2, ED-04 DI Final Rinse | MEDIUM–HIGH | Conductivity or solids exceed threshold — e-coat drag-out contaminates rinse stages | Paint carry-over into rinse water increases waste treatment load; high conductivity in ED-04 causes curing defects | 25–50 min |

> **Sensor signals used for detection:** temperature, pH, conductivity, free acid / total acid points, bath solids (%), zinc concentration (g/L), titanium activity, accelerator redox potential, LSTM reconstruction error, and Isolation Forest anomaly score.
