## 🇬🇧 AZ Router – Home Assistant Integration
*(🇨🇿 For Czech version scroll down or click here → [Czech README](#-česky---az-router---home-assistant-integrace))*

Custom integration for Home Assistant providing native support for devices from the **A-Z Router** family:

- **AZ Router Smart Master**
- **AZ Router Smart Slave**
- **AZ Charger Cube**
- (and other compatible devices that use the same API)

This integration communicates directly with the device API, exposes sensors, entities, and services, and creates a unified view of all devices in the system.

---

## 🔧 Current Features

### ✔ Master & Device Data
- Fetching and parsing of all master data (`all_data`)
- Per-device data from the device API
- Automatic refresh using DataUpdateCoordinator

### ✔ Entities
- Sensors (power, temperatures, currents, state, etc.)
- Switches (e.g., Boost)
- Numbers (target temperature, target power — where relevant)

### ✔ Services
- `azrouter.set_master_boost`
- `azrouter.set_device_boost` — with **Device Picker** support in HA

### ✔ Multiple device support
Each device is registered with its own device entry in Home Assistant device registry.

---

## 🧩 Planned Improvements (Conservative Roadmap)

The integration will be expanded **only** in these limited and realistic directions:

- Adding more sensors, switches or number entities where they make sense
- Adding additional services when the API supports them
- Supporting more A-Z devices **if users provide JSON dumps** of those devices  
  (to ensure correct entity mapping)

No automation logic, no cloud services, no energy algorithms — only API-based HA entities.

---

## 📥 Installation (Manual)

1. Download this repository as ZIP  
2. Extract into:

```
/config/custom_components/azrouter/
```

3. Restart Home Assistant  
4. Go to *Settings → Integrations → Add Integration*  
5. Search for **AZ Router**

---

## 📦 Installation via HACS (Custom Repository)

Until the integration is added to the official HACS index, it can be installed via custom repo:

1. HACS → Integrations  
2. Menu (⋯) → **Custom repositories**  
3. URL:  
   ```
   https://github.com/<your-username>/<your-repo>
   ```
4. Category: **Integration**  
5. Add → Install

---

## 🧪 Looking for Beta Testers

If you use any A-Z Router compatible device, please help test:

- Report issues in GitHub
- Include logs (debug mode recommended)
- If you have a **different A-Z device model**, send its JSON  
  → we can add proper support quickly

---

---

# 🇨🇿 Česky – AZ Router – Home Assistant Integrace

Integrační balíček pro Home Assistant určený pro zařízení rodiny **A-Z Router**:

- AZ Router Smart Master
- AZ Router Smart Slave
- AZ Charger Cube
- a případně další zařízení se stejným API

Integrace zajišťuje komunikaci s API, vytvoření senzorů, entit a služeb a sjednocené zobrazení všech zařízení.

---

## 🔧 Co integrace umí

### ✔ Data Master jednotky
- Načítání kompletních dat (`all_data`)
- Automatický refresh přes DataUpdateCoordinator

### ✔ Přehled zařízení
- Každé zařízení vystaveno jako samostatné „Device“ v Home Assistantu
- Senzory, položky Number a přepínače Switch podle typu jednotky

### ✔ Ovládací služby
- `azrouter.set_master_boost`
- `azrouter.set_device_boost` – s výběrem zařízení z Device Pickeru

---

## 🧩 Možnosti rozšíření

Držíme se jen reálných a jednoduchých rozšíření:

- doplnění dalších senzorů / switchů / number entit
- doplnění dalších služeb, pokud se objeví v API
- podpora nových jednotek **pokud uživatelé poskytnou JSON**
  (výpisy z `/api/v1/…`)

Žádná magie, žádné složité řízení energie — jen čistá integrace API → Home Assistant.

---

## 📥 Instalace (manuálně)

1. Stáhněte ZIP repozitáře  
2. Rozbalte do:

```
/config/custom_components/azrouter/
```

3. Restartujte Home Assistant  
4. V Nastavení → Integrace přidejte **AZ Router**

---

## 📦 Instalace přes HACS (Custom Repository)

1. Otevřete HACS → Integrations  
2. Vpravo nahoře: Custom repositories  
3. Vložte adresu repozitáře  
4. Category: **Integration**  
5. Instalovat

---

## 🧪 Hledáme testery

Pomůže nám:

- nahlášení chyb
- zaslání logů s debug výstupem
- zaslání JSON výpisů z neznámých jednotek (abychom je mohli přidat)

---

