# PACEEX Smart BMS for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/tuxevil/ha_paceex_smart_bms?display_name=tag)](https://github.com/tuxevil/ha_paceex_smart_bms/releases)
[![License](https://img.shields.io/github/license/tuxevil/ha_paceex_smart_bms)](LICENSE)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

A read-only Home Assistant custom integration for PeiCheng/PACEEX Smart BMS
Wi-Fi modules. It communicates directly with the BMS over the local network—no
vendor cloud, mobile application, MQTT broker, or external polling service is
required.

## Highlights

- Fully local polling over TCP.
- Configuration through the Home Assistant UI.
- One coordinated request cycle for all entities.
- Automatic availability and reconnect handling.
- Individual cell voltage monitoring.
- English and Spanish UI translations.
- No Python package dependencies outside Home Assistant Core.
- Read-only implementation: the integration never changes BMS settings.

## Compatibility

This integration targets PeiCheng/PACEEX Smart BMS units whose wireless module:

- appears over Bluetooth with a name beginning with `PC-` (for example,
  `PC-CFBA`);
- exposes a local TCP service, commonly on port `8888`; and
- uses the PACEEX binary protocol with frames beginning with `0x9A` and ending
  with `0x9D`.

It was initially developed and tested against a 16-cell, 100 Ah PACEEX BMS
used in a MUST battery system. Other capacities and cell counts should work
when they use the same protocol, but reports from additional hardware are
welcome.

> [!NOTE]
> A battery using the PACE RS232/RS485 ASCII protocol is not necessarily
> compatible. This integration targets the binary protocol exposed by the
> PACEEX Wi-Fi/Bluetooth module.

## Entities

The integration creates one Home Assistant device with the following sensors:

| Sensor | Unit | Description |
| --- | ---: | --- |
| State of charge | % | Remaining charge reported by the BMS |
| State of health | % | Battery health reported by the BMS |
| Battery voltage | V | Total pack voltage |
| Battery current | A | Signed pack current |
| Battery power | W | Calculated from pack voltage and current |
| Remaining capacity | Ah | Remaining charge capacity |
| Design capacity | Ah | Configured nominal capacity |
| Battery cycles | — | BMS cycle counter |
| Cell count | — | Number of cells reported by the BMS |
| Cell 01…NN voltage | V | Voltage of each individual cell |
| Minimum cell voltage | V | Lowest reported cell voltage |
| Maximum cell voltage | V | Highest reported cell voltage |
| Cell voltage delta | V | Difference between highest and lowest cell |

## Requirements

- Home Assistant 2025.1 or newer.
- Home Assistant must be able to reach the BMS IP address and TCP port.
- The BMS Wi-Fi module must be connected to the same network or to a routable
  network segment.
- Assigning the BMS a DHCP reservation is strongly recommended.

## Installation

### HACS custom repository

Until this repository is included in the default HACS catalog:

1. Open HACS in Home Assistant.
2. Select **Integrations**.
3. Open the three-dot menu and select **Custom repositories**.
4. Add `https://github.com/tuxevil/ha_paceex_smart_bms` as an
   **Integration** repository.
5. Search for **PACEEX BMS** and install it.
6. Restart Home Assistant.

### Manual installation

1. Download the latest release.
2. Copy `custom_components/paceex_bms` into your Home Assistant configuration
   directory:

   ```text
   /config/custom_components/paceex_bms/
   ```

3. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & services**.
2. Select **Add integration**.
3. Search for **PACEEX BMS**.
4. Enter:
   - **Host:** the local IP address of the BMS Wi-Fi module;
   - **Port:** normally `8888`;
   - **Update interval:** polling interval in seconds (minimum `5`, default
     `15`).

During setup, the integration reads the BMS serial number and a complete status
sample. Configuration is rejected if the endpoint is unreachable or does not
return valid PACEEX frames.

## Finding the BMS on your network

The wireless module may advertise over Bluetooth as `PC-` followed by the last
four hexadecimal characters of its MAC address. The Wi-Fi and Bluetooth
interfaces may share the same MAC address. Check your router's DHCP client list
for that address and create a DHCP reservation once identified.

The vendor's **BMS-TOOL** mobile application can also help confirm the Bluetooth
name. The mobile application is not required after this integration is set up.

## How it works

Home Assistant polls two read-only PACEEX commands:

- system/pack status;
- individual cell data.

Responses are validated for frame markers, declared length, and Modbus CRC
before any entity is updated. Network I/O runs outside Home Assistant's event
loop, and a single `DataUpdateCoordinator` shares each poll across all sensors.

## Troubleshooting

### The integration cannot connect

- Confirm that the BMS answers on its IP address.
- Confirm that the configured TCP port is open; `8888` is common but not
  guaranteed.
- Verify that Home Assistant and the BMS can communicate across VLANs or
  firewall zones.
- Ensure the BMS IP address has not changed.

### BMS-TOOL works remotely, but the integration does not

BMS-TOOL's Wi-Fi mode may use the vendor cloud. This integration requires the
local TCP endpoint to be reachable from Home Assistant.

### Entities become unavailable

The integration marks entities unavailable after a failed update and retries
on the next interval. Check the BMS Wi-Fi signal, DHCP lease, and Home Assistant
logs for `paceex_bms` messages.

### Current or power sign is reversed

The integration preserves the sign reported by the BMS. If a firmware variant
uses the opposite convention, please open an issue with raw diagnostic details,
the observed operating state, and the BMS model.

## Security and safety

- Communication remains on the local network.
- No credentials, accounts, or cloud APIs are used.
- The integration implements only known read commands.
- Home Assistant telemetry must not replace the BMS's physical protection,
  contactors, fuses, or inverter safety limits.

Treat the BMS network as trusted IoT infrastructure. Use firewall rules to
limit access to the local endpoint where appropriate.

## Privacy

The integration does not collect analytics or transmit data outside your Home
Assistant instance. Device readings are stored only according to your Home
Assistant recorder configuration.

## Contributing

Compatibility reports, protocol traces from other PACEEX models, documentation
improvements, and pull requests are welcome. When reporting a new hardware
variant, please include:

- battery brand and model;
- BMS hardware/firmware information, if available;
- cell count and nominal capacity;
- Bluetooth advertising name;
- TCP port;
- Home Assistant log messages with sensitive network details removed.

Do not post passwords, public IP addresses, cloud tokens, or other secrets.

## License

This project is licensed under the [MIT License](LICENSE).

## Disclaimer

This is an independent community project and is not affiliated with or endorsed
by PeiCheng Technology, PACEEX, MUST, BMS-TOOL, or Home Assistant.
