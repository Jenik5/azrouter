# <img src="https://raw.githubusercontent.com/Jenik5/azrouter/main/custom_components/azrouter/icons/logo.png" height="60" />
# AZ Router – Home Assistant Integration

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom%20Repository-orange.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)
![Version](https://img.shields.io/github/v/release/Jenik5/azrouter)
![Downloads](https://img.shields.io/github/downloads/Jenik5/azrouter/total)
![License](https://img.shields.io/github/license/Jenik5/azrouter?style=flat&v=1)

*(🇨🇿 For Czech version click here → [Czech README](#-česky---az-router---home-assistant-integrace))*

Native Home Assistant integration for devices from the **A-Z Router** ecosystem:

- **AZ Router Smart Master**
- **AZ Router Smart Slave** (`deviceType=1`)
- **AZ Charger Cube / Wallbox** (`deviceType=4`)
- other compatible A-Z devices using the same API

The integration focuses on direct API control, correct Home Assistant entities, and predictable device-level services.

![Migration warning](https://img.shields.io/badge/Migration%20warning-entity%20IDs%20may%20change-red.svg)
> 🔴 **Important migration warning:** This release can recreate some entities with new names or unique IDs. After upgrade, some old entities can disappear and new ones can be created. Check dashboards, panels, automations, and helpers that reference AZ Router entities.

---

## Features

### Data refresh
- Combined refresh of master status, master power, devices, and settings
- Device entities linked to real Home Assistant devices
- Automatic refresh through `DataUpdateCoordinator`

### Master
- Sensors for master status and power data
- Number entity for target power
- Services:
  - `azrouter.set_master_boost`
  - `azrouter.set_device_boost`

### Smart Slave (`deviceType=1`)
- Sensors for temperatures, phases, power, status, and diagnostics
- Numbers for:
  - `1. Max Power`
  - `2.1 Target Temperature`
  - `2.2 Boost Target Temperature`
- Switches for:
  - connected phases
  - `3.1 Keep Heated`
  - `3.2 Block Solar Heating`
  - `3.3 Block Heating From Battery`
  - `3.4 Allow Solar Heating Only In Time Window`
  - boost windows
  - device boost
- Time entities for:
  - `3.4.1 Window Start`
  - `3.4.2 Window Stop`
  - boost windows
- Select entity for:
  - `4.2 Boost Mode`
- Services for the main Smart Slave settings above

### Wallbox (`deviceType=4`)
- Sensors for charging state, current, temperature, breaker, total power, and diagnostics
- Switches for:
  - `1. Block Charging`
  - `2. Prioritize When Connected`
  - `3. Block Solar Charging`
  - `4. Block Charging From Battery`
  - `6.1 Allow Solar Charging Only In Time Window`
  - `8. Apply Only If Cloud Is Offline`
  - `9.1 Time Window Charging Enabled`
  - `10.1 HDO Charging Enabled`
  - device boost
- Select entity for:
  - `5. Triggering Phase`
- Numbers for:
  - `6.4 Trigger On Power`
  - `6.5 Trigger On Duration`
  - `6.6 Trigger Off Power`
  - `6.7 Trigger Off Duration`
  - `7.1 Manual Charging Power`
  - `9.2 Power`
  - `10.2 HDO Charging Power`
- Time entities for:
  - `6.2 Start Time`
  - `6.3 Stop Time`
  - `9.3` to `9.8` charging window times
- Dedicated services for the main wallbox toggle/select settings

### Notes
- Device-level services use the HA device target, so they work naturally with Device Picker.
- Number and time entities can be controlled directly with native Home Assistant services such as `number.set_value` and `time.set_value`.

---

## Configuration

During integration setup, enter:

- **Host or URL**
  Example: `http://192.168.xxx.xxx`
- **User**
  Your web UI username
- **Password**
  Your web UI password

These are the same credentials you use to log into the AZ Router web interface.

---

## Installation via HACS (custom repository for now)

At the moment, the integration is **not listed in the default HACS store index**, so direct search in the store may not find it. Install it as a **custom repository**:

1. Open **HACS → Integrations**
2. Open the menu and choose **Custom repositories**
3. Add `https://github.com/Jenik5/azrouter`
4. Set category to **Integration**
5. Install the integration
6. Restart Home Assistant
7. Add the integration in **Settings → Devices & Services**

---

## Manual Installation

1. Download this repository as ZIP
2. Extract it into:

```text
/config/custom_components/azrouter/
```

3. Restart Home Assistant
4. Add the integration in **Settings → Devices & Services**

---

## Scope

The project intentionally stays pragmatic:

- expose what the device API actually supports
- keep Home Assistant entities and services predictable
- add support for new A-Z devices when real payload samples are available

The integration does not try to add its own energy-routing logic or automation layer.

---

## Troubleshooting / Contribution

Useful things for debugging and support:

- Home Assistant logs from `custom_components.azrouter`
- JSON snapshots from the AZ Router API
- the exact device type and firmware version

Issues and payload samples are welcome on GitHub.

---

# 🇨🇿 Česky – AZ Router – Home Assistant Integrace

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom%20Repository-orange.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)
![Version](https://img.shields.io/github/v/release/Jenik5/azrouter)
![Downloads](https://img.shields.io/github/downloads/Jenik5/azrouter/total)
![License](https://img.shields.io/github/license/Jenik5/azrouter)

Nativní integrace pro zařízení rodiny **A-Z Router**:

- **AZ Router Smart Master**
- **AZ Router Smart Slave** (`deviceType=1`)
- **AZ Charger Cube / Wallbox** (`deviceType=4`)
- další kompatibilní A-Z zařízení používající stejné API

Integrace je zaměřená na přímou práci s API, správné Home Assistant entity a předvídatelné služby na úrovni zařízení.

![Migrační upozornění](https://img.shields.io/badge/Migrace-entity%20se%20mohou%20zm%C4%9Bnit-red.svg)
> 🔴 **Důležité migrační upozornění:** Tato verze může některé entity vytvořit znovu pod novým názvem nebo s novým `unique_id`. Po aktualizaci tak mohou některé staré entity zaniknout a vzniknout nové. Po upgradu zkontrolujte dashboardy, uživatelské panely, automatizace i helpery, které na entity AZ Routeru odkazují.

---

## Co integrace aktuálně umí

### Obnovování dat
- společné načítání `status`, `power`, `devices` a `settings`
- zařízení jsou správně zapsaná do Home Assistant Device Registry
- automatická aktualizace přes `DataUpdateCoordinator`

### Master
- senzory pro stav a výkon master jednotky
- number entita pro cílový výkon
- služby:
  - `azrouter.set_master_boost`
  - `azrouter.set_device_boost`

### Smart Slave (`deviceType=1`)
- senzory pro teploty, fáze, výkon, stav a diagnostiku
- number entity pro:
  - `1. Max Power`
  - `2.1 Target Temperature`
  - `2.2 Boost Target Temperature`
- switche pro:
  - připojené fáze
  - `3.1 Keep Heated`
  - `3.2 Block Solar Heating`
  - `3.3 Block Heating From Battery`
  - `3.4 Allow Solar Heating Only In Time Window`
  - boost okna
  - device boost
- time entity pro:
  - `3.4.1 Window Start`
  - `3.4.2 Window Stop`
  - boost okna
- select entita pro:
  - `4.2 Boost Mode`
- služby pro hlavní nastavení Smart Slave

### Wallbox (`deviceType=4`)
- senzory pro stav nabíjení, proudy, teplotu, jistič, celkový výkon a diagnostiku
- switche pro:
  - `1. Block Charging`
  - `2. Prioritize When Connected`
  - `3. Block Solar Charging`
  - `4. Block Charging From Battery`
  - `6.1 Allow Solar Charging Only In Time Window`
  - `8. Apply Only If Cloud Is Offline`
  - `9.1 Time Window Charging Enabled`
  - `10.1 HDO Charging Enabled`
  - device boost
- select entita pro:
  - `5. Triggering Phase`
- number entity pro:
  - `6.4 Trigger On Power`
  - `6.5 Trigger On Duration`
  - `6.6 Trigger Off Power`
  - `6.7 Trigger Off Duration`
  - `7.1 Manual Charging Power`
  - `9.2 Power`
  - `10.2 HDO Charging Power`
- time entity pro:
  - `6.2 Start Time`
  - `6.3 Stop Time`
  - `9.3` až `9.8` časová okna nabíjení
- samostatné služby pro hlavní wallbox switche a volbu fáze

### Poznámky
- služby na úrovni zařízení používají HA device target, takže dobře fungují s Device Pickerem
- number a time entity lze ovládat i nativními Home Assistant službami jako `number.set_value` a `time.set_value`

---

## Konfigurace

Při nastavování integrace zadejte:

- **Host nebo URL**
  například `http://192.168.xxx.xxx`
- **Uživatel**
  přihlašovací jméno do webového rozhraní
- **Heslo**
  přihlašovací heslo do webového rozhraní

Jsou to stejné údaje, které používáte pro přístup do webového rozhraní A-Z Routeru.

---

## Instalace přes HACS (zatím jako custom repository)

Integrace momentálně **není zařazená v defaultním HACS indexu**, takže přímé hledání ve Store ji nemusí najít. Instalace proto zatím probíhá jako **custom repository**:

1. Otevřete **HACS → Integrace**
2. V menu zvolte **Custom repositories**
3. Přidejte `https://github.com/Jenik5/azrouter`
4. Nastavte kategorii **Integration**
5. Integraci nainstalujte
6. Restartujte Home Assistant
7. Přidejte integraci v **Nastavení → Zařízení a služby**

---

## Manuální instalace

1. Stáhněte tento repozitář jako ZIP
2. Rozbalte jej do:

```text
/config/custom_components/azrouter/
```

3. Restartujte Home Assistant
4. Přidejte integraci v **Nastavení → Zařízení a služby**

---

## Rozsah projektu

Projekt je záměrně pragmatický:

- vystavit to, co zařízení skutečně podporuje přes API
- držet entity a služby v Home Assistantu předvídatelné
- doplňovat nové A-Z typy zařízení podle reálných payload vzorků

Integrace se nesnaží přidávat vlastní logiku energy routingu nebo automatizační vrstvu.

---

## Troubleshooting / příspěvky

Pro řešení problémů a rozšíření jsou užitečné hlavně:

- Home Assistant logy z `custom_components.azrouter`
- JSON snapshoty z AZ Router API
- přesný typ zařízení a verze firmware

Issues a payload ukázky jsou vítané na GitHubu.

---
