# Home Assistant – Growatt Cloud

## Einrichtung

1. `growatt_energy.yaml` nach `/config/packages/` kopieren  
2. Optional `speicher_vollast_defizit.yaml` ebenfalls nach packages  
3. In `configuration.yaml`: `homeassistant.packages: !include_dir_named packages`  
4. Neu starten  
5. Helfer **Speicher-Suffix** auf den Kleinbuchstaben-Serial des **Nexa** setzen (`sensor.gc_<suffix>_soc`)  
6. Optional WR-Suffix ebenso  

S0 setzt die Automation um 00:00 aus `sensor.growatt_batterie_wh` (Nexa).

Kein Plant-Gerät. `charged_today` / `battery_energy` liegen am Nexa-MQTT-Gerät.

## Rechnung

| Größe | Quelle |
|-------|--------|
| Speicher jetzt | Nexa `battery_energy` |
| **In die Batterie** | Nexa `charged_today` |
| **Aus der Batterie** | Nexa `discharged_today` |
| **Eigenverbrauch / Autarkie** | Template-Sensoren im Package |
