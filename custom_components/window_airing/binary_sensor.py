"""Binary sensors: airing recommended, window open in rain, trend rising."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MANAGE_CLIM,
    CONF_RAIN_ALERT,
    CONF_THRESHOLD,
    CONF_USE_TREND,
    DEFAULT_THRESHOLD,
    DOMAIN,
)
from .coordinator import WindowAiringCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WindowAiringCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AiringRecommended(coordinator),
            OpenInRain(coordinator),
            TrendRising(coordinator),
        ]
    )


class _Base(CoordinatorEntity[WindowAiringCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: WindowAiringCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"


class AiringRecommended(_Base):
    """On when the delta no longer justifies keeping the window open."""

    _attr_translation_key = "airing_recommended"
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, coordinator: WindowAiringCoordinator) -> None:
        super().__init__(coordinator, "airing_recommended")

    @property
    def is_on(self) -> bool:
        d = self.coordinator.data
        cfg = self.coordinator._cfg
        threshold = cfg.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)
        use_trend = cfg.get(CONF_USE_TREND, False)
        return bool(
            d.get("open_delayed")
            and d.get("delta") is not None
            and d["delta"] < threshold
            and (not use_trend or not d.get("trend_rising"))
        )


class OpenInRain(_Base):
    """On when at least one window is open while it is raining."""

    _attr_translation_key = "open_in_rain"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:weather-pouring"

    def __init__(self, coordinator: WindowAiringCoordinator) -> None:
        super().__init__(coordinator, "open_in_rain")

    @property
    def is_on(self) -> bool:
        d = self.coordinator.data
        return bool(d.get("open_count", 0) > 0 and d.get("raining"))


class TrendRising(_Base):
    """On when the indoor temperature is rising (replaces the Derivative helper)."""

    _attr_translation_key = "trend_rising"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator: WindowAiringCoordinator) -> None:
        super().__init__(coordinator, "trend_rising")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("trend_rising"))
