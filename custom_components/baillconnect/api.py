"""BaillConnect API client — pure HTTP, no HA dependency."""
from __future__ import annotations

import logging
import re
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

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Mimic a real browser to avoid 404/403 from basic bot-protection
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


class BaillConnectClient:
    """Async HTTP client for the BaillConnect cloud API."""

    def __init__(
        self,
        email: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._external_session = session is not None
        self._session: aiohttp.ClientSession | None = session
        self._csrf_token: str | None = None
        self._discovered_regulation_id: int | None = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._external_session = False
        return self._session

    async def close(self) -> None:
        """Close the underlying aiohttp session (only if we own it)."""
        if not self._external_session and self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

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

        # 1. GET /client/connexion to fetch the CSRF token from the login form
        try:
            async with session.get(
                LOGIN_URL,
                allow_redirects=True,
                timeout=REQUEST_TIMEOUT,
                headers=BROWSER_HEADERS,
            ) as resp:
                _LOGGER.debug("GET %s -> HTTP %s", LOGIN_URL, resp.status)
                if resp.status != 200:
                    raise BaillConnectConnectionError(
                        f"Login page returned HTTP {resp.status}"
                    )
                html = await resp.text()
        except aiohttp.ClientError as exc:
            raise BaillConnectConnectionError(f"Network error: {exc}") from exc

        soup = BeautifulSoup(html, "html.parser")
        # Try hidden _token input first (most reliable), then meta tag
        token_input = soup.find("input", attrs={"name": "_token"})
        if token_input and token_input.get("value"):
            self._csrf_token = str(token_input["value"])
        else:
            meta = soup.find("meta", attrs={"name": "csrf-token"})
            if meta and meta.get("content"):
                self._csrf_token = str(meta["content"])
        if not self._csrf_token:
            raise BaillConnectConnectionError("CSRF token not found on login page")
        _LOGGER.debug("CSRF token fetched (len=%d)", len(self._csrf_token))

        # 2. POST credentials
        payload = {
            "email": self._email,
            "password": self._password,
            "_token": self._csrf_token,
        }
        try:
            async with session.post(
                LOGIN_URL,
                data=payload,
                allow_redirects=False,   # 302 redirect = login success
                timeout=REQUEST_TIMEOUT,
                headers={
                    **BROWSER_HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": LOGIN_URL,
                    "Origin": BASE_URL,
                },
            ) as resp:
                _LOGGER.debug(
                    "Login POST status=%s Location=%s",
                    resp.status,
                    resp.headers.get("Location", "-"),
                )
                if resp.status in (401, 403):
                    raise BaillConnectAuthError("Invalid credentials")
                if resp.status == 200:
                    raise BaillConnectAuthError(
                        "Login returned 200 (credentials rejected or CSRF mismatch)"
                    )
                if resp.status not in (301, 302, 303, 307, 308):
                    raise BaillConnectConnectionError(
                        f"Unexpected login response HTTP {resp.status}"
                    )
                location = resp.headers.get("Location", "")

        except aiohttp.ClientError as exc:
            raise BaillConnectConnectionError(f"Network error during login: {exc}") from exc

        # Extract regulation ID from redirect URL (e.g. /client/regulations/2153)
        if location:
            m = re.search(r"/regulations/(\d+)", location)
            if m:
                self._discovered_regulation_id = int(m.group(1))
                _LOGGER.debug(
                    "Regulation ID discovered from login redirect: %d",
                    self._discovered_regulation_id,
                )

        # Follow the redirect to refresh the CSRF token for API calls
        if location:
            redirect_url = location if location.startswith("http") else f"{BASE_URL}{location}"
            try:
                async with session.get(
                    redirect_url,
                    allow_redirects=True,
                    timeout=REQUEST_TIMEOUT,
                    headers=BROWSER_HEADERS,
                ) as resp2:
                    if resp2.status == 200:
                        html2 = await resp2.text()
                        soup2 = BeautifulSoup(html2, "html.parser")
                        meta2 = soup2.find("meta", attrs={"name": "csrf-token"})
                        if meta2 and meta2.get("content"):
                            self._csrf_token = str(meta2["content"])
                            _LOGGER.debug("CSRF token refreshed after login")
            except aiohttp.ClientError:
                pass  # Non-fatal

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
                    timeout=REQUEST_TIMEOUT,
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
                    raw = await resp.json()
                    # API wraps response in {"data": {...}}
                    inner = raw.get("data", raw)
                    return RegulationState.from_dict(inner)

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
        """After login, try to find the regulation ID.

        Primary strategy: the login redirect URL contains /client/regulations/{id},
        captured during login() and stored in self._discovered_regulation_id.

        Fallback: navigate to /client/espaces or parse the authenticated page.
        """
        # Fast path: captured from login redirect
        if self._discovered_regulation_id:
            return self._discovered_regulation_id

        # Fallback: navigate to the authenticated regulations page
        session = self._ensure_session()
        for path in ("/client/espaces", "/client/regulations"):
            try:
                async with session.get(
                    f"{BASE_URL}{path}",
                    headers=BROWSER_HEADERS,
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        continue
                    # Check final URL for regulation ID
                    final_url = str(resp.url)
                    m = re.search(r"/regulations/(\d+)", final_url)
                    if m:
                        reg_id = int(m.group(1))
                        self._discovered_regulation_id = reg_id
                        return reg_id
                    # Check page HTML
                    html = await resp.text()
            except aiohttp.ClientError:
                continue

            for pattern in (
                r"/client/regulations/(\d+)",
                r"/api-client/regulations/(\d+)",
                r"regulationId[\"']?\s*[:=]\s*(\d+)",
                r"regulation_id[\"']?\s*[:=]\s*(\d+)",
            ):
                m = re.search(pattern, html)
                if m:
                    reg_id = int(m.group(1))
                    self._discovered_regulation_id = reg_id
                    return reg_id

        _LOGGER.warning("Could not auto-discover regulation ID")
        return None
