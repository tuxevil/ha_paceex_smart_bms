# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.1]: https://github.com/tuxevil/ha_paceex_smart_bms/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/tuxevil/ha_paceex_smart_bms/releases/tag/v0.1.0
