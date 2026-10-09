# Sensirion BLE for Home Assistant, with DIY gadgets

A drop-in replacement for the built-in **Sensirion BLE** integration of Home
Assistant that also accepts DIY gadgets built with Sensirion's
[arduino-ble-gadget](https://github.com/Sensirion/arduino-ble-gadget) library.

The built-in integration only decodes three advertisement formats (sample
types 4, 6 and 8: SHT3x/SHT4x gadgets and the MyCO2 gadget). A DIY gadget that
advertises anything else, for example temperature, humidity, CO2, VOC, PM2.5
and formaldehyde in one sample, is rejected as "Device not supported".

This version decodes the live-data sample types published by Sensirion in the
[BLE services specification](https://sensirion.github.io/ble-services/#/live-data).

## Supported sample types

| Sample type | Signals | Typical source |
|---|---|---|
| 3 | temperature, humidity, VOC index | AQ Minion |
| 4 | temperature, humidity | SHT3x |
| 6 | temperature, humidity | SHT40 Gadget, SHT43 Demo Board |
| 8, 10 | temperature, humidity, CO2 | MyCO2 Gadget, CO2 sensors |
| 12, 28 | temperature, humidity, CO2, PM2.5 | SEN63C |
| 14 | temperature, humidity, formaldehyde | formaldehyde sensors |
| 16, 30 | temperature, humidity, VOC index, PM2.5 | SEN54, SEN55, SEN65 |
| 20, 32 | temperature, humidity, CO2, VOC index, PM2.5, formaldehyde | SEN69C, DIY |
| 22 | temperature, humidity, VOC index, NOx index | |
| 24 | temperature, humidity, VOC index, NOx index, PM2.5 | SEN55 |
| 26 | temperature, humidity, CO2, VOC index, NOx index, PM2.5 | SEN66 |
| 34 | PM1, PM2.5, PM4, PM10 | SEN50, SEN60 |
| 36 | CO2 | CO2 sensors |
| 42 | temperature, humidity, PM2.5 | SEN62 |
| 44 | temperature, humidity, formaldehyde, VOC index, NOx index, PM2.5 | SEN68 |

Sample types 38 (air velocity) and 40 (H2, pressure) are not decoded: the
specification gives no unit for those signals.

## What has been tested

- Sample type 20, from an ESP32 with SCD30 + SFA30 + SEN54 running
  arduino-ble-gadget (`DataType::T_RH_CO2_VOC_PM25_HCHO`), received through an
  ESPHome Bluetooth proxy, on Home Assistant 2026.9.
- Sample types 4, 6 and 8 give the same values as the built-in integration
  (compared in code, not with real gadgets).

All other sample types are implemented from the specification and have not
been checked against real hardware. Reports are welcome.

## Installation

The integration uses the same domain as the built-in one (`sensirion_ble`), so
it replaces it. Home Assistant logs a warning about a custom integration
overriding a core one; that is expected.

**HACS:** add this repository as a custom repository of type *Integration*,
install it and restart Home Assistant.

**Manual:** copy `custom_components/sensirion_ble` into the
`custom_components` folder of your Home Assistant configuration and restart.

Gadgets in range are then discovered automatically (Settings → Devices &
services), provided the Bluetooth integration or a Bluetooth proxy is working.
To go back to the built-in integration, delete the folder and restart.

## Notes

- Advertisements are passive: no connection is made to the gadget, so the
  Sensirion MyAmbience app keeps working alongside.
- DIY gadgets advertise the one-letter name `S`; they are shown as
  `Sensirion Gadget XXXX`, where `XXXX` is the device id from the
  advertisement.
- The VOC and NOx indices and formaldehyde (ppb) have no matching device
  class in Home Assistant, so they are plain measurement sensors.

## Credits and license

Based on the `sensirion_ble` integration of
[Home Assistant Core](https://github.com/home-assistant/core) and on the
[sensirion-ble](https://github.com/akx/sensirion-ble) library by @akx.
Sample formats from Sensirion's
[BLE services specification](https://sensirion.github.io/ble-services/).
Not affiliated with or endorsed by Sensirion AG.

Licensed under the Apache License 2.0; see `LICENSE` and `NOTICE`.
