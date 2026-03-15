"""Constants for the BaillConnect integration."""
from homeassistant.components.climate.const import HVACMode

DOMAIN = "baillconnect"
MANUFACTURER = "Baill"
MODEL = "IDC-WEB BAILLCONNECT"

# API
BASE_URL = "https://www.baillconnect.com"
LOGIN_URL = f"{BASE_URL}/client/connexion"
API_URL = f"{BASE_URL}/api-client/regulations"

# HTTP headers
HEADER_CSRF = "X-CSRF-TOKEN"
HEADER_XHR = "X-Requested-With"
HEADER_XHR_VALUE = "XMLHttpRequest"

# Polling
SCAN_INTERVAL_SECONDS = 30

# Config entry keys
CONF_REGULATION_ID = "regulation_id"

# uc_mode values
UC_MODE_OFF = 0
UC_MODE_COOL = 1
UC_MODE_HEAT = 2
UC_MODE_DRY = 3

UC_MODE_TO_HVAC: dict[int, HVACMode] = {
    UC_MODE_OFF: HVACMode.OFF,
    UC_MODE_COOL: HVACMode.COOL,
    UC_MODE_HEAT: HVACMode.HEAT,
    UC_MODE_DRY: HVACMode.DRY,
}

HVAC_TO_UC_MODE: dict[HVACMode, int] = {v: k for k, v in UC_MODE_TO_HVAC.items()}

# Preset modes
PRESET_COMFORT = "confort"
PRESET_ECO = "eco"

T1_T2_TO_PRESET: dict[int, str] = {
    1: PRESET_COMFORT,
    2: PRESET_ECO,
}
PRESET_TO_T1_T2: dict[str, int] = {v: k for k, v in T1_T2_TO_PRESET.items()}

# ui_fan values
FAN_AUTO = 0
FAN_SPEED_1 = 1
FAN_SPEED_2 = 2
FAN_SPEED_3 = 3

FAN_MODE_AUTO = "auto"
FAN_MODE_LOW = "low"
FAN_MODE_MEDIUM = "medium"
FAN_MODE_HIGH = "high"

FAN_INT_TO_STR: dict[int, str] = {
    FAN_AUTO: FAN_MODE_AUTO,
    FAN_SPEED_1: FAN_MODE_LOW,
    FAN_SPEED_2: FAN_MODE_MEDIUM,
    FAN_SPEED_3: FAN_MODE_HIGH,
}
FAN_STR_TO_INT: dict[str, int] = {v: k for k, v in FAN_INT_TO_STR.items()}

# Temperature limits (API-side, here as safe defaults)
TEMP_MIN = 16.0
TEMP_MAX = 30.0
TEMP_STEP = 0.5

# motor_state: 4 = closed
MOTOR_STATE_CLOSED = 4

# Setpoint fields per mode
SETPOINT_FIELD_BY_MODE: dict[int, dict[int, str]] = {
    # mode: {t1_t2: field}
    UC_MODE_HEAT: {
        1: "setpoint_hot_t1",
        2: "setpoint_hot_t2",
    },
    UC_MODE_COOL: {
        1: "setpoint_cool_t1",
        2: "setpoint_cool_t2",
    },
    UC_MODE_DRY: {
        1: "setpoint_cool_t1",
        2: "setpoint_cool_t2",
    },
}

# Unique-ID suffixes for sensors
SENSOR_SUFFIX_TEMP = "temperature"
SENSOR_SUFFIX_BATTERY = "battery"
SENSOR_SUFFIX_CONNECTED = "connected"
SENSOR_SUFFIX_MOTOR = "motor_state"
SENSOR_SUFFIX_FAN = "fan_speed"
SENSOR_SUFFIX_CIRCUIT = "circuit_on"
SENSOR_SUFFIX_ERROR = "error_code"
SENSOR_SUFFIX_IDC_CONNECTED = "idc_connected"

# Entry data keys
ENTRY_CLIENT = "client"
ENTRY_COORDINATOR = "coordinator"
