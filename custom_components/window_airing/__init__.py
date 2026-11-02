"""The Window Airing integration.

One config entry == one room (area). The integration discovers the room's
window contacts, temperature sensors and climate entities, computes the
indoor/outdoor delta and a temperature trend, drives the climate on/off, and
fires `window_airing_alert` events for the notification blueprint to consume.

One optional extra entry stands for the whole home: it owns the winter switch
and its automatic season changes, which the rooms read.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DATA_HOUSE,
    DOMAIN,
    HOUSE_PLATFORMS,
    PLATFORMS,
    STORAGE_VERSION,
    is_house_entry,
)
from .coordinator import WindowAiringCoordinator
from .house import WindowAiringHouse

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Window Airing from a config entry."""
    if is_house_entry(entry):
        return await _async_setup_house(hass, entry)

    coordinator = WindowAiringCoordinator(hass, entry)
    await coordinator.async_setup()
    # First refresh runs discovery + a full evaluation.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload on options change so new thresholds / overrides take effect.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_setup_house(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the home-wide entry and hand the season over to the rooms."""
    house = WindowAiringHouse(hass, entry)
    await house.async_setup()
    await house.async_config_entry_first_refresh()

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = house
    await hass.config_entries.async_forward_entry_setups(entry, HOUSE_PLATFORMS)

    # Published last: rooms wait for it, and the number entity has now restored
    # the maximum open time they will read.
    domain_data[DATA_HOUSE] = house
    house.async_notify_rooms()

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    house = is_house_entry(entry)
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, HOUSE_PLATFORMS if house else PLATFORMS
    )
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if house:
            hass.data[DOMAIN].pop(DATA_HOUSE, None)
        await coordinator.async_shutdown()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the persisted state store when the room is removed."""
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
    await store.async_remove()
