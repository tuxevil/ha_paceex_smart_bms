"""Sensor entities for PACEEX BMS."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PaceexConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import PaceexDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class PaceexSensorEntityDescription(SensorEntityDescription):
    """PACEEX sensor description."""


SENSORS = (
    PaceexSensorEntityDescription(
        key="state_of_charge",
        name="State of charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PaceexSensorEntityDescription(
        key="state_of_health",
        name="State of health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
    ),
    PaceexSensorEntityDescription(
        key="voltage",
        name="Battery voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PaceexSensorEntityDescription(
        key="current",
        name="Battery current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PaceexSensorEntityDescription(
        key="power",
        name="Battery power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PaceexSensorEntityDescription(
        key="remaining_capacity",
        name="Remaining capacity",
        native_unit_of_measurement="Ah",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
    ),
    PaceexSensorEntityDescription(
        key="design_capacity",
        name="Design capacity",
        native_unit_of_measurement="Ah",
        icon="mdi:battery-high",
    ),
    PaceexSensorEntityDescription(
        key="cycles",
        name="Battery cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
    ),
    PaceexSensorEntityDescription(
        key="cell_count", name="Cell count", icon="mdi:counter"
    ),
    PaceexSensorEntityDescription(
        key="cell_delta",
        name="Cell voltage delta",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:delta",
    ),
    PaceexSensorEntityDescription(
        key="cell_min_voltage",
        name="Minimum cell voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PaceexSensorEntityDescription(
        key="cell_max_voltage",
        name="Maximum cell voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


DIAGNOSTICS = (
    PaceexSensorEntityDescription(
        key="consecutive_failures",
        name="Consecutive failures",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:counter",
    ),
    PaceexSensorEntityDescription(
        key="last_success",
        name="Last successful update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass,
    entry: PaceexConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up PACEEX BMS sensors."""
    coordinator = entry.runtime_data
    info = await hass.async_add_executor_job(coordinator.api.read_device_info)
    descriptions = list(SENSORS)
    for index in range(1, int(coordinator.data["cell_count"]) + 1):
        descriptions.append(
            PaceexSensorEntityDescription(
                key=f"cell_{index:02d}_voltage",
                name=f"Cell {index:02d} voltage",
                native_unit_of_measurement=UnitOfElectricPotential.VOLT,
                device_class=SensorDeviceClass.VOLTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:battery-outline",
            )
        )
    async_add_entities(
        PaceexSensor(coordinator, description, info.serial_number)
        for description in (*descriptions, *DIAGNOSTICS)
    )


class PaceexSensor(CoordinatorEntity[PaceexDataUpdateCoordinator], SensorEntity):
    """A sensor backed by the shared PACEEX coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description, serial_number: str) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{serial_number}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name="PACEEX Smart BMS",
            serial_number=serial_number,
        )

    @property
    def native_value(self):
        """Return the latest coordinated sensor value."""
        if self.entity_description.key == "consecutive_failures":
            return self.coordinator.consecutive_failures
        if self.entity_description.key == "last_success":
            return self.coordinator.last_success
        return (self.coordinator.data or {}).get(self.entity_description.key)
