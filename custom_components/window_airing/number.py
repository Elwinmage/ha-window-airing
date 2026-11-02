"""Number entities: room notify delay and home-wide winter maximum open time."""
from __future__ import annotations

from homeassistant.components.number import (
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_NOTIFY_DELAY,
    DEFAULT_WINTER_MAX_OPEN,
    DOMAIN,
    NOTIFY_DELAY_MAX_MIN,
    is_house_entry,
)
from .coordinator import WindowAiringCoordinator
from .house import WindowAiringHouse


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if is_house_entry(entry):
        async_add_entities([WinterMaxOpenNumber(coordinator)])
    else:
        async_add_entities([NotifyDelayNumber(coordinator)])


class NotifyDelayNumber(CoordinatorEntity[WindowAiringCoordinator], RestoreNumber):
    """How long a window must stay open before a notification is sent.

    The value lives here (restored across restarts) and is pushed to the
    coordinator, which reads it to gate the airing and rain notifications.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "notify_delay"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = NOTIFY_DELAY_MAX_MIN
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: WindowAiringCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_notify_delay"
        self._attr_device_info = coordinator.device_info
        self._attr_native_value = DEFAULT_NOTIFY_DELAY / 60

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        # Push the effective value to the coordinator (restored or default).
        self.coordinator.notify_delay_s = int(self._attr_native_value * 60)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.coordinator.notify_delay_s = int(value * 60)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class WinterMaxOpenNumber(CoordinatorEntity[WindowAiringHouse], RestoreNumber):
    """How long a window may stay open in winter before the alert.

    Shared by every room. The value lives here (restored across restarts) and
    is pushed to the house coordinator, which the rooms read.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "winter_max_open"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-alert-outline"
    _attr_native_min_value = 1
    _attr_native_max_value = NOTIFY_DELAY_MAX_MIN
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: WindowAiringHouse) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_winter_max_open"
        self._attr_device_info = coordinator.device_info
        self._attr_native_value = DEFAULT_WINTER_MAX_OPEN / 60

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self.coordinator.winter_max_open_s = int(self._attr_native_value * 60)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.coordinator.winter_max_open_s = int(value * 60)
        self.async_write_ha_state()
        self.coordinator.async_notify_rooms()
