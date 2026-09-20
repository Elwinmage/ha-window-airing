"""Sensor entities: indoor/outdoor delta and indoor average temperature."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WindowAiringCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WindowAiringCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            WindowAiringDeltaSensor(coordinator),
            WindowAiringIndoorSensor(coordinator),
        ]
    )


class _Base(CoordinatorEntity[WindowAiringCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: WindowAiringCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info


class WindowAiringDeltaSensor(_Base):
    _attr_translation_key = "delta"
    _attr_icon = "mdi:thermometer-lines"

    def __init__(self, coordinator: WindowAiringCoordinator) -> None:
        super().__init__(coordinator, "delta")

    @property
    def native_value(self):
        return self.coordinator.data.get("delta")

    @property
    def extra_state_attributes(self):
        # Everything a chips card needs to render one room, keyed by area.
        # `wa_room` is a stable marker to find these sensors from a template.
        d = self.coordinator.data
        return {
            "wa_room": True,
            "area_id": self.coordinator.area_id,
            "area_name": self.coordinator.area_name,
            "windows_open": d.get("windows_open"),
            "windows_total": d.get("windows_total"),
            "indoor": d.get("indoor"),
            "outdoor": d.get("outdoor"),
            "raining": d.get("raining"),
            "airing": bool(d.get("airing_reasons")),
            "reasons": d.get("airing_reasons", []),
        }


class WindowAiringIndoorSensor(_Base):
    _attr_translation_key = "indoor"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WindowAiringCoordinator) -> None:
        super().__init__(coordinator, "indoor")

    @property
    def native_value(self):
        return self.coordinator.data.get("indoor")

    @property
    def extra_state_attributes(self):
        return {"sensors": self.coordinator.indoor_sensors}
