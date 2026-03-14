"""Shared fixtures for BaillConnect tests."""
from __future__ import annotations

import pytest

from custom_components.baillconnect.api import (
    RegulationState,
    ThermostatState,
    ZoneState,
)


# ---------------------------------------------------------------------------
# Minimal thermostat fixtures
# ---------------------------------------------------------------------------

def make_thermostat(
    id: int = 1,
    key: str = "th1",
    name: str = "Salon",
    temperature: float = 21.5,
    is_on: bool = True,
    setpoint_hot_t1: float = 21.0,
    setpoint_hot_t2: float = 18.0,
    setpoint_cool_t1: float = 26.0,
    setpoint_cool_t2: float = 28.0,
    t1_t2: int = 1,
    motor_state: int = 0,
    is_battery_low: bool = False,
    is_connected: bool = True,
    zone: int = 1,
) -> ThermostatState:
    return ThermostatState(
        id=id,
        key=key,
        name=name,
        temperature=temperature,
        zone=zone,
        is_on=is_on,
        setpoint_hot_t1=setpoint_hot_t1,
        setpoint_hot_t2=setpoint_hot_t2,
        setpoint_cool_t1=setpoint_cool_t1,
        setpoint_cool_t2=setpoint_cool_t2,
        t1_t2=t1_t2,
        motor_state=motor_state,
        is_battery_low=is_battery_low,
        is_connected=is_connected,
        connected_at_text="",
    )


@pytest.fixture
def thermostat_th1() -> ThermostatState:
    return make_thermostat(id=1, key="th1", name="Salon")


@pytest.fixture
def thermostat_th2() -> ThermostatState:
    return make_thermostat(id=2, key="th2", name="Chambre 1", temperature=20.0)


@pytest.fixture
def regulation_state(thermostat_th1, thermostat_th2) -> RegulationState:
    return RegulationState(
        uc_mode=2,           # heat
        ui_on=True,
        ui_fan=0,            # auto
        ui_sp=20.0,
        ui_has_error=False,
        ui_error=0,
        is_connected=True,
        uc_hot_min=16.0,
        uc_hot_max=30.0,
        uc_cold_min=16.0,
        uc_cold_max=30.0,
        temp_diff=1.0,
        thermostats=[thermostat_th1, thermostat_th2],
        zones=[ZoneState(id=1, name="Zone 1")],
    )
