# Growatt Cloud

Changelog: [CHANGELOG.md](CHANGELOG.md)

## Releases

**Verbindlich:** [RELEASE.md](../RELEASE.md) im Repo-Root – Version **niemals** manuell in `config.yaml` setzen.

Kurz: Code pushen → Actions **Release add-on** → erst danach HA updaten. CI blockiert manuelle Versions-Upgrades.

## Warum

Ein Growatt-Login statt paralleler MQTT-/Server-Integrationen (weniger Sperr-Risiko).

## Noah und Nexa

Beide laufen in der Open API unter `deviceType=noah`. Die App unterscheidet sie über:

- Model/Alias (`Noah 2000` / `Nexa …`)
- Serial-Präfix (`0PVP…` = Noah, `0HVR…` = Nexa)

## Token holen

1. [openapi.growatt.com](https://openapi.growatt.com) einloggen  
2. Account → **API Token** erzeugen/kopieren  
3. In der App-Config unter `api_token` eintragen  

## Intervalle (Growatt-Limits)

| Gerät | Minimum |
|-------|---------|
| Noah / Nexa | 60 s **pro Gerät** (Noah und Nexa parallel möglich) |
| MIN-WR / andere | 300 s |
| Geräteliste | stündlich (Default) |

## Sensor-Modus

Option `sensor_mode`:

- **`useful`** (Default): schlanke Live-Sensoren. Beim MIN-WR u. a. ohne BMS/BDC/EPS-Nullfelder, ohne Einphasen-S/T, ohne Duplikate (Pac/Eac/Epv…).
- **`full`**: mehr Felder, aber weiterhin bereinigt (kein Balkon-„Wahnsinn“ mit 200 Null-Sensoren).

Nach dem Update App **neu starten**. Im Log sollte stehen:
`HA-Discovery-Purge … Alt-Entities entfernt` und `mode=useful → ~30 Entities`.

Falls in HA trotzdem Alt-Entities bleiben: Gerät einmal löschen
(Einstellungen → Geräte → Growatt … → löschen), App neu starten.

## Stack / Solar-Split (ab 0.1.27)

- **`battery1`–`battery4`**: Batterie-**Packs** im Stack (nicht „Speicher 2“ oder „Turm 3“ – das war irreführend).
- **`battery_num`**: wie viele Packs aktiv gemeldet werden.
- **PV1–PV4**: alle Solar-**Eingänge** am Master-Gerät (ein Noah/Nexa mit WLAN).
- **`solar_power_storage1`** = PV1 + PV2 + PV3 + PV4 (Summe der String-Messungen am Master).
- **`solar_power_other_storage`** = `Solar Power − PV1–4` – Solar von weiteren Speichern/Türmen **ohne** eigene String-Messung am Master (nicht zuordenbar zu Turm 2 vs. 3).
- **`generation_today_storage1` / `generation_today_other_storage`**: Tages-kWh per Integration der Live-Leistung.

Ein **zweites Cloud-Gerät** (eigene Serial, z. B. zweiter Nexa) hat **eigene** PV1–4 und `generation_today` – das ist ein separater Speicher, kein „Other Storage“ am Master.

## Geräte

Serials und Typen werden **automatisch** aus der Geräteliste erkannt.

## Empfohlen nach Sperre

1. Growatt-Account entsperren / Token neu  
2. **noah-mqtt** und **Growatt Server** in HA **aus**  
3. Diese App starten, Log prüfen  
4. MQTT-Gerät unter Einstellungen → Geräte  
