"""
DataUpdateCoordinator for Thailand Easy Pass.

POLLING ARCHITECTURE
--------------------
HA calls coordinator.async_request_refresh() every SCAN_INTERVAL minutes.
The coordinator runs _async_update_data() which:
  1. Calls loop.run_in_executor(None, scraper.fetch_cards)
     → offloads blocking I/O to a thread pool, never blocking the event loop.
  2. Returns list[EasyPassCard] – one entry per card on the account.
  3. All sensor entities subscribe to coordinator updates via CoordinatorEntity;
     they automatically re-render whenever new data arrives.

ANTI-LOGIN-LOOP PROTECTION
---------------------------
The scraper already caps login retries at MAX_LOGIN_RETRIES.
The coordinator additionally raises ConfigEntryAuthFailed on auth errors,
which tells HA to stop polling and notify the user to re-enter credentials.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HISTORY_DAYS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .models import EasyPassCard
from .scraper import (
    EasyPassAuthError,
    EasyPassConnectionError,
    EasyPassScraper,
)

_LOGGER = logging.getLogger(__name__)


class EasyPassCoordinator(DataUpdateCoordinator[list[EasyPassCard]]):
    """Manages polling and data distribution for one Easy Pass account."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._scraper = EasyPassScraper(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> list[EasyPassCard]:
        """
        Fetch new data.  Called by the coordinator framework automatically.
        Returns list[EasyPassCard] – one entry per registered card.
        """
        history_days: int = self._entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
        try:
            cards: list[EasyPassCard] = await self.hass.async_add_executor_job(
                self._scraper.fetch_cards, history_days
            )
        except EasyPassAuthError as exc:
            # Stops polling; HA shows a "re-authenticate" notification
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except EasyPassConnectionError as exc:
            # Temporary failure – coordinator will retry at next interval
            raise UpdateFailed(f"Connection error: {exc}") from exc

        return cards

    async def async_shutdown(self) -> None:
        """Clean up the underlying requests session."""
        await self.hass.async_add_executor_job(self._scraper.close)
        await super().async_shutdown()
