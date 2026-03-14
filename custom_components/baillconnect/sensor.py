"""Sensor entities for BaillConnect."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RegulationState, ThermostatState
from .const import (
    CONF_REGULATION_ID,
    DOMAIN,
    ENTRY_COORDINATOR,
    FAN_INT_TO_STR,
    MANUFACTURER,
    MODEL,
    MOTOR_STATE_CLOSED,
    SENSOR_SUFFIX_BATTERY,
    SENSOR_SUFFIX_CIRCUIT,
    SENSOR_SUFFIX_CONNECTED,
    SENSOR_SUFFIX_ERROR,
    SENSOR_SUFFIX_FAN,
    SENSOR_SUFFIX_IDC_CONNECTED,
    SENSOR_SUFFIX_MOTOR,
    SENSOR_SUFFIX_TEMP,
)
from .coordinator import BaillConnectCoordinator

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-thermostat sensor descriptions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class ThermostatSensorDescription(SensorEntityDescription):
    th_attr: str = ""
    value_fn: Any = None


THERMOSTAT_SENSORS: tuple[ThermostatSensorDescription, ...] = (
    ThermostatSensorDescription(
        key=SENSOR_SUFFIX_TEMP,
        name="Température ambiante",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        th_attr="temperature",
    ),
    ThermostatSensorDescription(
        key=SENSOR_SUFFIX_BATTERY,
        name="Batterie faible",
        th_attr="is_battery_low",
        value_fn=lambda v: "Oui" if v else "Non",
    ),
    ThermostatSensorDescription(
        key=SENSOR_SUFFIX_CONNECTED,
        name="Connexion thermostat",
        th_attr="is_connected",
        value_fn=lambda v: "Connecté" if v else "Déconnecté",
    ),
    ThermostatSensorDescription(
        key=SENSOR_SUFFIX_MOTOR,
        name="État volet",
        th_attr="motor_state",
        value_fn=lambda v: "Fermé" if v == MOTOR_STATE_CLOSED else "Ouvert",
    ),
)

# ---------------------------------------------------------------------------
# Regulation-level sensor descriptions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class RegulationSensorDescription(SensorEntityDescription):
    reg_attr: str = ""
    value_fn: Any = None


REGULATION_SENSORS: tuple[RegulationSensorDescription, ...] = (
    RegulationSensorDescription(
        key=SENSOR_SUFFIX_FAN,
        name="Vitesse ventilateur",
        reg_attr="ui_fan",
        value_fn=lambda v: FAN_INT_TO_STR.get(v, str(v)),
    ),
    RegulationSensorDescription(
        key=SENSOR_SUFFIX_CIRCUIT,
        name="Circuit actif",
        reg_attr="ui_on",
        value_fn=lambda v: "Actif" if v else "Inactif",
    ),
    RegulationSensorDescription(
        key=SENSOR_SUFFIX_ERROR,
        name="Code erreur",
        reg_attr="ui_error",
    ),
    RegulationSensorDescription(
        key=SENSOR_SUFFIX_IDC_CONNECTED,
        name="IDC-WEB connecté",
        reg_attr="is_connected",
        value_fn=lambda v: "Connecté" if v else "Déconnecté",
    ),
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BaillConnectCoordinator = data[ENTRY_COORDINATOR]
    regulation_id: int = entry.data[CONF_REGULATION_ID]

    entities: list[SensorEntity] = []

    # Per-thermostat sensors
    for th in coordinator.data.thermostats:
        for desc in THERMOSTAT_SENSORS:
            entities.append(
                BaillConnectThermostatSensor(coordinator, regulation_id, th.id, desc)
            )

    # Regulation-level sensors
    for desc in REGULATION_SENSORS:
        entities.append(
            BaillConnectRegulationSensor(coordinator, regulation_id, desc)
        )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Thermostat sensor entity
# ---------------------------------------------------------------------------

class BaillConnectThermostatSensor(
    CoordinatorEntity[BaillConnectCoordinator], SensorEntity
):
    """Sensor linked to a specific thermostat."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BaillConnectCoordinator,
        regulation_id: int,
        thermostat_id: int,
        description: ThermostatSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._regulation_id = regulation_id
        self._thermostat_id = thermostat_id

        self._attr_unique_id = (
            f"{DOMAIN}_{regulation_id}_th{thermostat_id}_{description.key}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(regulation_id))},
            "name": "BaillZoning",
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    def _thermostat(self) -> ThermostatState | None:
        for th in self.coordinator.data.thermostats:
            if th.id == self._thermostat_id:
                return th
        return None

    @property
    def name(self) -> str:
        th = self._thermostat()
        th_name = th.name if th else f"Thermostat {self._thermostat_id}"
        return f"{th_name} — {self.entity_description.name}"

    @property
    def native_value(self) -> Any:
        th = self._thermostat()
        if th is None:
            return None
        raw = getattr(th, self.entity_description.th_attr, None)
        fn = self.entity_description.value_fn
        return fn(raw) if fn is not None else raw


# ---------------------------------------------------------------------------
# Regulation sensor entity
# ---------------------------------------------------------------------------

class BaillConnectRegulationSensor(
    CoordinatorEntity[BaillConnectCoordinator], SensorEntity
):
    """Sensor for a regulation-level attribute."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BaillConnectCoordinator,
        regulation_id: int,
        description: RegulationSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._regulation_id = regulation_id

        self._attr_unique_id = f"{DOMAIN}_{regulation_id}_{description.key}"
        self._attr_name = description.name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(regulation_id))},
            "name": "BaillZoning",
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def native_value(self) -> Any:
        state: RegulationState = self.coordinator.data
        raw = getattr(state, self.entity_description.reg_attr, None)
        fn = self.entity_description.value_fn
        return fn(raw) if fn is not None else raw
