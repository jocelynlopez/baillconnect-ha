"""Config flow for BaillConnect integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .api import BaillConnectAuthError, BaillConnectClient, BaillConnectConnectionError
from .const import CONF_REGULATION_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_REGULATION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGULATION_ID): vol.Coerce(int),
    }
)


class BaillConnectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the BaillConnect config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str = ""
        self._password: str = ""
        self._client: BaillConnectClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1 — collect email + password, attempt login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]

            client = BaillConnectClient(self._email, self._password)
            try:
                await client.login()
            except BaillConnectAuthError:
                errors["base"] = "invalid_auth"
            except BaillConnectConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                self._client = client

                # Try auto-discovery
                regulation_id = await client.discover_regulation_id()
                if regulation_id is not None:
                    await self.async_set_unique_id(
                        f"{DOMAIN}_{self._email}_{regulation_id}"
                    )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"BaillConnect ({self._email})",
                        data={
                            CONF_EMAIL: self._email,
                            CONF_PASSWORD: self._password,
                            CONF_REGULATION_ID: regulation_id,
                        },
                    )

                # Auto-discovery failed — ask user
                return await self.async_step_regulation()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_regulation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2 (fallback) — manual regulation ID entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            regulation_id: int = user_input[CONF_REGULATION_ID]

            # Validate by fetching state
            if self._client is not None:
                try:
                    await self._client.get_state(regulation_id)
                except BaillConnectAuthError:
                    errors["base"] = "invalid_auth"
                except BaillConnectConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error validating regulation ID")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(
                        f"{DOMAIN}_{self._email}_{regulation_id}"
                    )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"BaillConnect ({self._email})",
                        data={
                            CONF_EMAIL: self._email,
                            CONF_PASSWORD: self._password,
                            CONF_REGULATION_ID: regulation_id,
                        },
                    )

        return self.async_show_form(
            step_id="regulation",
            data_schema=STEP_REGULATION_SCHEMA,
            errors=errors,
            description_placeholders={
                "help_url": "https://github.com/jocelynlopez/baillconnect-ha#trouver-regulation-id"
            },
        )
