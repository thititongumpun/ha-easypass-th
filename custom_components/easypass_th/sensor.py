"""Sensor platform for Thailand Easy Pass."""

from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    SENSOR_BALANCE,
    SENSOR_ICONS,
    SENSOR_LAST_TOLL_LOCATION,
    SENSOR_LAST_TOPUP,
    SENSOR_LAST_UPDATE,
    SENSOR_LICENSE,
    SENSOR_MFLOW,
    SENSOR_MONTHLY_SPEND,
    SENSOR_NAMES,
    SENSOR_OWNER,
    SENSOR_REWARD_POINTS,
    SENSOR_SERIAL,
)
from .coordinator import EasyPassCoordinator
from .models import EasyPassCard

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Easy Pass sensors from a config entry – one device per card.

    A coordinator listener runs on every poll so newly added cards get
    entities automatically without requiring a reload.
    """
    coordinator: EasyPassCoordinator = hass.data[DOMAIN][entry.entry_id]

    known_card_ids: set[str] = set()

    def _add_new_cards() -> None:
        new_entities: list[EasyPassSensorBase] = []
        for idx, card in enumerate(coordinator.data or []):
            card_id = card.serial_number or f"{entry.entry_id}_{idx}"
            if card_id not in known_card_ids:
                known_card_ids.add(card_id)
                for cls in _SENSOR_CLASSES:
                    new_entities.append(cls(coordinator, entry, card_id))
        if new_entities:
            async_add_entities(new_entities)

    # Register listener first so it fires on every coordinator refresh.
    entry.async_on_unload(coordinator.async_add_listener(_add_new_cards))

    # Seed entities from data already loaded by async_config_entry_first_refresh.
    _add_new_cards()


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class EasyPassSensorBase(CoordinatorEntity[EasyPassCoordinator], SensorEntity):
    """
    Common base for all Easy Pass sensors.

    Each instance is tied to one card (identified by card_id = serial number).
    CoordinatorEntity handles:
      - Subscribing to coordinator updates
      - Setting available=False when the coordinator fails
      - Calling async_write_ha_state() automatically on updates
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EasyPassCoordinator,
        entry: ConfigEntry,
        card_id: str,
        sensor_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._card_id = card_id
        self._sensor_key = sensor_key
        # unique_id includes card_id so each card's sensors are independent
        self._attr_unique_id = f"{entry.entry_id}_{card_id}_{sensor_key}"
        self._attr_name = SENSOR_NAMES[sensor_key]
        self._attr_icon = SENSOR_ICONS[sensor_key]

    @property
    def device_info(self) -> DeviceInfo:
        """One HA device per card, identified by serial number."""
        card = self._card
        plate = (card.license_plate if card else "") or self._card_id
        return DeviceInfo(
            identifiers={(DOMAIN, self._card_id)},
            name=f"Easy Pass – {plate}",
            manufacturer=MANUFACTURER,
            model="Easy Pass Card",
            sw_version="1.0.0",
            serial_number=card.serial_number if card else None,
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def _card(self) -> Optional[EasyPassCard]:
        """Find this sensor's card in the current coordinator data."""
        if not self.coordinator.data:
            return None
        for card in self.coordinator.data:
            if (card.serial_number or "") == self._card_id:
                return card
        # Fall back by position encoded in card_id ({entry_id}_{idx})
        suffix = self._card_id.replace(f"{self._entry.entry_id}_", "")
        if suffix.isdigit():
            idx = int(suffix)
            if idx < len(self.coordinator.data):
                return self.coordinator.data[idx]
        return None


# ---------------------------------------------------------------------------
# Concrete sensors
# ---------------------------------------------------------------------------


class EasyPassBalanceSensor(EasyPassSensorBase):
    """Current balance in THB."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_BALANCE)
        self._attr_native_unit_of_measurement = "THB"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> Optional[float]:
        card = self._card
        return card.balance if card else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        card = self._card
        if not card:
            return {}
        attrs: dict[str, Any] = {
            "serial_number": card.serial_number,
            "license_plate": card.license_plate,
            "owner_name": card.owner_name,
        }
        if card.usage_history:
            attrs["transactions"] = [
                {
                    "no": t.row_id,
                    "date": t.txn_date,
                    "type": t.txn_desc,
                    "amount": t.txn_amt,
                    "balance_after": t.txn_balance,
                    "location": t.location,
                }
                for t in card.usage_history
            ]
        return attrs


class EasyPassLicenseSensor(EasyPassSensorBase):
    """Thai vehicle license plate associated with the card."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_LICENSE)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        return card.license_plate if card else None


class EasyPassSerialSensor(EasyPassSensorBase):
    """Card serial / tag number."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_SERIAL)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        return card.serial_number if card else None


class EasyPassLastUpdateSensor(EasyPassSensorBase):
    """Date of the most recent toll transaction."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_LAST_UPDATE)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        if card and card.last_toll:
            return card.last_toll.txn_date
        return card.last_transaction_date if card else None


class EasyPassLastTopupSensor(EasyPassSensorBase):
    """Amount of the most recent top-up."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_LAST_TOPUP)
        self._attr_native_unit_of_measurement = "THB"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> Optional[float]:
        card = self._card
        if card and card.last_topup:
            return card.last_topup.txn_amt
        return card.last_topup_amount if card else None


class EasyPassOwnerSensor(EasyPassSensorBase):
    """Account holder name."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_OWNER)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        return card.owner_name if card else None


class EasyPassMflowSensor(EasyPassSensorBase):
    """M-Flow registration status message."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_MFLOW)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        return card.mflow_message if card else None


class EasyPassMonthlySpendSensor(EasyPassSensorBase):
    """Total toll charges for the current month from usage history."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_MONTHLY_SPEND)
        self._attr_native_unit_of_measurement = "THB"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> Optional[float]:
        card = self._card
        if card is None:
            return None
        return card.monthly_toll_spend if card.usage_history else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        card = self._card
        if not card:
            return {}
        return {"transaction_count": sum(1 for t in card.usage_history if t.is_toll)}


class EasyPassLastTollLocationSensor(EasyPassSensorBase):
    """Location of the most recent toll passage."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_LAST_TOLL_LOCATION)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        if card and card.last_toll:
            return card.last_toll.location
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        card = self._card
        if not card or not card.last_toll:
            return {}
        t = card.last_toll
        return {
            "txn_date": t.txn_date,
            "amount": t.txn_amt,
            "balance_after": t.txn_balance,
        }


class EasyPassRewardPointsSensor(EasyPassSensorBase):
    """Reward points balance (คะแนน) — direct value from get-all API."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry, card_id: str) -> None:
        super().__init__(coordinator, entry, card_id, SENSOR_REWARD_POINTS)
        self._attr_native_unit_of_measurement = "คะแนน"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[int]:
        card = self._card
        return card.reward_points if card else None


# Ordered list used by async_setup_entry to create all sensors per card
_SENSOR_CLASSES = [
    EasyPassBalanceSensor,
    EasyPassLicenseSensor,
    EasyPassSerialSensor,
    EasyPassOwnerSensor,
    EasyPassMflowSensor,
    EasyPassLastUpdateSensor,
    EasyPassLastTopupSensor,
    EasyPassMonthlySpendSensor,
    EasyPassLastTollLocationSensor,
    EasyPassRewardPointsSensor,
]
