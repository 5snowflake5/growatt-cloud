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

Die App-Config erlaubt 1–86400 s. Werte **unter** den Growatt-Empfehlungen speichern geht – im Log kommt eine Warnung, Rate-Limit (code 102) ist dann möglich.

| Gerät | Empfehlung |
|-------|------------|
| Noah / Nexa | 60 s **pro Gerät** |
| MIN-WR / andere | 300 s |
| Geräteliste | stündlich (Default) |

## Zeitzone

Option `timezone` (IANA, z. B. `Europe/Berlin`):

- leer → Zeitzone von Home Assistant (Supervisor)
- ungültig/nicht erreichbar → UTC

Growatt liefert oft nur einen Offset, keinen IANA-Namen – deshalb nicht als Uhr für Tageswechsel genutzt. `pack_capacity_wh` ist Wh **pro Batterie-Pack** (Noah oft 2048); `battery_energy` = SoC × Packs × dieser Wert.

## MQTT

Wenn User/Pass leer sind, liest die App die Mosquitto-Daten vom Supervisor (`mqtt:need`). Manuell überschreiben geht weiter über `mqtt_host` / `mqtt_user` / `mqtt_password`.

## Sensor-Modus

Option `sensor_mode`:

- **`useful`** (Default): schlanke Live-Sensoren. Idle-Werte bleiben **0** (kein Löschen von Tages-kWh nachts).
- **`full`**: mehr Felder, ohne BMS-Geister auf Balkon-WR.

Zusätzlich am **echten** Nexa/Noah (nicht als Extra-Gerät): `charged_today` / `discharged_today`, `battery_energy`, Netz Import/Export.

Nach dem Update App **neu starten**.

Falls in HA Alt-Entities bleiben: Gerät einmal löschen
(Einstellungen → Geräte → Growatt … → löschen), App neu starten.

## Stack / Solar-Split (ab 0.1.27)

- **`battery1`–`battery4`**: Batterie-**Packs** im Stack.
- **`battery_num`**: wie viele Packs aktiv gemeldet werden.
- **PV1–PV4**: alle Solar-**Eingänge** am Master-Gerät.
- **`solar_power_storage1`** = PV1 + PV2 + PV3 + PV4.
- **`solar_power_other_storage`** = `Solar Power − PV1–4`.
- **`generation_today_storage1` / `generation_today_other_storage`**: Tages-kWh per Integration der Live-Leistung.

Ein **zweites Cloud-Gerät** (eigene Serial) hat **eigene** PV1–4 – das ist ein separater Speicher, kein „Other Storage“ am Master.

## Geräte

Serials und Typen werden **automatisch** aus der Geräteliste erkannt. Jedes echte Gerät (Nexa, Noah, WR) hat seine Sensoren selbst – **kein** virtuelles Plant-Gerät.

Ungenutzte Geräte (z. B. alter Noah): `last_update` älter als `stale_after_hours` (Default 24) → in HA unavailable, Poll nur noch stündlich. Komplett ausnehmen: `skip_serials` in der App-Config (Serial, Komma-getrennt).

## Empfohlen nach Sperre

1. Growatt-Account entsperren / Token neu  
2. **noah-mqtt** und **Growatt Server** in HA **aus**  
3. Diese App starten, Log prüfen  
4. MQTT-Gerät unter Einstellungen → Geräte  
