"""Sensor entities: room delta, indoor average, sources; house heating time."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, is_house_entry
from .coordinator import WindowAiringCoordinator
from .house import WindowAiringHouse


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if is_house_entry(entry):
        async_add_entities(
            [HeatingTodaySensor(coordinator), HouseSourcesSensor(coordinator)]
        )
        return
    async_add_entities(
        [
            WindowAiringDeltaSensor(coordinator),
            WindowAiringIndoorSensor(coordinator),
            WindowAiringSourcesSensor(coordinator),
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
            "winter": d.get("winter"),
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


# Attributes of the sources sensor: lists of entity ids that rarely change,
# kept out of the recorder so they do not bloat the database.
_SOURCES_ATTRS = frozenset(
    {
        "windows",
        "windows_source",
        "indoor_sensors",
        "indoor_sensors_source",
        "climates",
        "climates_source",
        "exterior_temp",
        "rain_sensor",
        "weather",
        "excluded",
        "area_id",
    }
)


class WindowAiringSourcesSensor(CoordinatorEntity[WindowAiringCoordinator], SensorEntity):
    """Diagnostic: how many entities the room relies on, listed in attributes.

    State = number of distinct entities used (windows, indoor sensors,
    climates, outdoor/rain/weather sources). Attributes give the lists per
    role, whether each role comes from auto-discovery or an override, and the
    area entities that discovery dropped (with the reason).
    """

    _attr_has_entity_name = True
    _attr_translation_key = "sources"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:format-list-checks"
    _unrecorded_attributes = _SOURCES_ATTRS

    def __init__(self, coordinator: WindowAiringCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_sources"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int:
        return len(self.coordinator.used_entities())

    @property
    def extra_state_attributes(self):
        return {
            "area_id": self.coordinator.area_id,
            **self.coordinator.discovery_summary(),
        }


class HeatingTodaySensor(CoordinatorEntity[WindowAiringHouse], SensorEntity):
    """Diagnostic: heating time today, what the automatic winter switch counts."""

    _attr_has_entity_name = True
    _attr_translation_key = "heating_today"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: WindowAiringHouse) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_heating_today"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        return self.coordinator.data.get("heating_minutes")

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        return {
            "heating_now": d.get("heating_now"),
            "days_without_heating": d.get("idle_days"),
        }


class HouseSourcesSensor(CoordinatorEntity[WindowAiringHouse], SensorEntity):
    """Diagnostic: the climates the automatic season change relies on."""

    _attr_has_entity_name = True
    _attr_translation_key = "sources"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:format-list-checks"
    _unrecorded_attributes = frozenset({"climates"})

    def __init__(self, coordinator: WindowAiringHouse) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_sources"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int:
        return len(self.coordinator.climates)

    @property
    def extra_state_attributes(self):
        return {"climates": self.coordinator.climates}
