"""Select platform – exposes transaction history range as a controllable HA entity."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_HISTORY_DAYS,
    DEFAULT_HISTORY_DAYS,
    DOMAIN,
    HISTORY_DAYS_OPTIONS,
)
from .coordinator import EasyPassCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EasyPassCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EasyPassHistorySelect(hass, entry, card.serial_number or f"{entry.entry_id}_{i}")
        for i, card in enumerate(coordinator.data or [])
    ]
    if entities:
        async_add_entities(entities)


class EasyPassHistorySelect(SelectEntity):
    """Select entity for the transaction history window (7 / 30 / 90 days)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:history"
    _attr_name = "History Range"
    _attr_options = [str(d) for d in HISTORY_DAYS_OPTIONS]

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, card_id: str) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{card_id}_history_days"
        # Use the same device identifier as the sensors for this card
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, card_id)},
        )

    @property
    def current_option(self) -> str:
        return str(self._entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS))

    async def async_select_option(self, option: str) -> None:
        new_options = {**self._entry.options, CONF_HISTORY_DAYS: int(option)}
        self._hass.config_entries.async_update_entry(self._entry, options=new_options)
