"""Switch entity: the home-wide winter mode."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .house import WindowAiringHouse


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WindowAiringHouse = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WinterModeSwitch(coordinator)])


class WinterModeSwitch(CoordinatorEntity[WindowAiringHouse], SwitchEntity):
    """On in winter. Moved by hand, or by the automatic season change."""

    _attr_has_entity_name = True
    _attr_translation_key = "winter_mode"
    _attr_icon = "mdi:snowflake"

    def __init__(self, coordinator: WindowAiringHouse) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_winter_mode"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self.coordinator.winter

    @property
    def extra_state_attributes(self):
        return {
            "source": self.coordinator.source,
            "changed_at": self.coordinator.changed_at,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_winter(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_winter(False)
