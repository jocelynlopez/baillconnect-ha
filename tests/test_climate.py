"""Unit tests for BaillConnect climate entities."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode

from custom_components.baillconnect.climate import BaillConnectClimate
from custom_components.baillconnect.const import (
    PRESET_COMFORT,
    PRESET_ECO,
    UC_MODE_COOL,
    UC_MODE_HEAT,
    UC_MODE_OFF,
)


def make_climate(thermostat, regulation_state):
    """Construct a BaillConnectClimate with a mocked coordinator."""
    coordinator = MagicMock()
    coordinator.data = regulation_state
    client = MagicMock()
    client.set_thermostat = AsyncMock()
    client.set_mode = AsyncMock()
    client.set_regulation = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return BaillConnectClimate(coordinator, client, 99, thermostat)


class TestClimateProperties:
    def test_current_temperature(self, regulation_state, thermostat_th1):
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.current_temperature == thermostat_th1.temperature

    def test_hvac_mode_maps_uc_mode(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_HEAT
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_off(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_OFF
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.hvac_mode == HVACMode.OFF

    def test_target_temperature_heat_t1(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_HEAT
        thermostat_th1.t1_t2 = 1
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.target_temperature == thermostat_th1.setpoint_hot_t1

    def test_target_temperature_heat_t2(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_HEAT
        thermostat_th1.t1_t2 = 2
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.target_temperature == thermostat_th1.setpoint_hot_t2

    def test_target_temperature_cool_t1(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_COOL
        thermostat_th1.t1_t2 = 1
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.target_temperature == thermostat_th1.setpoint_cool_t1

    def test_target_temperature_none_when_off(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_OFF
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.target_temperature is None

    def test_preset_comfort(self, regulation_state, thermostat_th1):
        thermostat_th1.t1_t2 = 1
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.preset_mode == PRESET_COMFORT

    def test_preset_eco(self, regulation_state, thermostat_th1):
        thermostat_th1.t1_t2 = 2
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity.preset_mode == PRESET_ECO

    def test_master_thermostat_is_th1(self, regulation_state, thermostat_th1):
        entity = make_climate(thermostat_th1, regulation_state)
        assert entity._is_master is True

    def test_non_master_thermostat(self, regulation_state, thermostat_th2):
        entity = make_climate(thermostat_th2, regulation_state)
        assert entity._is_master is False


class TestSetHvacMode:
    @pytest.mark.asyncio
    async def test_master_can_set_mode(self, regulation_state, thermostat_th1):
        entity = make_climate(thermostat_th1, regulation_state)
        await entity.async_set_hvac_mode(HVACMode.COOL)
        entity._client.set_mode.assert_called_once_with(99, UC_MODE_COOL)
        entity.coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_master_cannot_set_mode(self, regulation_state, thermostat_th2):
        entity = make_climate(thermostat_th2, regulation_state)
        await entity.async_set_hvac_mode(HVACMode.COOL)
        entity._client.set_mode.assert_not_called()


class TestSetTemperature:
    @pytest.mark.asyncio
    async def test_sets_hot_t1_when_heat_comfort(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_HEAT
        thermostat_th1.t1_t2 = 1
        entity = make_climate(thermostat_th1, regulation_state)
        await entity.async_set_temperature(temperature=22.0)
        entity._client.set_thermostat.assert_called_once_with(
            99, 1, "setpoint_hot_t1", 22.0
        )

    @pytest.mark.asyncio
    async def test_clamps_confort_above_eco_in_heat(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_HEAT
        thermostat_th1.t1_t2 = 1
        thermostat_th1.setpoint_hot_t2 = 19.0
        entity = make_climate(thermostat_th1, regulation_state)
        # Set confort below eco — should be clamped to eco value
        await entity.async_set_temperature(temperature=17.0)
        entity._client.set_thermostat.assert_called_once_with(
            99, 1, "setpoint_hot_t1", 19.0  # clamped to eco
        )

    @pytest.mark.asyncio
    async def test_no_set_when_off(self, regulation_state, thermostat_th1):
        regulation_state.uc_mode = UC_MODE_OFF
        entity = make_climate(thermostat_th1, regulation_state)
        await entity.async_set_temperature(temperature=22.0)
        entity._client.set_thermostat.assert_not_called()


class TestSetPreset:
    @pytest.mark.asyncio
    async def test_set_eco(self, regulation_state, thermostat_th1):
        entity = make_climate(thermostat_th1, regulation_state)
        await entity.async_set_preset_mode(PRESET_ECO)
        entity._client.set_thermostat.assert_called_once_with(99, 1, "t1_t2", 2)

    @pytest.mark.asyncio
    async def test_set_comfort(self, regulation_state, thermostat_th1):
        thermostat_th1.t1_t2 = 2
        entity = make_climate(thermostat_th1, regulation_state)
        await entity.async_set_preset_mode(PRESET_COMFORT)
        entity._client.set_thermostat.assert_called_once_with(99, 1, "t1_t2", 1)
