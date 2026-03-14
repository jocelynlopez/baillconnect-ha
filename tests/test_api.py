"""Unit tests for BaillConnect API client."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.baillconnect.api import (
    BaillConnectAuthError,
    BaillConnectClient,
    BaillConnectConnectionError,
    RegulationState,
    ThermostatState,
    ZoneState,
)


# ---------------------------------------------------------------------------
# RegulationState.from_dict
# ---------------------------------------------------------------------------

MINIMAL_REGULATION = {
    "uc_mode": 2,
    "ui_on": True,
    "ui_fan": 0,
    "ui_sp": 20.0,
    "ui_has_error": False,
    "ui_error": 0,
    "is_connected": True,
    "uc_hot_min": 16.0,
    "uc_hot_max": 30.0,
    "uc_cold_min": 16.0,
    "uc_cold_max": 30.0,
    "temp_diff": 1.0,
    "thermostats": [],
    "zones": [],
}

MINIMAL_THERMOSTAT = {
    "id": 1,
    "key": "th1",
    "name": "Salon",
    "temperature": 21.5,
    "zone": 1,
    "is_on": True,
    "setpoint_hot_t1": 21.0,
    "setpoint_hot_t2": 18.0,
    "setpoint_cool_t1": 26.0,
    "setpoint_cool_t2": 28.0,
    "t1_t2": 1,
    "motor_state": 0,
    "is_battery_low": False,
    "is_connected": True,
    "connected_at_text": "",
}


class TestRegulationStateFromDict:
    def test_parses_uc_mode(self):
        state = RegulationState.from_dict(MINIMAL_REGULATION)
        assert state.uc_mode == 2

    def test_parses_ui_on(self):
        state = RegulationState.from_dict(MINIMAL_REGULATION)
        assert state.ui_on is True

    def test_parses_thermostats(self):
        data = dict(MINIMAL_REGULATION, thermostats=[MINIMAL_THERMOSTAT])
        state = RegulationState.from_dict(data)
        assert len(state.thermostats) == 1
        assert state.thermostats[0].id == 1
        assert state.thermostats[0].name == "Salon"

    def test_parses_zones(self):
        data = dict(
            MINIMAL_REGULATION,
            zones=[{"id": 1, "name": "Zone 1", "schedule_0_8": 1}],
        )
        state = RegulationState.from_dict(data)
        assert len(state.zones) == 1
        assert state.zones[0].schedule == {"schedule_0_8": 1}

    def test_defaults_on_missing_keys(self):
        state = RegulationState.from_dict({})
        assert state.uc_mode == 0
        assert state.ui_on is False


class TestThermostatStateFromDict:
    def test_all_fields(self):
        th = ThermostatState.from_dict(MINIMAL_THERMOSTAT)
        assert th.id == 1
        assert th.key == "th1"
        assert th.temperature == 21.5
        assert th.setpoint_hot_t1 == 21.0
        assert th.t1_t2 == 1

    def test_defaults(self):
        th = ThermostatState.from_dict({"id": 5})
        assert th.key == ""
        assert th.is_connected is False


# ---------------------------------------------------------------------------
# BaillConnectClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> BaillConnectClient:
    return BaillConnectClient("user@example.com", "secret")


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, client):
        """Login succeeds when the server returns CSRF token + 200 on login."""
        csrf_html = '<html><head><meta name="csrf-token" content="tok123"></head></html>'

        mock_get_resp = AsyncMock()
        mock_get_resp.status = 200
        mock_get_resp.text = AsyncMock(return_value=csrf_html)
        mock_get_resp.__aenter__ = AsyncMock(return_value=mock_get_resp)
        mock_get_resp.__aexit__ = AsyncMock(return_value=False)

        mock_post_resp = AsyncMock()
        mock_post_resp.status = 200
        mock_post_resp.text = AsyncMock(return_value=csrf_html)
        mock_post_resp.__aenter__ = AsyncMock(return_value=mock_post_resp)
        mock_post_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.get = MagicMock(return_value=mock_get_resp)
        mock_session.post = MagicMock(return_value=mock_post_resp)

        client._session = mock_session
        result = await client.login()
        assert result is True
        assert client._csrf_token == "tok123"

    @pytest.mark.asyncio
    async def test_login_raises_auth_error_on_401(self, client):
        csrf_html = '<html><head><meta name="csrf-token" content="tok123"></head></html>'

        mock_get_resp = AsyncMock()
        mock_get_resp.status = 200
        mock_get_resp.text = AsyncMock(return_value=csrf_html)
        mock_get_resp.__aenter__ = AsyncMock(return_value=mock_get_resp)
        mock_get_resp.__aexit__ = AsyncMock(return_value=False)

        mock_post_resp = AsyncMock()
        mock_post_resp.status = 401
        mock_post_resp.__aenter__ = AsyncMock(return_value=mock_post_resp)
        mock_post_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.get = MagicMock(return_value=mock_get_resp)
        mock_session.post = MagicMock(return_value=mock_post_resp)

        client._session = mock_session
        with pytest.raises(BaillConnectAuthError):
            await client.login()

    @pytest.mark.asyncio
    async def test_login_raises_connection_error_when_no_csrf(self, client):
        mock_get_resp = AsyncMock()
        mock_get_resp.status = 200
        mock_get_resp.text = AsyncMock(return_value="<html><head></head></html>")
        mock_get_resp.__aenter__ = AsyncMock(return_value=mock_get_resp)
        mock_get_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.get = MagicMock(return_value=mock_get_resp)

        client._session = mock_session
        with pytest.raises(BaillConnectConnectionError):
            await client.login()


class TestGetState:
    @pytest.mark.asyncio
    async def test_returns_regulation_state(self, client):
        client._csrf_token = "tok"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=MINIMAL_REGULATION)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)
        client._session = mock_session

        state = await client.get_state(regulation_id=42)
        assert isinstance(state, RegulationState)
        assert state.uc_mode == 2

    @pytest.mark.asyncio
    async def test_relogin_on_401(self, client):
        """On 401 the client should re-login and retry."""
        client._csrf_token = "tok"
        client.login = AsyncMock(return_value=True)

        ok_data = MINIMAL_REGULATION

        call_count = 0

        async def fake_post_ctx(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = AsyncMock()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            if call_count == 1:
                mock_resp.status = 401
            else:
                mock_resp.status = 200
                mock_resp.json = AsyncMock(return_value=ok_data)
            return mock_resp

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=fake_post_ctx)
        client._session = mock_session

        state = await client.get_state(42)
        assert isinstance(state, RegulationState)
        client.login.assert_called_once()


class TestSetThermostat:
    @pytest.mark.asyncio
    async def test_sends_dot_notation_key(self, client):
        client._csrf_token = "tok"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=MINIMAL_REGULATION)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)
        client._session = mock_session

        await client.set_thermostat(42, 1, "setpoint_hot_t1", 22.0)

        call_kwargs = mock_session.post.call_args
        body = call_kwargs[1]["json"]
        assert body == {"thermostats.1.setpoint_hot_t1": 22.0}
