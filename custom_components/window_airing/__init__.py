"""The Window Airing integration.

One config entry == one room (area). The integration discovers the room's
window contacts, temperature sensors and climate entities, computes the
indoor/outdoor delta and a temperature trend, drives the climate on/off, and
fires `window_airing_alert` events for the notification blueprint to consume.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import WindowAiringCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Window Airing from a config entry."""
    coordinator = WindowAiringCoordinator(hass, entry)
    await coordinator.async_setup()
    # First refresh runs discovery + a full evaluation.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload on options change so new thresholds / overrides take effect.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: WindowAiringCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
