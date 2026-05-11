"""Config Flow for Thailand Easy Pass."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_UNKNOWN,
)
from .scraper import (
    EasyPassAuthError,
    EasyPassConnectionError,
    EasyPassScraper,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate_credentials(hass, username: str, password: str) -> None:
    """
    Try to log in with supplied credentials.
    Raises EasyPassAuthError or EasyPassConnectionError on failure.
    """
    scraper = EasyPassScraper(username, password)
    try:
        # fetch_cards performs a full login + scrape round-trip
        await hass.async_add_executor_job(scraper.fetch_cards)
    finally:
        await hass.async_add_executor_job(scraper.close)


class EasyPassConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the UI setup flow for Easy Pass."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """First (and only) step: collect username + password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            # Prevent duplicate entries for the same account
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            try:
                await _validate_credentials(self.hass, username, password)
            except EasyPassAuthError:
                errors["base"] = ERROR_INVALID_AUTH
            except EasyPassConnectionError:
                errors["base"] = ERROR_CANNOT_CONNECT
            except Exception:
                _LOGGER.exception("Unexpected error during config flow validation")
                errors["base"] = ERROR_UNKNOWN

            if not errors:
                return self.async_create_entry(
                    title=f"Easy Pass ({username})",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Re-authentication flow – shown when ConfigEntryAuthFailed is raised.
        Preserves the existing config entry and just updates the password.
        """
        errors: dict[str, str] = {}
        existing_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            username = existing_entry.data[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                await _validate_credentials(self.hass, username, password)
            except EasyPassAuthError:
                errors["base"] = ERROR_INVALID_AUTH
            except EasyPassConnectionError:
                errors["base"] = ERROR_CANNOT_CONNECT
            except Exception:
                _LOGGER.exception("Unexpected error during re-auth")
                errors["base"] = ERROR_UNKNOWN

            if not errors:
                self.hass.config_entries.async_update_entry(
                    existing_entry,
                    data={**existing_entry.data, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(existing_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={
                "username": existing_entry.data.get(CONF_USERNAME, "")
            },
        )
