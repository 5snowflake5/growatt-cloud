# Growatt Cloud

Home-Assistant-App: **Noah / Nexa + MIN-Wechselrichter** über Growatt **Open API v4** (ein Token) → MQTT.

Ersatz für die Combo `noah-mqtt` + Growatt-Server-Integration (Doppel-Login, Account-Sperren).

## Installation

1. Einstellungen → Apps → ⋮ → Repositories  
2. `https://github.com/5snowflake5/growatt-cloud`  
3. App **Growatt Cloud** installieren  

Images kommen von GHCR (kein Build auf dem Pi).

## Releases (wichtig)

Home Assistant liest die Version aus `config.yaml` im Git-Repo. Damit kein Update erscheint, bevor das Image da ist:

1. Code nach `master` pushen → baut nur Preview-Tags `edge` / `sha-…`  
2. **GitHub → Actions → „Release add-on“ → Run workflow** mit Version z. B. `0.1.24`  
3. Workflow: Image pushen → **erst danach** Versionsbump committen  
4. Dann in HA updaten

Nicht die Versionsnummer in `config.yaml` von Hand hochsetzen und pushen – sonst wieder Race.

## Kurz

- Token von [openapi.growatt.com](https://openapi.growatt.com) (Account → API Token)
- Noah **und** Nexa (`deviceType=noah` in v4; v1 kennt beides nicht)
- Optional MIN-WR (Energy Today / Input 1+2)
- Poll-Limits respektieren (≥60 s Speicher, ≥300 s WR)

Details: [growatt_cloud/DOCS.md](growatt_cloud/DOCS.md) · Changelog: [growatt_cloud/CHANGELOG.md](growatt_cloud/CHANGELOG.md)
