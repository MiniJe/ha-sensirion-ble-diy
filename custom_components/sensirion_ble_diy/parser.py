"""Parser for Sensirion BLE advertisements.

Decodes the live data sample types published by Sensirion at
https://sensirion.github.io/ble-services/#/live-data that the built-in
sensirion_ble integration does not know, so that DIY gadgets built with the
Sensirion arduino-ble-gadget library can be used. Sample types 4, 6 and 8
(SHT3x, SHT4x and MyCO2 gadgets) are left to the built-in integration.

Manufacturer data layout (company id 0x06D5), little endian:
  byte 0      advertising type (0)
  byte 1      sample type
  bytes 2-3   device id
  bytes 4...  one uint16 per signal
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import struct

from bluetooth_data_tools import short_address
from bluetooth_sensor_state_data import BluetoothData
from home_assistant_bluetooth import BluetoothServiceInfo
from sensor_state_data import SensorDeviceClass, Units

_LOGGER = logging.getLogger(__name__)

COMPANY_IDENTIFIER = 0x06D5
ADVERTISING_TYPE = 0x00
HEADER_SIZE = 4
FULL_SCALE = 2**16 - 1


@dataclass(frozen=True)
class Signal:
    """One uint16 field of a sample."""

    key: str
    device_class: SensorDeviceClass | None
    unit: Units | None
    convert: Callable[[int], float | int]
    name: str | None = None


def _raw(ticks: int) -> int:
    return ticks


def _tenths(ticks: int) -> float:
    return round(ticks / 10, 1)


TEMPERATURE = Signal(
    "temperature",
    SensorDeviceClass.TEMPERATURE,
    Units.TEMP_CELSIUS,
    lambda ticks: round(-45 + 175.0 * ticks / FULL_SCALE, 2),
)
HUMIDITY = Signal(
    "humidity",
    SensorDeviceClass.HUMIDITY,
    Units.PERCENTAGE,
    lambda ticks: round(100.0 * ticks / FULL_SCALE, 2),
)
CO2 = Signal(
    "carbon_dioxide",
    SensorDeviceClass.CO2,
    Units.CONCENTRATION_PARTS_PER_MILLION,
    _raw,
)
VOC = Signal("voc_index", None, None, _raw, "VOC index")
NOX = Signal("nox_index", None, None, _raw, "NOx index")
HCHO = Signal(
    "formaldehyde",
    None,
    Units.CONCENTRATION_PARTS_PER_BILLION,
    lambda ticks: round(ticks / 5, 1),
    "Formaldehyde",
)
PM1 = Signal(
    "pm1",
    SensorDeviceClass.PM1,
    Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    _tenths,
    "PM1",
)
PM25 = Signal(
    "pm25",
    SensorDeviceClass.PM25,
    Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    _tenths,
    "PM2.5",
)
# older sample types spread 0-1000 ug/m3 over the full uint16 range
PM25_FULL_SCALE = Signal(
    "pm25",
    SensorDeviceClass.PM25,
    Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    lambda ticks: round(1000.0 * ticks / FULL_SCALE, 1),
    "PM2.5",
)
PM4 = Signal(
    "pm4",
    SensorDeviceClass.PM4,
    Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    _tenths,
    "PM4",
)
PM10 = Signal(
    "pm10",
    SensorDeviceClass.PM10,
    Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    _tenths,
    "PM10",
)

# Sample types 4, 6 and 8 belong to the built-in sensirion_ble integration.
# Types 38 (air velocity) and 40 (H2, pressure) are left out: the
# specification gives no unit for them.
SAMPLE_TYPES: dict[int, tuple[Signal, ...]] = {
    3: (TEMPERATURE, HUMIDITY, VOC),
    10: (TEMPERATURE, HUMIDITY, CO2),
    12: (TEMPERATURE, HUMIDITY, CO2, PM25_FULL_SCALE),
    14: (TEMPERATURE, HUMIDITY, HCHO),
    16: (TEMPERATURE, HUMIDITY, VOC, PM25_FULL_SCALE),
    20: (TEMPERATURE, HUMIDITY, CO2, VOC, PM25_FULL_SCALE, HCHO),
    22: (TEMPERATURE, HUMIDITY, VOC, NOX),
    24: (TEMPERATURE, HUMIDITY, VOC, NOX, PM25),
    26: (TEMPERATURE, HUMIDITY, CO2, VOC, NOX, PM25),
    28: (TEMPERATURE, HUMIDITY, CO2, PM25),
    30: (TEMPERATURE, HUMIDITY, VOC, PM25),
    32: (TEMPERATURE, HUMIDITY, CO2, VOC, PM25, HCHO),
    34: (PM1, PM25, PM4, PM10),
    36: (CO2,),
    42: (TEMPERATURE, HUMIDITY, PM25),
    44: (TEMPERATURE, HUMIDITY, HCHO, VOC, NOX, PM25),
}


def parse_advertisement(
    raw_data: bytes,
) -> tuple[str, int, list[tuple[Signal, float | int]]] | None:
    """Return device id, sample type and the converted signals, or None."""
    if len(raw_data) < HEADER_SIZE or raw_data[0] != ADVERTISING_TYPE:
        _LOGGER.debug("Not a Sensirion sample advertisement: %s", raw_data.hex())
        return None
    sample_type = raw_data[1]
    signals = SAMPLE_TYPES.get(sample_type)
    if signals is None:
        _LOGGER.debug("Sample type %d not supported: %s", sample_type, raw_data.hex())
        return None
    if len(raw_data) < HEADER_SIZE + 2 * len(signals):
        _LOGGER.debug("Sample type %d too short: %s", sample_type, raw_data.hex())
        return None
    ticks = struct.unpack_from(f"<{len(signals)}H", raw_data, HEADER_SIZE)
    device_id = raw_data[2:4].hex().upper()
    return (
        device_id,
        sample_type,
        [(signal, signal.convert(value)) for signal, value in zip(signals, ticks)],
    )


class SensirionBluetoothDeviceData(BluetoothData):
    """Data for Sensirion BLE sensors."""

    def _start_update(self, service_info: BluetoothServiceInfo) -> None:
        try:
            raw_data = service_info.manufacturer_data[COMPANY_IDENTIFIER]
        except (KeyError, IndexError):
            _LOGGER.debug("Manufacturer ID not found in data")
            return

        result = parse_advertisement(raw_data)
        if result is None:
            return
        device_id, sample_type, values = result

        # DIY gadgets advertise the one-letter name "S"; proxies that miss the
        # scan response report the address instead
        local_name = service_info.name
        if len(local_name) < 2 or local_name == service_info.address:
            local_name = "Sensirion Gadget"
            self.set_device_type(f"Sensirion gadget, sample type {sample_type}")
        else:
            self.set_device_type(f"Sensirion {local_name}")
        self.set_device_manufacturer("Sensirion AG")
        self.set_device_name(
            f"{local_name} {device_id or short_address(service_info.address)}"
        )
        for signal, value in values:
            self.update_sensor(
                key=signal.key,
                native_unit_of_measurement=signal.unit,
                native_value=value,
                device_class=signal.device_class,
                name=signal.name,
            )
