# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-09-25

### Added

- Link diagnostics: `consecutive failures` and `last successful update`
  diagnostic sensors.
- Distinct transport error types (`PaceexConnectError` for unreachable hosts,
  `PaceexReceiveError` for resets/timeouts/closed connections) so logs tell
  an unreachable BMS apart from one rejecting queries.

### Changed

- Each poll cycle now uses a single persistent TCP connection for the status
  and cell queries instead of reconnecting between them.
- Setup validation reads serial, status, and cell data through one paced TCP
  session instead of opening back-to-back connections.
- Default polling interval raised from `15` to `30` seconds; the module
  handles one connection at a time and aggressive polling caused
  `unavailable` states.
- Battery telemetry becomes unavailable after 3 consecutive failed polls while
  diagnostic entities remain available and continue reporting failure count
  and the time of the last successful update.
- Replaced the nested retry layers with a single reconnect (after a 2-second
  cooldown) per query; a still-failing adapter is left alone until the next
  cycle instead of being hammered with reconnect storms.

### Fixed

- Read binary responses using the frame's declared length instead of stopping
  whenever a TCP fragment happens to end in `0x9D`; payload bytes can legally
  contain that value.
- Handle fragmented TCP responses and early connection closes deterministically.
- Remove the redundant serial-number query during sensor setup.

## [0.1.3] - 2026-07-20

### Fixed

- Retry each protocol query independently with backoff so a transient cell
  query failure does not discard an already successful status query.

## [0.1.2] - 2026-07-20

### Added

- Add an options flow for changing the polling interval after setup.

### Fixed

- Wait for the BMS Wi-Fi adapter to accept connections before querying cell
  voltages, preventing repeated unavailable states.

## [0.1.1] - 2026-07-18

### Fixed

- Retry transient TCP and protocol failures before marking entities unavailable.
- Improve reliability when a BMS Wi-Fi module is briefly busy or another client
  is connected.

## [0.1.0] - 2026-07-18

### Added

- Local TCP communication with PeiCheng/PACEEX Smart BMS Wi-Fi modules.
- UI-based setup with connection and protocol validation.
- Battery SOC, SOH, voltage, current, power, capacity, and cycle sensors.
- Individual cell voltage sensors and cell minimum, maximum, and delta sensors.
- English and Spanish translations.
- Automatic availability handling through Home Assistant's update coordinator.

[1.3.0]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.3...v1.3.0
[0.1.3]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/tuxevil/ha_paceex_smart_bms/releases/tag/v0.1.0
