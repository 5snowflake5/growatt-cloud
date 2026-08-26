# Changelog

Alle bemerkenswerten Änderungen an **Growatt Cloud**.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/).

## [0.1.16] – 2026-08-26

### Fixed
- Noah 2-Turm-Stack: **PV3/PV4** (Turm 2) bleiben fest als Entities – auch bei 0 W, mit Namen „Tower 2“.
- PV1/PV2 als „Tower 1“; Log zeigt PV1–4 einzeln.

## [0.1.15] – 2026-08-26

### Fixed
- Noah/Nexa: PV1–PV4 bleiben immer sichtbar (auch 0 W) – wurden vorher als „inaktiv“ entfernt.
- Stack mit mehreren Batterie-Türmen im Gerätenamen erkennbar (`Noah 2T …`).

### Note
- Der zweite Batterie-Turm hat in der Growatt-API **keine eigenen PV-Werte** – nur Battery 2 SoC/Temp. PV ist systemweit (Solar Power + PV1–4).

## [0.1.14] – 2026-08-26

### Changed
- Energy-Limit wieder **pro Geräte-SN** (Noah und Nexa dürfen beide ~1/min) – der globale 1-Slot war zu streng.
- Kurze Pause zwischen Requests bleibt, damit Bursts keinen code 102 auslösen.
- Info/WiFi weiterhin ohne Energy-Slot; beide Speicher werden wieder je Zyklus gepollt wenn fällig.

## [0.1.13] – 2026-08-26

### Fixed
- Noah + Nexa teilen sich 1 Energy-Abruf/Min: bisher hat oft nur eines Daten bekommen (Rate-Limit), der andere (z. B. Noah mit 2 Türmen / PV) blieb leer.
- DeviceInfo/WiFi verbrauchen den Energy-Slot nicht mehr.
- Round-Robin: pro Loop nur ein Speicher – abwechselnd Noah und Nexa (ca. alle 2 Min je Gerät).

## [0.1.12] – 2026-08-26

### Fixed
- API Rate-Limit (code 102): Noah/Nexa und MIN werden **account-weit** gedrosselt (nicht pro Gerät), plus 65 s Backoff nach 102.
- Warnung im Log, wenn `sensor_mode=full` aktiv ist.

### Note
- Für ~25–30 Sensoren in der App-Config **`sensor_mode: useful`** setzen (nicht `full`).

## [0.1.11] – 2026-08-26

### Fixed
- Nexa-Erkennung: Serial aus der Geräteliste hat Vorrang; `0HVR`/`HVR` → Nexa (vor Model-Text).
- `useful`-Modus baut Sensoren nur noch aus Whitelist (kein Rohdaten-Leak für Speicher/WR).
- HA-Gerätename/Model erzwingen (`Nexa …` / `Growatt Nexa`), damit alte „Noah“-Namen überschrieben werden.

### Changed
- Log zeigt `mode=useful entities=N` für Speicher und WR.

## [0.1.10] – 2026-08-26

### Fixed
- Crash `AttributeError: 'dict' object has no attribute 'add'` beim Discovery-Purge (`_subscribed_nodes` war versehentlich ein Dict).

## [0.1.9] – 2026-08-26

### Fixed
- Alte MQTT-Discovery-Entities (Full-Dump) werden beim Start aktiv entfernt (Purge-Liste + Subscribe).
- Discovery-Key-Cache bleibt über MQTT-Reconnect erhalten, damit Purge funktioniert.

### Changed
- Log zeigt `mode=useful` und Anzahl der Entities sowie Purge-Zähler.

## [0.1.8] – 2026-08-26

### Changed
- MIN-Wechselrichter: aggressives Filtern (BMS/BDC/EPS-Nullfelder, Einphasen-S/T, PV3/4, Duplikate).
- `useful` liefert für typische Balkon-WR ca. 25–30 Sensoren statt 200+.

## [0.1.7] – 2026-08-26

### Added
- Option `sensor_mode`: `useful` (Default) oder `full`.

### Changed
- Default veröffentlicht nur sinnvolle Live-Sensoren; Duplikate, leere Felder, Zeitfenster-Config und Phantom-Packs entfallen.

## [0.1.6] – 2026-08-26

### Fixed
- Noah vs Nexa: korrekte Erkennung über Serial-Präfix (`0PVP` / `0HVR`), Model und Alias (API-Typ ist bei beiden `noah`).
- HA-Gerätename aus Alias/Model statt generischem „Noah“.

### Changed
- Nur vorhandene Batterie-Packs als Entities (keine leeren Pack 3/4).

## [0.1.5] – 2026-08-26

### Added
- Alle skalaren Felder aus `queryLastData` + `queryDeviceInfo` + WiFi-Signal.
- Freundliche Aliase (`soc`, `solar_power`, `ac_power`, …) bleiben erhalten.

## [0.1.4] – 2026-08-26

### Changed
- Keine manuellen Serials / Speichertypen mehr – Geräte nur noch aus der API-Geräteliste.
- Erweiterte Noah/Nexa- und MIN-Sensor-Maps (Packs, PV-Strings, Limits, …).

## [0.1.0] – 2026-08-26

### Added
- Erstes Add-on: Growatt Open API Token, v4 `queryLastData`, MQTT Discovery für Noah/Nexa + MIN.
- Schonendes Polling (Noah ≥60 s, andere ≥300 s).
