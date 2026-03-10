# Changelog

![Migration warning](https://img.shields.io/badge/Migration%20warning-entity%20IDs%20may%20change-red.svg)

> 🔴 **Important migration warning / Dulezite migracni upozorneni:** This update can recreate some entities with new names or unique IDs. Old entities can disappear and new ones can be created. After upgrade, review dashboards, custom panels, automations, and helpers that reference AZ Router entities.

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
