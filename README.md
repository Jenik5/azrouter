# <img src="https://raw.githubusercontent.com/Jenik5/azrouter/main/custom_components/azrouter/icons/logo.png" height="60" />  
# AZ Router – Home Assistant Integration

[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://hacs.xyz)
![Version](https://img.shields.io/github/v/release/Jenik5/azrouter)
![Downloads](https://img.shields.io/github/downloads/Jenik5/azrouter/total)
![License](https://img.shields.io/github/license/Jenik5/azrouter?style=flat&v=1)

*(🇨🇿 For Czech version click here → [Czech README](#-česky---az-router---home-assistant-integrace))*

Native Home Assistant integration for devices from the **A-Z Router** ecosystem:

- **AZ Router Smart Master**
- **AZ Router Smart Slave**
- **AZ Charger Cube**
- and other compatible A-Z devices using the same API

This project aims to provide a clean, reliable API-based integration with properly structured entities, device registry entries, and services.

---

## 🔧 Current Features

### ✔ Master & Device Data
- Parsing of all master data (`all_data`)
- Data for each device via device API
- Automatic refresh via DataUpdateCoordinator

### ✔ Entities
- Sensors (power, temperature, current, operational states…)
- Switches (Boost)
- Numbers (target power, target temperature — depending on device type)

### ✔ Services
- `azrouter.set_master_boost`
- `azrouter.set_device_boost` — fully supports HA Device Picker

### ✔ Multi-Device Support
Each A-Z device appears as a separate “Device” in Home Assistant.

---

## 🛠 Configuration

During integration setup, enter:

- **Host or URL:**  
  `http://192.168.xxx.xxx`

- **User:**  
  `web_ui_username`

- **Password:**  
  `web_ui_password`

These are the same credentials you use to log into the device’s web interface.

---

## 📦 Installation (via HACS)

The integration is now directly available in **HACS**.

Steps:

1. Open **HACS → Integrations**
2. Search for **“AZ Router”**
3. Install
4. Restart Home Assistant
5. Go to **Settings → Devices & Services** and add the integration

---

## 📥 Manual Installation

1. Download this repository as ZIP  
2. Extract into:

```
/config/custom_components/azrouter/
```

3. Restart Home Assistant  
4. Add the integration via Settings

---

## 🧩 Future Improvements (Conservative Roadmap)

We intentionally keep the scope narrow:

- Adding more sensors, switches, or numbers where useful  
- Adding more services when supported by the device API  
- Support for new A-Z devices **if users provide JSON dumps**  

No complex energy algorithms or automation logic — just clean HA entities.

---

## 🧪 Beta Testing

You can help by:

- Reporting issues on GitHub  
- Providing debug logs  
- Sending JSON dumps from unsupported A-Z devices  

---

---

# 🇨🇿 Česky – AZ Router – Home Assistant Integrace

![HACS](https://img.shields.io/badge/HACS-Default-blue.svg)
![Version](https://img.shields.io/github/v/release/Jenik5/azrouter)
![Downloads](https://img.shields.io/github/downloads/Jenik5/azrouter/total)
![License](https://img.shields.io/github/license/Jenik5/azrouter)

Nativní integrace pro zařízení rodiny **A-Z Router**:

- AZ Router Smart Master  
- AZ Router Smart Slave  
- AZ Charger Cube  
- a další zařízení používající stejné API  

Integrace poskytuje stabilní propojení s API zařízení a vystavuje správné entity, služby a záznamy v Device Registry.

---

## 🔧 Co integrace umí

### ✔ Načítání dat
- kompletní data z Master jednotky (`all_data`)
- data jednotlivých zařízení
- automatická aktualizace přes DataUpdateCoordinator

### ✔ Entity
- senzory (výkon, teploty, proudy, stav…)
- switche (např. Boost)
- čísla (cílový výkon, cílová teplota – dle jednotky)

### ✔ Služby
- `azrouter.set_master_boost`
- `azrouter.set_device_boost` – včetně **Device Pickeru**

### ✔ Podpora více zařízení
Každé zařízení se objeví jako samostatné „Device“ v Home Assistantu.

---

## 🛠 Základní konfigurace

Při nastavování integrace zadejte:

- **Host nebo URL:**  
  `http://192.168.xxx.xxx`

- **Uživatel:**  
  `web_ui_username`

- **Heslo:**  
  `web_ui_password`

Jsou to stejné údaje, jaké používáte pro přístup do webového rozhraní A-Z Routeru.

---

## 📦 Instalace přes HACS

Integrace je dostupná **přímo v HACS**:

1. Otevřete **HACS → Integrace**
2. Vyhledejte **„AZ Router“**
3. Instalujte
4. Restartujte HA
5. Přidejte integraci přes **Nastavení → Zařízení a služby**

---

## 📥 Manuální instalace

1. Stáhněte ZIP  
2. Rozbalte do:

```
/config/custom_components/azrouter/
```

3. Restartujte Home Assistant  
4. Přidejte integraci

---

## 🧩 Možnosti rozšíření

Držíme se realistického rozsahu:

- doplnění dalších senzorů / switchů / number entit  
- doplnění dalších služeb (pokud je podporuje API)  
- podpora nových jednotek **pokud uživatelé poskytnou JSON výpis**  

---

## 🧪 Testování

Pomůžete nám, pokud:

- nahlásíte chyby  
- pošlete logy  
- pošlete JSON výpisy z neznámých jednotek  

---

