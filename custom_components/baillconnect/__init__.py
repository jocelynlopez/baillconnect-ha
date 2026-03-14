"""BaillConnect integration for Home Assistant."""
from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import BaillConnectAuthError, BaillConnectClient, BaillConnectConnectionError
from .const import CONF_REGULATION_ID, DOMAIN, ENTRY_CLIENT, ENTRY_COORDINATOR
from .coordinator import BaillConnectCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BaillConnect from a config entry."""
    email: str = entry.data[CONF_EMAIL]
    password: str = entry.data[CONF_PASSWORD]
    regulation_id: int = entry.data[CONF_REGULATION_ID]

    # Dedicated session with its own cookie jar (required for auth cookies)
    session = aiohttp.ClientSession()
    client = BaillConnectClient(email, password, session=session)

    try:
        await client.login()
    except BaillConnectAuthError as exc:
        await session.close()
        raise ConfigEntryAuthFailed(f"Invalid credentials: {exc}") from exc
    except BaillConnectConnectionError as exc:
        await session.close()
        raise ConfigEntryNotReady(f"Cannot connect: {exc}") from exc
    except Exception as exc:
        await session.close()
        raise ConfigEntryNotReady(f"Unexpected error: {exc}") from exc

    coordinator = BaillConnectCoordinator(hass, client, regulation_id)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        ENTRY_CLIENT: client,
        ENTRY_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        client: BaillConnectClient | None = entry_data.get(ENTRY_CLIENT)
        if client:
            await client.close()
    return unload_ok
