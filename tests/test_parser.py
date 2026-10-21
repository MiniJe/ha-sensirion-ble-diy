"""Tests for the Sensirion advertisement parser."""

from collections.abc import Iterator
import importlib.util
import logging
from pathlib import Path
import struct
import sys

from habluetooth import BluetoothServiceInfo
import pytest

# parser.py does not depend on Home Assistant; it is loaded on its own so the
# package __init__ (which imports homeassistant) is not needed for the tests
PARSER_PATH = (
    Path(__file__).parents[1] / "custom_components" / "sensirion_ble_diy" / "parser.py"
)
_spec = importlib.util.spec_from_file_location("sensirion_ble_diy_parser", PARSER_PATH)
assert _spec is not None and _spec.loader is not None
parser = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = parser  # dataclasses look the module up
_spec.loader.exec_module(parser)

ADDRESS = "AA:BB:CC:DD:EE:FF"
DEVICE_ID = b"\x34\x12"

# the README table of supported sample types, kept apart from SAMPLE_TYPES so
# that a change to either one shows up here
EXPECTED_SIGNALS = {
    3: ["temperature", "humidity", "voc_index"],
    10: ["temperature", "humidity", "carbon_dioxide"],
    12: ["temperature", "humidity", "carbon_dioxide", "pm25"],
    14: ["temperature", "humidity", "formaldehyde"],
    16: ["temperature", "humidity", "voc_index", "pm25"],
    20: [
        "temperature",
        "humidity",
        "carbon_dioxide",
        "voc_index",
        "pm25",
        "formaldehyde",
    ],
    22: ["temperature", "humidity", "voc_index", "nox_index"],
    24: ["temperature", "humidity", "voc_index", "nox_index", "pm25"],
    26: ["temperature", "humidity", "carbon_dioxide", "voc_index", "nox_index", "pm25"],
    28: ["temperature", "humidity", "carbon_dioxide", "pm25"],
    30: ["temperature", "humidity", "voc_index", "pm25"],
    32: [
        "temperature",
        "humidity",
        "carbon_dioxide",
        "voc_index",
        "pm25",
        "formaldehyde",
    ],
    34: ["pm1", "pm25", "pm4", "pm10"],
    36: ["carbon_dioxide"],
    42: ["temperature", "humidity", "pm25"],
    44: ["temperature", "humidity", "formaldehyde", "voc_index", "nox_index", "pm25"],
}


def advertisement(sample_type: int, *ticks: int, advertising_type: int = 0) -> bytes:
    """Build the manufacturer data of a sample advertisement."""
    return (
        bytes([advertising_type, sample_type])
        + DEVICE_ID
        + struct.pack(f"<{len(ticks)}H", *ticks)
    )


def decoded(raw_data: bytes) -> dict[str, float | int]:
    """Parse an advertisement that must be supported."""
    result = parser.parse_advertisement(raw_data)
    assert result is not None
    return {signal.key: value for signal, value in result[2]}


@pytest.fixture(autouse=True)
def reset_reported_sample_types() -> Iterator[None]:
    """Let every test see the unknown sample type warning again."""
    parser._reported_sample_types.clear()
    yield
    parser._reported_sample_types.clear()


def test_supported_sample_types_match_readme() -> None:
    """Every documented sample type is decoded, and nothing else."""
    assert set(parser.SAMPLE_TYPES) == set(EXPECTED_SIGNALS)
    assert not parser.BUILT_IN_SAMPLE_TYPES & set(parser.SAMPLE_TYPES)


@pytest.mark.parametrize("sample_type", sorted(EXPECTED_SIGNALS))
def test_sample_type_signals(sample_type: int) -> None:
    """Each sample type yields its signals in advertisement order."""
    expected = EXPECTED_SIGNALS[sample_type]
    result = parser.parse_advertisement(
        advertisement(sample_type, *[0] * len(expected))
    )
    assert result is not None
    device_id, parsed_type, values = result
    assert device_id == "3412"
    assert parsed_type == sample_type
    assert [signal.key for signal, _ in values] == expected


def test_sample_type_20() -> None:
    """The sample type of the tested DIY gadget (SCD30 + SFA30 + SEN54)."""
    # 24.0 C, 45 %, 812 ppm, VOC index 120, 10.0 ug/m3, 10.0 ppb
    values = decoded(advertisement(20, 25841, 29491, 812, 120, 655, 50))
    assert values == {
        "temperature": 24.0,
        "humidity": 45.0,
        "carbon_dioxide": 812,
        "voc_index": 120,
        "pm25": 10.0,
        "formaldehyde": 10.0,
    }


@pytest.mark.parametrize(
    ("ticks", "temperature", "humidity"),
    [(0, -45.0, 0.0), (65535, 130.0, 100.0), (32768, 42.5, 50.0)],
)
def test_temperature_and_humidity_scale(
    ticks: int, temperature: float, humidity: float
) -> None:
    """Temperature and humidity span the full uint16 range."""
    values = decoded(advertisement(3, ticks, ticks, 0))
    assert values["temperature"] == temperature
    assert values["humidity"] == humidity


def test_pm25_full_scale() -> None:
    """Older sample types spread 0-1000 ug/m3 over the full uint16 range."""
    assert decoded(advertisement(16, 0, 0, 0, 65535))["pm25"] == 1000.0
    assert decoded(advertisement(16, 0, 0, 0, 6554))["pm25"] == 100.0


def test_pm_tenths() -> None:
    """Newer sample types send particulate matter in tenths of ug/m3."""
    assert decoded(advertisement(34, 12, 123, 456, 1000)) == {
        "pm1": 1.2,
        "pm25": 12.3,
        "pm4": 45.6,
        "pm10": 100.0,
    }
    assert decoded(advertisement(30, 0, 0, 0, 123))["pm25"] == 12.3


def test_formaldehyde_fifths() -> None:
    """Formaldehyde is sent in fifths of a ppb."""
    assert decoded(advertisement(14, 0, 0, 101))["formaldehyde"] == 20.2


def test_trailing_bytes_are_ignored() -> None:
    """Data after the last signal does not prevent decoding."""
    assert decoded(advertisement(36, 812) + b"\x00\x00") == {"carbon_dioxide": 812}


@pytest.mark.parametrize(
    "raw_data",
    [
        b"",
        b"\x00\x0a\x34",
        advertisement(10, 0, 0),
        advertisement(10, 0, 0, 0, advertising_type=1),
    ],
    ids=["empty", "short-header", "short-sample", "advertising-type"],
)
def test_invalid_advertisements(raw_data: bytes) -> None:
    """Incomplete or foreign advertisements are rejected."""
    assert parser.parse_advertisement(raw_data) is None


@pytest.mark.parametrize("sample_type", sorted(parser.BUILT_IN_SAMPLE_TYPES))
def test_built_in_sample_types_are_left_alone(
    sample_type: int, caplog: pytest.LogCaptureFixture
) -> None:
    """Sample types of the built-in integration are skipped without a warning."""
    with caplog.at_level(logging.WARNING):
        assert parser.parse_advertisement(advertisement(sample_type, 0, 0)) is None
    assert not caplog.records


def test_unknown_sample_type_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """An unknown sample type is reported once, with the data to report."""
    raw_data = advertisement(99, 1, 2)
    with caplog.at_level(logging.WARNING):
        assert parser.parse_advertisement(raw_data) is None
        assert parser.parse_advertisement(raw_data) is None
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "sample type 99" in message
    assert raw_data.hex() in message
    assert parser.ISSUE_TRACKER in message


def service_info(name: str, raw_data: bytes, rssi: int = -60) -> BluetoothServiceInfo:
    """Wrap manufacturer data as received from the Bluetooth integration."""
    return BluetoothServiceInfo(
        name, ADDRESS, rssi, {parser.COMPANY_IDENTIFIER: raw_data}, {}, [], "local"
    )


def test_device_update() -> None:
    """A DIY gadget becomes a device with its signals and signal strength."""
    device = parser.SensirionBluetoothDeviceData()
    update = device.update(service_info("S", advertisement(36, 812), rssi=-71))
    assert device.get_device_name() == "Sensirion Gadget 3412"
    values = {
        key.key: value.native_value for key, value in update.entity_values.items()
    }
    assert values == {"carbon_dioxide": 812, "signal_strength": -71}
    assert update.devices[None].model == "Sensirion gadget, sample type 36"


@pytest.mark.parametrize(
    ("name", "device_name"),
    [
        ("S", "Sensirion Gadget 3412"),
        (ADDRESS, "Sensirion Gadget 3412"),
        ("MyAir", "MyAir 3412"),
    ],
)
def test_device_name(name: str, device_name: str) -> None:
    """The one-letter DIY name and a missing scan response get a readable name."""
    device = parser.SensirionBluetoothDeviceData()
    device.update(service_info(name, advertisement(36, 812)))
    assert device.get_device_name() == device_name


def test_unsupported_device() -> None:
    """A gadget of the built-in integration is not claimed."""
    device = parser.SensirionBluetoothDeviceData()
    assert not device.supported(service_info("S", advertisement(6, 0, 0)))
