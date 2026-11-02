"""Constants for the Window Airing integration."""
from __future__ import annotations

DOMAIN = "window_airing"
PLATFORMS = ["sensor", "binary_sensor", "number"]
HOUSE_PLATFORMS = ["sensor", "number", "switch"]
STORAGE_VERSION = 1

# ── Entry types ──────────────────────────────────────────────────────────────
# Entries without this key are rooms: the house entry is the only marked one.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_HOUSE = "house"
HOUSE_UNIQUE_ID = f"{DOMAIN}_house"
# hass.data[DOMAIN] key of the loaded house coordinator.
DATA_HOUSE = "house"
# Dispatcher signal: the season or one of its settings changed.
SIGNAL_SEASON = f"{DOMAIN}_season_changed"

# ── Config (config_flow) ─────────────────────────────────────────────────────
CONF_AREA = "area_id"
CONF_EXTERIOR_TEMP = "exterior_temp"

# ── Options (options_flow) ───────────────────────────────────────────────────
CONF_DEVICE_CLASSES = "device_classes"
CONF_OVERRIDE_WINDOWS = "override_windows"
CONF_OVERRIDE_INDOOR = "override_indoor"
CONF_OVERRIDE_CLIM = "override_clim"
CONF_EXCLUDE_PLATFORMS = "exclude_platforms"
CONF_EXCLUDE_ENTITIES = "exclude_entities"
CONF_THRESHOLD = "threshold"
CONF_OPEN_DELAY = "open_delay"          # seconds
CONF_MANAGE_CLIM = "manage_clim"
CONF_USE_TREND = "use_trend"
CONF_RAIN_ALERT = "rain_alert"
CONF_RAIN_SENSOR = "rain_sensor"
CONF_RAIN_MM_THRESHOLD = "rain_mm_threshold"
CONF_WEATHER = "weather"
CONF_WEATHER_RAIN_STATES = "weather_rain_states"
CONF_WINTER_CUT_HEAT_ONLY = "winter_cut_heat_only"

# ── House options ────────────────────────────────────────────────────────────
CONF_HEATING_CLIMATES = "heating_climates"
CONF_WINTER_HEATING_MIN = "winter_heating_minutes"
CONF_SUMMER_IDLE_DAYS = "summer_idle_days"
CONF_WINTER_START_MONTH = "winter_start_month"
CONF_SUMMER_START_MONTH = "summer_start_month"
CONF_WINTER_REMINDER_INTERVAL = "winter_reminder_interval"
CONF_WINTER_MAX_REMINDERS = "winter_max_reminders"

# ── Defaults ─────────────────────────────────────────────────────────────────
# Shelly BLU DoorWindow usually reports one of these; adjust in options if not.
DEFAULT_DEVICE_CLASSES: list[str] = ["window", "door", "opening"]
# Computed/aggregate sensor platforms that must NOT count as a physical room
# temperature: they often carry device_class temperature but report a delta,
# an average or a statistic. Physical sources (shelly, onewire/esphome for
# DS18B20, airzone...) are not in this list and pass through. Editable in options.
DEFAULT_EXCLUDE_PLATFORMS: list[str] = [
    "template",
    "derivative",
    "statistics",
    "min_max",
    "integration",
    "trend",
    "filter",
    "group",
    "average",
]
DEFAULT_THRESHOLD = 0.3                 # °C, delta below which airing is useless
DEFAULT_OPEN_DELAY = 60                 # s, continuous-open time before cutting clim
# Notify delay is a live per-room `number` entity (minutes). This is only the
# initial value before the entity restores its own stored value.
DEFAULT_NOTIFY_DELAY = 300              # s (= 5 min) before a notification fires
NOTIFY_DELAY_MAX_MIN = 120              # number entity upper bound (minutes)
DEFAULT_WEATHER_RAIN_STATES: list[str] = [
    "rainy", "pouring", "lightning-rainy", "snowy-rainy", "hail",
]
# For a numeric rain sensor (mm): raining when its value is strictly above this.
DEFAULT_RAIN_MM_THRESHOLD = 0.0

# Winter mode. The max open time is a live `number` entity (minutes): this is
# only its initial value before the entity restores its stored value.
DEFAULT_WINTER_MAX_OPEN = 600           # s (= 10 min) before the winter alert
DEFAULT_WINTER_HEATING_MIN = 30         # min of daily heating to enter winter
DEFAULT_SUMMER_IDLE_DAYS = 7            # heating-free days to leave winter, 0 = off
DEFAULT_WINTER_START_MONTH = 10         # auto winter from this month...
DEFAULT_SUMMER_START_MONTH = 4          # ...auto summer from this one
DEFAULT_WINTER_REMINDER_INTERVAL = 10   # min between two reminders
DEFAULT_WINTER_MAX_REMINDERS = 3        # reminders after the first alert
# `hvac_action` values that count as heating.
HEATING_ACTIONS = ("heating", "preheating")
# `hvac_modes` that make a climate able to cool, i.e. an AC.
COOLING_MODES = ("cool", "heat_cool")
SOURCE_MANUAL = "manual"
SOURCE_AUTO = "auto"

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
ALERT_SEASON = "season"                 # automatic season change
REASON_MAX_DURATION = "max_duration"    # winter: open longer than allowed

# States that mean "not running" for a climate entity.
CLIMATE_OFF_STATES = ("off", "unavailable", "unknown")
# Climate attributes saved before turning it off, restored on close.
CLIMATE_RESTORE_ATTRS = (
    "temperature",
    "target_temp_low",
    "target_temp_high",
    "fan_mode",
    "preset_mode",
    "swing_mode",
)
# After an HA reboot, wait up to this long (s) for window states to be known
# before acting; past it, unavailable windows are treated as closed.
STARTUP_GRACE = 600


def is_house_entry(entry) -> bool:
    """True for the home-wide entry, False for a room."""
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_HOUSE
