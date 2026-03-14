"""DataUpdateCoordinator for BaillConnect."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    BaillConnectAuthError,
    BaillConnectClient,
    BaillConnectConnectionError,
    RegulationState,
)
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class BaillConnectCoordinator(DataUpdateCoordinator[RegulationState]):
    """Coordinator that polls the BaillConnect API every 30 seconds."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: BaillConnectClient,
        regulation_id: int,
    ) -> None:
        self.client = client
        self.regulation_id = regulation_id

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> RegulationState:
        """Fetch data from the API; re-login on auth errors."""
        try:
            return await self.client.get_state(self.regulation_id)
        except BaillConnectAuthError:
            _LOGGER.warning("Session expired — attempting re-login")
            try:
                await self.client.login()
            except BaillConnectAuthError as exc:
                raise UpdateFailed(f"Re-authentication failed: {exc}") from exc
            except BaillConnectConnectionError as exc:
                raise UpdateFailed(f"Connection error during re-login: {exc}") from exc
            # Retry after re-login
            try:
                return await self.client.get_state(self.regulation_id)
            except (BaillConnectAuthError, BaillConnectConnectionError) as exc:
                raise UpdateFailed(f"Failed after re-login: {exc}") from exc
        except BaillConnectConnectionError as exc:
            raise UpdateFailed(f"Communication error: {exc}") from exc
