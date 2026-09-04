# Home Assistant – Growatt / NOAH

## Einrichtung kurz

1. `noah_bilanz_package.yaml` nach `/config/packages/`  
2. `packages: !include_dir_named packages` in `configuration.yaml`  
3. `input_number.noah_s0_wh` um **00:00** auf `SoC% × 4096` setzen  
4. `noah_board_lovelace.yaml` ins Dashboard pasten  

### Volle Last + EcoTracker-Mehrbedarf

`speicher_vollast_defizit.yaml` → packages: zählt **Minuten/Tag**, wenn Speicher ≥ Schwelle abgibt und EcoTracker trotzdem noch Bezug zeigt (`0–250` / `250–500` / `500–800` / `≥800` W).

Schwelle: `input_number.speicher_voll_last_w` (z. B. 750 bei einem Noah ~800 W).  

## Rechnung (aus SoC jetzt + SoC₀)

| Größe | Formel |
|-------|--------|
| Speicher jetzt | SoC% × 4096 Wh |
| **In die Batterie** | max(0, jetzt − SoC₀) |
| **Aus der Batterie** | max(0, SoC₀ − jetzt) |
| Verlust Batterie | (SoC₀ + Solar − Zum WR) − jetzt |
| Zum WR | Input 1 + Input 2 |
| Vom Balkon | energy_today |
| Verlust WR | Zum WR − Vom Balkon |
| **Gesamtstrombedarf** | Netzbezug + Vom Balkon − Einspeisung |
