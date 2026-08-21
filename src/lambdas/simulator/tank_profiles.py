import random
from datetime import datetime, timezone

TANK_PROFILES = {
    "PT-01": {
        "name": "Hot Pre-Clean",
        "temperature_c": {"min": 50, "max": 60, "sigma": 0.8},
        "ph":            {"min": 11.0, "max": 12.0, "sigma": 0.05},
        "free_alkalinity": {"min": 8.0, "max": 14.0, "sigma": 0.3},
        "conductivity_us_cm": {"min": 5000, "max": 12000, "sigma": 200},
    },
    "PT-02": {
        "name": "Main Cleaner",
        "temperature_c":    {"min": 55, "max": 65, "sigma": 0.8},
        "ph":               {"min": 11.5, "max": 12.5, "sigma": 0.05},
        "free_alkalinity":  {"min": 10.0, "max": 16.0, "sigma": 0.3},
        "total_alkalinity": {"min": 14.0, "max": 22.0, "sigma": 0.4},
    },
    "PT-03": {
        "name": "Rinse 1",
        "conductivity_us_cm": {"min": 20, "max": 100, "sigma": 5},
        "ph":                 {"min": 6.5, "max": 8.5, "sigma": 0.1},
        "rinse_flow":         {"min": 8.0, "max": 15.0, "sigma": 0.5},
    },
    "PT-04": {
        "name": "Rinse 2",
        "conductivity_us_cm": {"min": 10, "max": 80, "sigma": 4},
        "ph":                 {"min": 6.5, "max": 8.0, "sigma": 0.1},
        "rinse_flow":         {"min": 8.0, "max": 15.0, "sigma": 0.5},
    },
    "PT-05": {
        "name": "Activation",
        "ph":           {"min": 8.5, "max": 9.5, "sigma": 0.05},
        "temperature_c": {"min": 25, "max": 35, "sigma": 0.5},
        "titanium_ppm": {"min": 0.5, "max": 2.5, "sigma": 0.1},
    },
    "PT-06": {
        "name": "Zinc Phosphate",
        "temperature_c":      {"min": 40, "max": 50, "sigma": 0.5},
        "free_acid_pts":      {"min": 0.5, "max": 1.5, "sigma": 0.05},
        "total_acid_pts":     {"min": 18, "max": 24, "sigma": 0.3},
        "zinc_g_per_l":       {"min": 1.0, "max": 1.8, "sigma": 0.03},
        "accelerator_pts":    {"min": 2.5, "max": 4.5, "sigma": 0.1},
        "conductivity_us_cm": {"min": 2000, "max": 4000, "sigma": 50},
    },
    "PT-07": {
        "name": "Post-Rinse",
        "conductivity_us_cm": {"min": 50, "max": 200, "sigma": 8},
        "ph":                 {"min": 6.0, "max": 8.0, "sigma": 0.1},
        "rinse_flow":         {"min": 8.0, "max": 15.0, "sigma": 0.5},
    },
    "PT-08": {
        "name": "Nano-Seal",
        "ph":               {"min": 4.0, "max": 5.0, "sigma": 0.05},
        "temperature_c":    {"min": 25, "max": 35, "sigma": 0.5},
        "concentration_pct": {"min": 0.3, "max": 1.2, "sigma": 0.03},
    },
    "ED-01": {
        "name": "E-Coat Bath",
        "ph":                   {"min": 5.8, "max": 6.2, "sigma": 0.02},
        "temperature_c":        {"min": 28, "max": 32, "sigma": 0.3},
        "solids_pct":           {"min": 18, "max": 22, "sigma": 0.2},
        "conductivity_us_cm":   {"min": 1200, "max": 1800, "sigma": 30},
        "voltage_v":            {"min": 200, "max": 350, "sigma": 5},
        "meq_acid":             {"min": 18, "max": 32, "sigma": 0.5},
        "pigment_binder_ratio": {"min": 0.18, "max": 0.25, "sigma": 0.003},
    },
    "ED-02": {
        "name": "UF Rinse 1",
        "ph":                 {"min": 5.5, "max": 7.0, "sigma": 0.1},
        "conductivity_us_cm": {"min": 500, "max": 2000, "sigma": 50},
        "solids_pct":         {"min": 1.0, "max": 5.0, "sigma": 0.2},
    },
    "ED-03": {
        "name": "UF Rinse 2",
        "ph":                 {"min": 5.5, "max": 7.0, "sigma": 0.1},
        "conductivity_us_cm": {"min": 200, "max": 800, "sigma": 20},
        "solids_pct":         {"min": 0.2, "max": 1.5, "sigma": 0.05},
    },
    "ED-04": {
        "name": "DI Water Final Rinse",
        "conductivity_us_cm": {"min": 1, "max": 20, "sigma": 1},
        "ph":                 {"min": 5.5, "max": 7.5, "sigma": 0.1},
    },
}

FAULT_OVERRIDES = {
    "acid_drift":          {"PT-06": {"free_acid_pts": 2.4, "total_acid_pts": 26.1, "conductivity_us_cm": 4380}},
    "zinc_depletion":      {"PT-06": {"zinc_g_per_l": 0.78, "accelerator_pts": 2.1}},
    "accelerator_depletion": {"PT-06": {"accelerator_pts": 1.8, "free_acid_pts": 1.7}},
    "temperature_creep":   {"ED-01": {"temperature_c": 35.2, "solids_pct": 17.1}},
    "meq_acid_buildup":    {"ED-01": {"meq_acid": 41.5, "conductivity_us_cm": 1950}},
    "ph_drift":            {"ED-01": {"ph": 6.8, "solids_pct": 21.5},
                            "PT-08": {"ph": 6.2, "concentration_pct": 0.12}},
    "rinse_contamination": {
        "PT-03": {"conductivity_us_cm": 320},
        "PT-04": {"conductivity_us_cm": 210},
        "PT-07": {"conductivity_us_cm": 580},
        "ED-02": {"conductivity_us_cm": 3800},
        "ED-03": {"conductivity_us_cm": 1400},
        "ED-04": {"conductivity_us_cm": 95},
    },
    "titanium_depletion":  {"PT-05": {"titanium_ppm": 0.3, "ph": 9.8}},
    "alkalinity_depletion":{"PT-01": {"free_alkalinity": 5.2, "ph": 10.6},
                            "PT-02": {"free_alkalinity": 7.1, "total_alkalinity": 12.3}},
}


def generate_reading(tank_id: str, fault: str = None, drift_factor: float = 1.0) -> dict:
    """Generate a sensor reading for a tank.

    drift_factor: 0.0 = normal readings, 1.0 = full fault values.
    Values between 0 and 1 interpolate gradually — simulating a fault developing over time.
    """
    profile = TANK_PROFILES[tank_id]
    reading = {
        "tank_id": tank_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    for sensor, params in profile.items():
        if sensor == "name":
            continue
        mid = (params["min"] + params["max"]) / 2
        value = random.gauss(mid, params["sigma"])
        value = max(params["min"] * 0.95, min(params["max"] * 1.05, value))
        reading[sensor] = round(value, 3)

    if fault and fault in FAULT_OVERRIDES and drift_factor > 0:
        overrides = FAULT_OVERRIDES[fault].get(tank_id, {})
        for sensor, fault_value in overrides.items():
            normal_value = reading.get(sensor, fault_value)
            # Interpolate: at drift_factor=0 → normal, at 1.0 → full fault value
            reading[sensor] = round(normal_value + (fault_value - normal_value) * drift_factor, 3)

    return reading
