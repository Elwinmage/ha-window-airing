"""Constants for the Window Airing integration."""
from __future__ import annotations

DOMAIN = "window_airing"
PLATFORMS = ["sensor", "binary_sensor", "number"]

# ── Config (config_flow) ─────────────────────────────────────────────────────
CONF_AREA = "area_id"
CONF_EXTERIOR_TEMP = "exterior_temp"

# ── Options (options_flow) ───────────────────────────────────────────────────
CONF_DEVICE_CLASSES = "device_classes"
CONF_OVERRIDE_WINDOWS = "override_windows"
CONF_OVERRIDE_INDOOR = "override_indoor"
CONF_OVERRIDE_CLIM = "override_clim"
CONF_THRESHOLD = "threshold"
CONF_OPEN_DELAY = "open_delay"          # seconds
CONF_MANAGE_CLIM = "manage_clim"
CONF_USE_TREND = "use_trend"
CONF_RAIN_ALERT = "rain_alert"
CONF_RAIN_SENSOR = "rain_sensor"
CONF_WEATHER = "weather"
CONF_WEATHER_RAIN_STATES = "weather_rain_states"

# ── Defaults ─────────────────────────────────────────────────────────────────
# Shelly BLU DoorWindow usually reports one of these; adjust in options if not.
DEFAULT_DEVICE_CLASSES: list[str] = ["window", "door", "opening"]
DEFAULT_THRESHOLD = 0.3                 # °C, delta below which airing is useless
DEFAULT_OPEN_DELAY = 60                 # s, continuous-open time before cutting clim
# Notify delay is a live per-room `number` entity (minutes). This is only the
# initial value before the entity restores its own stored value.
DEFAULT_NOTIFY_DELAY = 300              # s (= 5 min) before a notification fires
NOTIFY_DELAY_MAX_MIN = 120              # number entity upper bound (minutes)
DEFAULT_WEATHER_RAIN_STATES: list[str] = [
    "rainy", "pouring", "lightning-rainy", "snowy-rainy", "hail",
]

# ── Trend (replaces the manual Derivative helper) ────────────────────────────
TREND_WINDOW = 900                      # s of samples kept for the slope
TREND_MIN_SAMPLES = 5
TREND_RISING_SLOPE = 0.0006             # °C/s, ~ the old Derivative threshold

# ── Update cadence ───────────────────────────────────────────────────────────
# Heartbeat; state-change events also trigger an immediate refresh.
UPDATE_INTERVAL = 60                    # s

# ── Event bus ────────────────────────────────────────────────────────────────
EVENT_ALERT = "window_airing_alert"
ALERT_AIRING = "airing"                 # delta too low, close the window
ALERT_RAIN = "rain"                     # window open while raining

# States that mean "not running" for a climate entity.
CLIMATE_OFF_STATES = ("off", "unavailable", "unknown")
