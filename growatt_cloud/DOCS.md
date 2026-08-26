# Growatt Cloud

## Warum

`noah-mqtt` + HA **Growatt Server** = zwei Logins / viele Requests → Account-Sperre.

Diese App: **ein Open-API-Token**, offizielle **v4**-Endpunkte, MQTT → Home Assistant.

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
| Noah / Nexa | 60 s |
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

## Geräte

Serials und Typen werden **automatisch** aus der Geräteliste erkannt.

## Empfohlen nach Sperre

1. Growatt-Account entsperren / Token neu  
2. **noah-mqtt** und **Growatt Server** in HA **aus**  
3. Diese App starten, Log prüfen  
4. MQTT-Gerät unter Einstellungen → Geräte  
