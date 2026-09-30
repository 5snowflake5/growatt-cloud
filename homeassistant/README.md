# Home Assistant – Growatt Cloud

## Einrichtung

1. `growatt_energy.yaml` nach `/config/packages/` kopieren  
2. Optional `speicher_vollast_defizit.yaml` ebenfalls nach packages  
3. In `configuration.yaml`: `homeassistant.packages: !include_dir_named packages`  
4. Neu starten  
5. Optional: Helfer **Wechselrichter-Suffix** auf den Kleinbuchstaben-Serial des MIN-WR setzen (steht in der Entity-ID `sensor.gc_<suffix>_energy_today`)  
6. `noah_board_lovelace.yaml` oder `lovelace_view.yaml` ins Dashboard pasten  

S0 (Batterie-Wh um Mitternacht) setzt die Automation um 00:00 aus `sensor.gc_plant_battery_energy`.

Kapazität kommt aus der Add-on-Option `pack_capacity_wh` × Anzahl Packs, nicht aus einer festen 4096-Wh-Konstante.

## Plant-Sensoren (ohne Serial)

Das Add-on veröffentlicht ein Gerät **Growatt Plant** mit Summe aller Noah/Nexa/WR:

`sensor.gc_plant_soc`, `solar_power`, `output_power`, `charged_today`, `discharged_today`, `generation_today`, `energy_today`, …

Einzelne PV-Strings bleiben am jeweiligen MQTT-Gerät.

## Rechnung

| Größe | Quelle |
|-------|--------|
| Speicher jetzt | `sensor.gc_plant_battery_energy` |
| **In die Batterie** | `charged_today` (Integration der Ladeleistung, nicht Netto-SoC) |
| **Aus der Batterie** | `discharged_today` |
| Zum WR | WR Input 1+2 wenn Suffix gesetzt, sonst Plant `energy_today` |
| Vom Balkon | Plant `energy_today` |
| **Eigenverbrauch** | (Balkon − Einspeisung) / Balkon |
| **Autarkie** | (Balkon − Einspeisung) / Gesamtbedarf |
| **Gesamtstrombedarf** | Netzbezug + Balkon − Einspeisung |
