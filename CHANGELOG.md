# Changelog

![Migration warning](https://img.shields.io/badge/Migration%20warning-entity%20IDs%20may%20change-red.svg)

> 🔴 **Important migration warning / Dulezite migracni upozorneni:** This update can recreate some entities with new names or unique IDs. Old entities can disappear and new ones can be created. After upgrade, review dashboards, custom panels, automations, and helpers that reference AZ Router entities.

## 2026.04.03.1 - 2026-04-03

### Changed
- Preserved the last known endpoint data during partial AZ Router API failures instead of replacing failed sections with empty payloads.
- This prevents transient `unavailable` states for device entities when only one endpoint, such as `/api/v1/devices`, times out briefly.

## 2026.03.23.1 - 2026-03-23

### Changed
- Added one immediate retry for full refresh failures when all AZ Router API endpoints fail in the same polling cycle.
- This reduces short transient disconnects when the device briefly stops responding and recovers within about one second.

## 2026.03.10.2 - 2026-03-10

### Changed
- Fixed `services.yaml` to use supported `device_id` selectors instead of invalid device-filter targets.
- Sorted manifest keys to satisfy Hassfest validation.
- Removed unsupported `domains` from `hacs.json`.
- Added local integration brand assets under `custom_components/azrouter/brand/`.
- Aligned the repository with HACS validation requirements before default repository submission.

## 2026.03.10.1 - 2026-03-10

### Added
- Expanded `deviceType=1` Smart Slave support with new switches, time entities, select entities, and matching device services.
- Expanded `deviceType=4` Wallbox support with new switches, numbers, times, select entities, and matching device services.
- Added localized service translations for `cs`, `en`, `de`, `pl`, and `sk`.
- Added GitHub Actions workflows for HACS validation and Hassfest validation.

### Changed
- Aligned Smart Slave and Wallbox entity naming with numbered AZ Router settings where that improves clarity.
- Added UI availability guards for dependent Smart Slave and Wallbox settings.
- Updated installation instructions to describe HACS custom repository installation instead of default-store discovery.
- Updated integration metadata for clearer HACS and Home Assistant compatibility.

### Notes for Upgrades
- Existing dashboards or custom UI panels can need manual repair if they reference entity IDs that were recreated.
- Existing automations, scripts, template sensors, and helpers can need the same review.
- HACS direct discovery in the default store still requires a GitHub release and submission to `hacs/default`; until then, install via custom repository URL.
