"""Diagnostics support for sensirion_ble_diy."""

from typing import Any

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.core import HomeAssistant

from . import SensirionBluetoothConfigEntry
from .parser import COMPANY_IDENTIFIER, parse_advertisement


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SensirionBluetoothConfigEntry
) -> dict[str, Any]:
    """Return the last advertisement of the gadget, raw and decoded."""
    address = entry.unique_id
    assert address is not None
    service_info = async_last_service_info(hass, address, connectable=False)
    if service_info is None:
        return {"address": address, "last_advertisement": None}

    raw_data = service_info.manufacturer_data.get(COMPANY_IDENTIFIER)
    advertisement: dict[str, Any] = {
        "name": service_info.name,
        "rssi": service_info.rssi,
        "source": service_info.source,
        "manufacturer_data": raw_data.hex() if raw_data is not None else None,
    }
    if raw_data is not None and (result := parse_advertisement(raw_data)):
        device_id, sample_type, values = result
        advertisement["device_id"] = device_id
        advertisement["sample_type"] = sample_type
        advertisement["values"] = {signal.key: value for signal, value in values}
    return {"address": address, "last_advertisement": advertisement}
