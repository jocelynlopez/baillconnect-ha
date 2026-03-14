"""BaillConnect API client — pure HTTP, no HA dependency."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    API_URL,
    BASE_URL,
    HEADER_CSRF,
    HEADER_XHR,
    HEADER_XHR_VALUE,
    LOGIN_URL,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class BaillConnectAuthError(Exception):
    """Raised when authentication fails (401/403 or bad credentials)."""


class BaillConnectConnectionError(Exception):
    """Raised on network errors or unexpected HTTP responses."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ThermostatState:
    id: int
    key: str
    name: str
    temperature: float
    zone: int
    is_on: bool
    setpoint_hot_t1: float
    setpoint_hot_t2: float
    setpoint_cool_t1: float
    setpoint_cool_t2: float
    t1_t2: int                 # 1=confort, 2=eco
    motor_state: int
    is_battery_low: bool
    is_connected: bool
    connected_at_text: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThermostatState":
        return cls(
            id=int(data["id"]),
            key=str(data.get("key", "")),
            name=str(data.get("name", "")),
            temperature=float(data.get("temperature", 0.0)),
            zone=int(data.get("zone", 1)),
            is_on=bool(data.get("is_on", False)),
            setpoint_hot_t1=float(data.get("setpoint_hot_t1", 20.0)),
            setpoint_hot_t2=float(data.get("setpoint_hot_t2", 18.0)),
            setpoint_cool_t1=float(data.get("setpoint_cool_t1", 26.0)),
            setpoint_cool_t2=float(data.get("setpoint_cool_t2", 28.0)),
            t1_t2=int(data.get("t1_t2", 1)),
            motor_state=int(data.get("motor_state", 0)),
            is_battery_low=bool(data.get("is_battery_low", False)),
            is_connected=bool(data.get("is_connected", False)),
            connected_at_text=str(data.get("connected_at_text", "")),
        )


@dataclass
class ZoneState:
    id: int
    name: str
    schedule: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZoneState":
        schedule = {
            k: v
            for k, v in data.items()
            if k.startswith("schedule_")
        }
        return cls(
            id=int(data["id"]),
            name=str(data.get("name", "")),
            schedule=schedule,
        )


@dataclass
class RegulationState:
    uc_mode: int
    ui_on: bool
    ui_fan: int
    ui_sp: float
    ui_has_error: bool
    ui_error: int
    is_connected: bool
    uc_hot_min: float
    uc_hot_max: float
    uc_cold_min: float
    uc_cold_max: float
    temp_diff: float
    thermostats: list[ThermostatState]
    zones: list[ZoneState]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegulationState":
        thermostats = [
            ThermostatState.from_dict(t)
            for t in data.get("thermostats", [])
        ]
        zones = [
            ZoneState.from_dict(z)
            for z in data.get("zones", [])
        ]
        return cls(
            uc_mode=int(data.get("uc_mode", 0)),
            ui_on=bool(data.get("ui_on", False)),
            ui_fan=int(data.get("ui_fan", 0)),
            ui_sp=float(data.get("ui_sp", 20.0)),
            ui_has_error=bool(data.get("ui_has_error", False)),
            ui_error=int(data.get("ui_error", 0)),
            is_connected=bool(data.get("is_connected", False)),
            uc_hot_min=float(data.get("uc_hot_min", 16.0)),
            uc_hot_max=float(data.get("uc_hot_max", 30.0)),
            uc_cold_min=float(data.get("uc_cold_min", 16.0)),
            uc_cold_max=float(data.get("uc_cold_max", 30.0)),
            temp_diff=float(data.get("temp_diff", 1.0)),
            thermostats=thermostats,
            zones=zones,
        )


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

class BaillConnectClient:
    """Async HTTP client for the BaillConnect cloud API."""

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._csrf_token: str | None = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # CSRF helpers
    # ------------------------------------------------------------------

    async def _fetch_csrf_token(self) -> str:
        """Fetch CSRF token from the homepage meta tag."""
        session = self._ensure_session()
        try:
            async with session.get(BASE_URL, allow_redirects=True) as resp:
                if resp.status != 200:
                    raise BaillConnectConnectionError(
                        f"Homepage returned HTTP {resp.status}"
                    )
                html = await resp.text()
        except aiohttp.ClientError as exc:
            raise BaillConnectConnectionError(f"Network error: {exc}") from exc

        soup = BeautifulSoup(html, "html.parser")
        meta = soup.find("meta", attrs={"name": "csrf-token"})
        if not meta or not meta.get("content"):
            raise BaillConnectConnectionError(
                "CSRF token not found in page meta tags"
            )
        token = str(meta["content"])
        _LOGGER.debug("CSRF token fetched (len=%d)", len(token))
        return token

    def _api_headers(self) -> dict[str, str]:
        headers = {
            HEADER_XHR: HEADER_XHR_VALUE,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._csrf_token:
            headers[HEADER_CSRF] = self._csrf_token
        return headers

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self) -> bool:
        """Authenticate and store the session cookie.

        Returns True on success, raises BaillConnectAuthError on bad
        credentials, BaillConnectConnectionError on network issues.
        """
        session = self._ensure_session()

        # 1. Get CSRF token
        self._csrf_token = await self._fetch_csrf_token()

        # 2. POST login
        payload = {
            "email": self._email,
            "password": self._password,
            "_token": self._csrf_token,
        }
        try:
            async with session.post(
                LOGIN_URL,
                data=payload,
                allow_redirects=True,
            ) as resp:
                if resp.status in (401, 403):
                    raise BaillConnectAuthError("Invalid credentials")
                if resp.status != 200:
                    raise BaillConnectConnectionError(
                        f"Login returned HTTP {resp.status}"
                    )
                # Refresh CSRF after login (new token in the new page)
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                meta = soup.find("meta", attrs={"name": "csrf-token"})
                if meta and meta.get("content"):
                    self._csrf_token = str(meta["content"])

        except aiohttp.ClientError as exc:
            raise BaillConnectConnectionError(f"Network error during login: {exc}") from exc

        _LOGGER.info("BaillConnect login successful for %s", self._email)
        return True

    # ------------------------------------------------------------------
    # State reading
    # ------------------------------------------------------------------

    async def get_state(self, regulation_id: int) -> RegulationState:
        """Fetch full regulation state (POST with empty body)."""
        return await self._post_regulation(regulation_id, {})

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def set_regulation(
        self, regulation_id: int, payload: dict[str, Any]
    ) -> RegulationState:
        """Write arbitrary regulation-level fields and return updated state."""
        return await self._post_regulation(regulation_id, payload)

    async def set_thermostat(
        self,
        regulation_id: int,
        thermostat_id: int,
        field: str,
        value: Any,
    ) -> None:
        """Write a single thermostat field using dot-notation key."""
        dot_key = f"thermostats.{thermostat_id}.{field}"
        await self._post_regulation(regulation_id, {dot_key: value})

    async def set_mode(self, regulation_id: int, mode: int) -> None:
        """Change the global uc_mode."""
        await self._post_regulation(regulation_id, {"uc_mode": mode})

    # ------------------------------------------------------------------
    # Low-level POST
    # ------------------------------------------------------------------

    async def _post_regulation(
        self, regulation_id: int, body: dict[str, Any]
    ) -> RegulationState:
        """POST to the regulation endpoint; handles auth refresh on 401/403."""
        url = f"{API_URL}/{regulation_id}"
        session = self._ensure_session()

        for attempt in range(2):
            try:
                async with session.post(
                    url,
                    json=body,
                    headers=self._api_headers(),
                ) as resp:
                    if resp.status in (401, 403):
                        if attempt == 0:
                            _LOGGER.warning(
                                "Session expired (HTTP %s), re-logging in…",
                                resp.status,
                            )
                            await self.login()
                            continue
                        raise BaillConnectAuthError(
                            f"Re-authentication failed (HTTP {resp.status})"
                        )
                    if resp.status != 200:
                        raise BaillConnectConnectionError(
                            f"API returned HTTP {resp.status}"
                        )
                    data = await resp.json()
                    return RegulationState.from_dict(data)

            except aiohttp.ClientError as exc:
                raise BaillConnectConnectionError(
                    f"Network error calling {url}: {exc}"
                ) from exc

        # Should never be reached
        raise BaillConnectConnectionError("Max retries exceeded")

    # ------------------------------------------------------------------
    # Regulation discovery
    # ------------------------------------------------------------------

    async def discover_regulation_id(self) -> int | None:
        """After login, try to find the regulation ID from the dashboard page."""
        session = self._ensure_session()
        try:
            async with session.get(
                f"{BASE_URL}/dashboard",
                headers={HEADER_XHR: HEADER_XHR_VALUE},
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning(
                        "Dashboard returned HTTP %s during discovery", resp.status
                    )
                    return None
                html = await resp.text()
        except aiohttp.ClientError as exc:
            _LOGGER.error("Network error during regulation discovery: %s", exc)
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Strategy 1: data-regulation-id attribute anywhere in the page
        el = soup.find(attrs={"data-regulation-id": True})
        if el:
            try:
                return int(el["data-regulation-id"])
            except (ValueError, KeyError):
                pass

        # Strategy 2: look for /api-client/regulations/{id} in script tags
        import re
        for script in soup.find_all("script"):
            text = script.get_text()
            match = re.search(r"/api-client/regulations/(\d+)", text)
            if match:
                return int(match.group(1))

        # Strategy 3: look for regulationId or regulation_id in inline JS
        full_text = html
        for pattern in (
            r"regulationId[\"']?\s*[:=]\s*(\d+)",
            r"regulation_id[\"']?\s*[:=]\s*(\d+)",
        ):
            match = re.search(pattern, full_text)
            if match:
                return int(match.group(1))

        _LOGGER.warning("Could not auto-discover regulation ID from dashboard")
        return None
