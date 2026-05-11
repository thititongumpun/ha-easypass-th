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
    DATA_CARD,
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
    """Set up Easy Pass sensors from a config entry."""
    coordinator: EasyPassCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            EasyPassBalanceSensor(coordinator, entry),
            EasyPassLicenseSensor(coordinator, entry),
            EasyPassSerialSensor(coordinator, entry),
            EasyPassOwnerSensor(coordinator, entry),
            EasyPassMflowSensor(coordinator, entry),
            EasyPassLastUpdateSensor(coordinator, entry),
            EasyPassLastTopupSensor(coordinator, entry),
            EasyPassMonthlySpendSensor(coordinator, entry),
            EasyPassLastTollLocationSensor(coordinator, entry),
        ]
    )


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class EasyPassSensorBase(CoordinatorEntity[EasyPassCoordinator], SensorEntity):
    """
    Common base for all Easy Pass sensors.

    Each sensor reads from coordinator.data[DATA_CARD] (an EasyPassCard).
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
        sensor_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_key = sensor_key
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_name = SENSOR_NAMES[sensor_key]
        self._attr_icon = SENSOR_ICONS[sensor_key]

    @property
    def device_info(self) -> DeviceInfo:
        """Group all sensors under one device card in HA device registry."""
        card: Optional[EasyPassCard] = self._card
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Easy Pass – {self._entry.data.get(CONF_USERNAME, '')}",
            manufacturer=MANUFACTURER,
            model="Easy Pass Card",
            sw_version="1.0.0",
            # Serial doubles as the device HW identifier once scraped
            serial_number=card.serial_number if card else None,
        )

    @property
    def _card(self) -> Optional[EasyPassCard]:
        """Shortcut to the EasyPassCard from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(DATA_CARD)


# ---------------------------------------------------------------------------
# Concrete sensors
# ---------------------------------------------------------------------------


class EasyPassBalanceSensor(EasyPassSensorBase):
    """Current balance in THB."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_BALANCE)
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
            attrs["recent_transactions"] = [
                {
                    "date": t.txn_date,
                    "location": t.location,
                    "type": t.txn_desc,
                    "amount": t.txn_amt,
                    "balance_after": t.txn_balance,
                }
                for t in card.usage_history[-10:]
            ]
        return attrs


class EasyPassLicenseSensor(EasyPassSensorBase):
    """Thai vehicle license plate associated with the card."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_LICENSE)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        return card.license_plate if card else None


class EasyPassSerialSensor(EasyPassSensorBase):
    """Card serial / tag number."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_SERIAL)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        return card.serial_number if card else None


class EasyPassLastUpdateSensor(EasyPassSensorBase):
    """Date of the most recent toll transaction."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_LAST_UPDATE)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        if card and card.last_toll:
            return card.last_toll.txn_date
        return card.last_transaction_date if card else None


class EasyPassLastTopupSensor(EasyPassSensorBase):
    """Amount of the most recent top-up."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_LAST_TOPUP)
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

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_OWNER)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        return card.owner_name if card else None


class EasyPassMflowSensor(EasyPassSensorBase):
    """M-Flow registration status message."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_MFLOW)

    @property
    def native_value(self) -> Optional[str]:
        card = self._card
        return card.mflow_message if card else None


class EasyPassMonthlySpendSensor(EasyPassSensorBase):
    """Total toll charges for the current month from usage history."""

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_MONTHLY_SPEND)
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

    def __init__(self, coordinator: EasyPassCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SENSOR_LAST_TOLL_LOCATION)

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
