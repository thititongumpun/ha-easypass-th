"""
Thailand Easy Pass – Home Assistant Custom Integration.

Entry-point called by HA when the integration is loaded.

LIFECYCLE
---------
async_setup_entry   → creates coordinator, does first refresh, forwards to platforms
async_unload_entry  → unloads platforms, shuts down coordinator
async_reload_entry  → called after re-auth succeeds (default HA behaviour)
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import EasyPassCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Easy Pass from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = EasyPassCoordinator(hass, entry)

    # First refresh: raises ConfigEntryNotReady on connection failure so HA
    # will retry setup automatically (with exponential back-off).
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        raise ConfigEntryNotReady(f"Unable to connect to Easy Pass: {exc}") from exc

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register a reload listener so option changes take effect immediately
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry cleanly."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        coordinator: EasyPassCoordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator:
            await coordinator.async_shutdown()

    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when the config entry is updated (e.g. re-auth)."""
    await hass.config_entries.async_reload(entry.entry_id)
