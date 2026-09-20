"""Config and options flow for Window Airing."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import selector

from .const import (
    CONF_AREA,
    CONF_DEVICE_CLASSES,
    CONF_EXCLUDE_ENTITIES,
    CONF_EXCLUDE_PLATFORMS,
    CONF_EXTERIOR_TEMP,
    CONF_MANAGE_CLIM,
    CONF_OPEN_DELAY,
    CONF_OVERRIDE_CLIM,
    CONF_OVERRIDE_INDOOR,
    CONF_OVERRIDE_WINDOWS,
    CONF_RAIN_ALERT,
    CONF_RAIN_MM_THRESHOLD,
    CONF_RAIN_SENSOR,
    CONF_THRESHOLD,
    CONF_USE_TREND,
    CONF_WEATHER,
    CONF_WEATHER_RAIN_STATES,
    DEFAULT_DEVICE_CLASSES,
    DEFAULT_EXCLUDE_PLATFORMS,
    DEFAULT_OPEN_DELAY,
    DEFAULT_RAIN_MM_THRESHOLD,
    DEFAULT_THRESHOLD,
    DEFAULT_WEATHER_RAIN_STATES,
    DOMAIN,
)

# A rain source can be a numeric sensor (mm) or a binary_sensor.
_RAIN_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
)
_TEMP_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)

# Config step: identity + the two live sensors. Everything else is tuned later.
# The rain sensor is optional (no default → the key is simply omitted if empty).
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AREA): selector.AreaSelector(),
        vol.Required(CONF_EXTERIOR_TEMP): _TEMP_SELECTOR,
        vol.Optional(CONF_RAIN_SENSOR): _RAIN_SELECTOR,
    }
)


def _optional_entity(key: str, current: dict[str, Any]) -> vol.Optional:
    """Optional entity marker: pre-fills the current value, clears when empty.

    Crucially there is NO default="" — an empty EntitySelector value fails
    validation ("neither a valid entity ID nor a valid UUID"). Instead the
    field is truly optional and simply omitted when the user clears it.
    """
    val = current.get(key)
    if val:
        return vol.Optional(key, description={"suggested_value": val})
    return vol.Optional(key)


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    def num(key, fallback):
        return current.get(key, fallback)

    return vol.Schema(
        {
            # ── The two live sensors (editable after creation) ───────────────
            vol.Required(
                CONF_EXTERIOR_TEMP, default=current.get(CONF_EXTERIOR_TEMP)
            ): _TEMP_SELECTOR,
            _optional_entity(CONF_RAIN_SENSOR, current): _RAIN_SELECTOR,
            vol.Optional(
                CONF_RAIN_MM_THRESHOLD,
                default=num(CONF_RAIN_MM_THRESHOLD, DEFAULT_RAIN_MM_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=50.0, step=0.1, unit_of_measurement="mm",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            # ── Airing thresholds ────────────────────────────────────────────
            vol.Optional(
                CONF_DEVICE_CLASSES, default=num(CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["window", "door", "opening", "garage_door"],
                    multiple=True,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_THRESHOLD, default=num(CONF_THRESHOLD, DEFAULT_THRESHOLD)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=3.0, step=0.1, unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_OPEN_DELAY, default=num(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=3600, step=10, unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_USE_TREND, default=num(CONF_USE_TREND, False)
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_MANAGE_CLIM, default=num(CONF_MANAGE_CLIM, False)
            ): selector.BooleanSelector(),
            # ── Rain alert ───────────────────────────────────────────────────
            vol.Optional(
                CONF_RAIN_ALERT, default=num(CONF_RAIN_ALERT, False)
            ): selector.BooleanSelector(),
            _optional_entity(CONF_WEATHER, current): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional(
                CONF_WEATHER_RAIN_STATES,
                default=num(CONF_WEATHER_RAIN_STATES, DEFAULT_WEATHER_RAIN_STATES),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        "rainy", "pouring", "lightning-rainy",
                        "snowy-rainy", "hail", "snowy", "lightning",
                    ],
                    multiple=True,
                    custom_value=True,
                )
            ),
            # ── Discovery exclusions ─────────────────────────────────────────
            vol.Optional(
                CONF_EXCLUDE_PLATFORMS,
                default=num(CONF_EXCLUDE_PLATFORMS, DEFAULT_EXCLUDE_PLATFORMS),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        "template", "derivative", "statistics", "min_max",
                        "integration", "trend", "filter", "group", "average",
                    ],
                    multiple=True,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_EXCLUDE_ENTITIES, default=num(CONF_EXCLUDE_ENTITIES, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True)
            ),
            # ── Overrides (leave empty to keep auto-discovery) ───────────────
            vol.Optional(
                CONF_OVERRIDE_WINDOWS, default=num(CONF_OVERRIDE_WINDOWS, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["binary_sensor", "input_boolean"], multiple=True
                )
            ),
            _optional_entity(CONF_OVERRIDE_INDOOR, current): _TEMP_SELECTOR,
            vol.Optional(
                CONF_OVERRIDE_CLIM, default=num(CONF_OVERRIDE_CLIM, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate", multiple=True)
            ),
        }
    )


class WindowAiringConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial config: pick a room and its sensors."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_AREA])
            self._abort_if_unique_id_configured()

            area = ar.async_get(self.hass).async_get_area(user_input[CONF_AREA])
            title = area.name if area else user_input[CONF_AREA]
            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(step_id="user", data_schema=CONFIG_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return WindowAiringOptionsFlow(entry)


class WindowAiringOptionsFlow(OptionsFlow):
    """Tune the room; also lets the two live sensors be changed or cleared."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # The two live sensors live in entry.data so that clearing the rain
            # sensor actually removes it (options can only add/override a merge,
            # never unset a data key). Everything else goes to options.
            new_data = dict(self.entry.data)
            new_data[CONF_EXTERIOR_TEMP] = user_input.pop(CONF_EXTERIOR_TEMP)
            if user_input.get(CONF_RAIN_SENSOR):
                new_data[CONF_RAIN_SENSOR] = user_input.pop(CONF_RAIN_SENSOR)
            else:
                user_input.pop(CONF_RAIN_SENSOR, None)
                new_data.pop(CONF_RAIN_SENSOR, None)
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)

            # Drop empty tunables so cleared optional fields fall back to unset.
            cleaned = {
                k: v for k, v in user_input.items() if v not in ("", [], None)
            }
            return self.async_create_entry(title="", data=cleaned)

        current = {**self.entry.data, **self.entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(current)
        )
