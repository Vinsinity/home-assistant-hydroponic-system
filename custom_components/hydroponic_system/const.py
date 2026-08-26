"""Constants and default profiles for Hydroponic System."""

from __future__ import annotations

DOMAIN = "hydroponic_system"
CONF_ENVIRONMENT_DEVICES = "environment_devices"
CONF_CO2_SENSORS = "co2_sensors"
CONF_TEMPERATURE_SENSORS = "temperature_sensors"
CONF_HUMIDITY_SENSORS = "humidity_sensors"
CONF_VPD_SENSOR = "vpd_sensor"
CONF_PPM_SENSOR = "ppm_sensor"
CONF_PH_SENSOR = "ph_sensor"
CONF_DO_SENSOR = "do_sensor"
CONF_WATER_TEMPERATURE_SENSOR = "water_temperature_sensor"
CONF_WATER_LEVEL_SENSOR = "water_level_sensor"
CONF_LIGHT = "light"
CONF_CO2_VALVE = "co2_valve"
CONF_EXHAUST_FAN = "exhaust_fan"
CONF_INLINE_FAN = "inline_fan"
CONF_RDWC_PUMP = "rdwc_pump"
CONF_CLIMATE = "climate"
CONF_DEHUMIDIFIER = "dehumidifier"
CONF_HUMIDIFIER = "humidifier"
CONF_CHILLER = "chiller"
CONF_CAMERAS = "cameras"
CONF_LEAK_SENSORS = "leak_sensors"

SENSOR_KEYS = (
    CONF_ENVIRONMENT_DEVICES,
    CONF_CO2_SENSORS,
    CONF_TEMPERATURE_SENSORS,
    CONF_HUMIDITY_SENSORS,
    CONF_VPD_SENSOR,
    CONF_PPM_SENSOR,
    CONF_PH_SENSOR,
    CONF_DO_SENSOR,
    CONF_WATER_TEMPERATURE_SENSOR,
    CONF_WATER_LEVEL_SENSOR,
    CONF_CAMERAS,
    CONF_LEAK_SENSORS,
)

CONTROL_KEYS = (
    CONF_LIGHT,
    CONF_CO2_VALVE,
    CONF_EXHAUST_FAN,
    CONF_INLINE_FAN,
    CONF_RDWC_PUMP,
    CONF_CLIMATE,
    CONF_DEHUMIDIFIER,
    CONF_HUMIDIFIER,
    CONF_CHILLER,
)
STORAGE_KEY = f"{DOMAIN}.profiles"
STORAGE_VERSION = 1
JOURNAL_RECOVERY_STORAGE_KEY = f"{DOMAIN}.journal_recovery"
JOURNAL_RECOVERY_STORAGE_VERSION = 1
PANEL_URL = "/hydroponic-system-static/hydroponic-system-panel.js"
PANEL_MODULE_URL = f"{PANEL_URL}?v=0.26.1"
PANEL_PATH = "hydroponic-system"
PANEL_COMPONENT = "hydroponic-system-panel"

STAGE_ORDER = ["germination", "early_veg", "veg", "bloom", "darkness", "harvest"]

DEFAULT_DOSING_POLICY = {
    "nutrient_interval_minutes": 360,
    "mixing_wait_minutes": 20,
    "remeasure_wait_minutes": 10,
    "ph_interval_minutes": 30,
    "ph_deadband": 0.10,
    "max_nutrient_dose_ml": 10.0,
    "max_ph_dose_ml": 1.0,
    "ph_single_direction": True,
    "sequence": "nutrients_mix_remeasure_ph",
}

DEFAULT_CULTIVATION_PLAN = [
    {"stage": "germination", "minimum_days": 4, "maximum_days": 8, "planned_days": 6},
    {"stage": "early_veg", "minimum_days": 10, "maximum_days": 15, "planned_days": 12},
    {"stage": "veg", "minimum_days": 21, "maximum_days": 28, "planned_days": 24},
    {"stage": "bloom", "minimum_days": 42, "maximum_days": 56, "planned_days": 49},
    {"stage": "darkness", "minimum_days": 3, "maximum_days": 3, "planned_days": 3},
    {"stage": "harvest", "minimum_days": 7, "maximum_days": 14, "planned_days": 10},
]

DEFAULT_PROFILES = {
    "germination": {
        "name": "Çimlenme",
        "planned_days": 6,
        "photoperiod": 24,
        "light_intensity": 30,
        "day_temperature": 25,
        "night_temperature": 23,
        "humidity": 70,
        "vpd": 0.8,
        "co2": 450,
        "ppm": 300,
        "water_temperature": 19,
        "ph": 5.8,
        "do_minimum": 6,
        "nutrient_ids": [],
    },
    "early_veg": {
        "name": "Erken gelişim",
        "planned_days": 12,
        "photoperiod": 20,
        "light_intensity": 50,
        "day_temperature": 25,
        "night_temperature": 22,
        "humidity": 65,
        "vpd": 1.0,
        "co2": 800,
        "ppm": 500,
        "water_temperature": 19,
        "ph": 5.8,
        "do_minimum": 6,
        "nutrient_ids": [],
    },
    "veg": {
        "name": "Gelişim",
        "planned_days": 24,
        "photoperiod": 18,
        "light_intensity": 75,
        "day_temperature": 26,
        "night_temperature": 22,
        "humidity": 60,
        "vpd": 1.2,
        "co2": 900,
        "ppm": 700,
        "water_temperature": 19,
        "ph": 5.8,
        "do_minimum": 6,
        "nutrient_ids": [],
    },
    "bloom": {
        "name": "Çiçeklenme",
        "planned_days": 49,
        "photoperiod": 12,
        "light_intensity": 100,
        "day_temperature": 25,
        "night_temperature": 21,
        "humidity": 50,
        "vpd": 1.35,
        "co2": 850,
        "ppm": 800,
        "water_temperature": 19,
        "ph": 5.8,
        "do_minimum": 6,
        "nutrient_ids": [],
    },
    "darkness": {
        "name": "Karanlık",
        "planned_days": 3,
        "photoperiod": 0,
        "light_intensity": 0,
        "day_temperature": 21,
        "night_temperature": 20,
        "humidity": 50,
        "vpd": 1.1,
        "co2": 450,
        "ppm": 800,
        "water_temperature": 19,
        "ph": 5.8,
        "do_minimum": 6,
        "nutrient_ids": [],
    },
    "harvest": {
        "name": "Hasat / Kurutma",
        "planned_days": 10,
        "photoperiod": 0,
        "light_intensity": 0,
        "day_temperature": 19,
        "night_temperature": 18,
        "humidity": 55,
        "vpd": 0.95,
        "co2": 450,
        "ppm": 0,
        "water_temperature": 19,
        "ph": 5.8,
        "do_minimum": 0,
        "nutrient_ids": [],
    },
}
