# Changelog

Alle bemerkenswerten Änderungen an **Growatt Cloud**.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/).

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
