"""Climate entities for BaillConnect (one per thermostat)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import BaillConnectClient, ThermostatState
from .const import (
    CONF_REGULATION_ID,
    DOMAIN,
    ENTRY_CLIENT,
    ENTRY_COORDINATOR,
    FAN_INT_TO_STR,
    FAN_STR_TO_INT,
    HVAC_TO_UC_MODE,
    MANUFACTURER,
    MODEL,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_TO_T1_T2,
    SETPOINT_FIELD_BY_MODE,
    T1_T2_TO_PRESET,
    TEMP_MAX,
    TEMP_MIN,
    TEMP_STEP,
    UC_MODE_COOL,
    UC_MODE_DRY,
    UC_MODE_HEAT,
    UC_MODE_OFF,
    UC_MODE_TO_HVAC,
)
from .coordinator import BaillConnectCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities from config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BaillConnectCoordinator = data[ENTRY_COORDINATOR]
    client: BaillConnectClient = data[ENTRY_CLIENT]
    regulation_id: int = entry.data[CONF_REGULATION_ID]

    entities = [
        BaillConnectClimate(coordinator, client, regulation_id, th)
        for th in coordinator.data.thermostats
    ]
    async_add_entities(entities)


class BaillConnectClimate(CoordinatorEntity[BaillConnectCoordinator], ClimateEntity):
    """Climate entity for one BaillConnect thermostat."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX
    _attr_preset_modes = [PRESET_COMFORT, PRESET_ECO]
    _attr_fan_modes = list(FAN_STR_TO_INT.keys())
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BaillConnectCoordinator,
        client: BaillConnectClient,
        regulation_id: int,
        thermostat: ThermostatState,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._regulation_id = regulation_id
        self._thermostat_id = thermostat.id
        self._is_master = thermostat.key == "th1"

        self._attr_unique_id = f"{DOMAIN}_{regulation_id}_th{thermostat.id}"
        self._attr_name = thermostat.name or f"Thermostat {thermostat.key}"

        # Device info groups all thermostats under the same regulation device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(regulation_id))},
            "name": "BaillZoning",
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

        # Features depend on whether this is the master thermostat
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
        )
        if self._is_master:
            features |= ClimateEntityFeature.FAN_MODE
        self._attr_supported_features = features

        # HVAC modes: master can change mode, others only display
        if self._is_master:
            self._attr_hvac_modes = list(UC_MODE_TO_HVAC.values())
        else:
            self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _thermostat(self) -> ThermostatState | None:
        """Return current thermostat state from coordinator data."""
        for th in self.coordinator.data.thermostats:
            if th.id == self._thermostat_id:
                return th
        return None

    # ------------------------------------------------------------------
    # HA properties
    # ------------------------------------------------------------------

    @property
    def current_temperature(self) -> float | None:
        th = self._thermostat()
        return th.temperature if th else None

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self.coordinator.data.uc_mode
        return UC_MODE_TO_HVAC.get(mode, HVACMode.OFF)

    @property
    def target_temperature(self) -> float | None:
        th = self._thermostat()
        if th is None:
            return None
        mode = self.coordinator.data.uc_mode
        if mode == UC_MODE_OFF:
            return None
        fields = SETPOINT_FIELD_BY_MODE.get(mode)
        if fields is None:
            return None
        field = fields.get(th.t1_t2)
        return getattr(th, field, None) if field else None

    @property
    def preset_mode(self) -> str:
        th = self._thermostat()
        if th is None:
            return PRESET_COMFORT
        return T1_T2_TO_PRESET.get(th.t1_t2, PRESET_COMFORT)

    @property
    def fan_mode(self) -> str | None:
        if not self._is_master:
            return None
        return FAN_INT_TO_STR.get(self.coordinator.data.ui_fan)

    # ------------------------------------------------------------------
    # HA actions
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Change global HVAC mode — only allowed on master thermostat."""
        if not self._is_master:
            _LOGGER.warning(
                "HVAC mode change ignored: only th1 can change the global mode"
            )
            return
        uc_mode = HVAC_TO_UC_MODE.get(hvac_mode)
        if uc_mode is None:
            _LOGGER.error("Unknown HVAC mode: %s", hvac_mode)
            return
        await self._client.set_mode(self._regulation_id, uc_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature for current mode/preset combination."""
        temperature: float | None = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        th = self._thermostat()
        if th is None:
            return

        mode = self.coordinator.data.uc_mode
        if mode == UC_MODE_OFF:
            return

        fields = SETPOINT_FIELD_BY_MODE.get(mode)
        if fields is None:
            return

        field = fields.get(th.t1_t2)
        if field is None:
            return

        # Enforce eco <= confort constraint
        temperature = self._clamp_setpoint(th, mode, th.t1_t2, temperature)

        await self._client.set_thermostat(
            self._regulation_id, self._thermostat_id, field, temperature
        )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between confort (T1) and eco (T2)."""
        t1_t2 = PRESET_TO_T1_T2.get(preset_mode)
        if t1_t2 is None:
            _LOGGER.error("Unknown preset mode: %s", preset_mode)
            return
        await self._client.set_thermostat(
            self._regulation_id, self._thermostat_id, "t1_t2", t1_t2
        )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan speed — only on master thermostat."""
        if not self._is_master:
            return
        fan_int = FAN_STR_TO_INT.get(fan_mode)
        if fan_int is None:
            _LOGGER.error("Unknown fan mode: %s", fan_mode)
            return
        await self._client.set_regulation(
            self._regulation_id, {"ui_fan": fan_int}
        )
        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------
    # Constraint helper
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp_setpoint(
        th: ThermostatState, mode: int, t1_t2: int, value: float
    ) -> float:
        """Enforce setpoint_t2 <= setpoint_t1 before sending to API."""
        if mode in (UC_MODE_HEAT,):
            if t1_t2 == 1:  # confort — must be >= eco
                return max(value, th.setpoint_hot_t2)
            else:  # eco — must be <= confort
                return min(value, th.setpoint_hot_t1)
        if mode in (UC_MODE_COOL, UC_MODE_DRY):
            if t1_t2 == 1:  # confort — must be <= eco (cold: lower is more aggressive)
                return min(value, th.setpoint_cool_t2)
            else:  # eco — must be >= confort
                return max(value, th.setpoint_cool_t1)
        return value
