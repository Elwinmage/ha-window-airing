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

# Config step: only the area + the (shared) outdoor sensor. Everything else is
# discovered and tuned in the options flow.
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AREA): selector.AreaSelector(),
        vol.Required(CONF_EXTERIOR_TEMP): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor", device_class="temperature"
            )
        ),
    }
)


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    def d(key, fallback):
        return defaults.get(key, fallback)

    return vol.Schema(
        {
            vol.Optional(
                CONF_DEVICE_CLASSES, default=d(CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["window", "door", "opening", "garage_door"],
                    multiple=True,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_THRESHOLD, default=d(CONF_THRESHOLD, DEFAULT_THRESHOLD)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=3.0, step=0.1, unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_OPEN_DELAY, default=d(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=3600, step=10, unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_USE_TREND, default=d(CONF_USE_TREND, False)
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_MANAGE_CLIM, default=d(CONF_MANAGE_CLIM, False)
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_RAIN_ALERT, default=d(CONF_RAIN_ALERT, False)
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_RAIN_SENSOR, default=d(CONF_RAIN_SENSOR, "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
            ),
            vol.Optional(
                CONF_RAIN_MM_THRESHOLD,
                default=d(CONF_RAIN_MM_THRESHOLD, DEFAULT_RAIN_MM_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=50.0, step=0.1, unit_of_measurement="mm",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_WEATHER, default=d(CONF_WEATHER, "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional(
                CONF_WEATHER_RAIN_STATES,
                default=d(CONF_WEATHER_RAIN_STATES, DEFAULT_WEATHER_RAIN_STATES),
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
                default=d(CONF_EXCLUDE_PLATFORMS, DEFAULT_EXCLUDE_PLATFORMS),
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
                CONF_EXCLUDE_ENTITIES, default=d(CONF_EXCLUDE_ENTITIES, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True)
            ),
            # ── Overrides (leave empty to keep auto-discovery) ───────────────
            vol.Optional(
                CONF_OVERRIDE_WINDOWS, default=d(CONF_OVERRIDE_WINDOWS, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["binary_sensor", "input_boolean"], multiple=True
                )
            ),
            vol.Optional(
                CONF_OVERRIDE_INDOOR, default=d(CONF_OVERRIDE_INDOOR, "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="temperature"
                )
            ),
            vol.Optional(
                CONF_OVERRIDE_CLIM, default=d(CONF_OVERRIDE_CLIM, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate", multiple=True)
            ),
        }
    )


class WindowAiringConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial config: pick a room."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # One entry per area.
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
    """Tune thresholds, clim, rain and overrides."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # Drop empty override fields so they don't shadow auto-discovery.
            cleaned = {k: v for k, v in user_input.items() if v not in ("", [], None)}
            return self.async_create_entry(title="", data=cleaned)

        return self.async_show_form(
            step_id="init", data_schema=_options_schema(dict(self.entry.options))
        )
