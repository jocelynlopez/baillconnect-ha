"""Unit tests for BaillConnect sensor entities."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.baillconnect.sensor import (
    BaillConnectRegulationSensor,
    BaillConnectThermostatSensor,
    REGULATION_SENSORS,
    THERMOSTAT_SENSORS,
)


def make_coordinator(regulation_state):
    coordinator = MagicMock()
    coordinator.data = regulation_state
    return coordinator


class TestThermostatSensors:
    def test_temperature_sensor_value(self, regulation_state, thermostat_th1):
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in THERMOSTAT_SENSORS if d.key == "temperature")
        sensor = BaillConnectThermostatSensor(coordinator, 99, thermostat_th1.id, desc)
        assert sensor.native_value == thermostat_th1.temperature

    def test_battery_sensor_false(self, regulation_state, thermostat_th1):
        thermostat_th1.is_battery_low = False
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in THERMOSTAT_SENSORS if d.key == "battery")
        sensor = BaillConnectThermostatSensor(coordinator, 99, thermostat_th1.id, desc)
        assert sensor.native_value == "Non"

    def test_battery_sensor_true(self, regulation_state, thermostat_th1):
        thermostat_th1.is_battery_low = True
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in THERMOSTAT_SENSORS if d.key == "battery")
        sensor = BaillConnectThermostatSensor(coordinator, 99, thermostat_th1.id, desc)
        assert sensor.native_value == "Oui"

    def test_connected_sensor(self, regulation_state, thermostat_th1):
        thermostat_th1.is_connected = True
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in THERMOSTAT_SENSORS if d.key == "connected")
        sensor = BaillConnectThermostatSensor(coordinator, 99, thermostat_th1.id, desc)
        assert sensor.native_value == "Connecté"

    def test_motor_closed(self, regulation_state, thermostat_th1):
        thermostat_th1.motor_state = 4
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in THERMOSTAT_SENSORS if d.key == "motor_state")
        sensor = BaillConnectThermostatSensor(coordinator, 99, thermostat_th1.id, desc)
        assert sensor.native_value == "Fermé"

    def test_motor_open(self, regulation_state, thermostat_th1):
        thermostat_th1.motor_state = 0
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in THERMOSTAT_SENSORS if d.key == "motor_state")
        sensor = BaillConnectThermostatSensor(coordinator, 99, thermostat_th1.id, desc)
        assert sensor.native_value == "Ouvert"

    def test_unique_id_format(self, regulation_state, thermostat_th1):
        coordinator = make_coordinator(regulation_state)
        desc = THERMOSTAT_SENSORS[0]
        sensor = BaillConnectThermostatSensor(coordinator, 99, thermostat_th1.id, desc)
        assert sensor.unique_id == f"baillconnect_99_th{thermostat_th1.id}_{desc.key}"


class TestRegulationSensors:
    def test_fan_speed_auto(self, regulation_state):
        regulation_state.ui_fan = 0
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in REGULATION_SENSORS if d.key == "fan_speed")
        sensor = BaillConnectRegulationSensor(coordinator, 99, desc)
        assert sensor.native_value == "auto"

    def test_fan_speed_high(self, regulation_state):
        regulation_state.ui_fan = 3
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in REGULATION_SENSORS if d.key == "fan_speed")
        sensor = BaillConnectRegulationSensor(coordinator, 99, desc)
        assert sensor.native_value == "high"

    def test_circuit_active(self, regulation_state):
        regulation_state.ui_on = True
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in REGULATION_SENSORS if d.key == "circuit_on")
        sensor = BaillConnectRegulationSensor(coordinator, 99, desc)
        assert sensor.native_value == "Actif"

    def test_circuit_inactive(self, regulation_state):
        regulation_state.ui_on = False
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in REGULATION_SENSORS if d.key == "circuit_on")
        sensor = BaillConnectRegulationSensor(coordinator, 99, desc)
        assert sensor.native_value == "Inactif"

    def test_error_code(self, regulation_state):
        regulation_state.ui_error = 7
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in REGULATION_SENSORS if d.key == "error_code")
        sensor = BaillConnectRegulationSensor(coordinator, 99, desc)
        assert sensor.native_value == 7

    def test_idc_connected(self, regulation_state):
        regulation_state.is_connected = True
        coordinator = make_coordinator(regulation_state)
        desc = next(d for d in REGULATION_SENSORS if d.key == "idc_connected")
        sensor = BaillConnectRegulationSensor(coordinator, 99, desc)
        assert sensor.native_value == "Connecté"

    def test_unique_id_format(self, regulation_state):
        coordinator = make_coordinator(regulation_state)
        desc = REGULATION_SENSORS[0]
        sensor = BaillConnectRegulationSensor(coordinator, 99, desc)
        assert sensor.unique_id == f"baillconnect_99_{desc.key}"
