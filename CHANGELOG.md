# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-25

### Added

- Link diagnostics: `consecutive failures` and `last successful update`
  diagnostic sensors.
- Distinct transport error types (`PaceexConnectError` for unreachable hosts,
  `PaceexReceiveError` for resets/timeouts/closed connections) so logs tell
  an unreachable BMS apart from one rejecting queries.

### Changed

- Each poll cycle now uses a single persistent TCP connection for the status
  and cell queries instead of reconnecting between them.
- Default polling interval raised from `15` to `30` seconds; the module
  handles one connection at a time and aggressive polling caused
  `unavailable` states.
- Entities keep their last values through up to 3 consecutive failed polls
  instead of going unavailable on the first failure.
- Replaced the nested retry layers with a single reconnect (after a 2-second
  cooldown) per query; a still-failing adapter is left alone until the next
  cycle instead of being hammered with reconnect storms.

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

[0.2.0]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/tuxevil/ha_paceex_smart_bms/releases/tag/v0.1.0
