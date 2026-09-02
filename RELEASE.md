# Release-Prozess (verbindlich)

Home Assistant liest `growatt_cloud/config.yaml` → `version`. Erscheint die Version im Git-Repo **bevor** das Docker-Image auf GHCR existiert, schlägt das Update in HA fehl.

## Regel (nicht verhandelbar)

1. **Feature-Commits:** `version` in `config.yaml` und `VERSION` in `growatt_cloud.py` **nicht ändern**.
2. **Changelog:** Eintrag unter `growatt_cloud/CHANGELOG.md` schreiben (ohne Versionsbump).
3. **Push** nach `master` → baut nur `edge` / `sha-…` Images.
4. **Actions → „Release add-on“** mit neuer Version `x.y.z` starten.
5. Workflow: Image nach GHCR → Commit `Release x.y.z (image published first).` → erst **dann** in HA updaten.

## Verboten

- `version` / `VERSION` im Feature-Commit erhöhen
- Release-Workflow überspringen und Version von Hand committen
- `release-addon.yml` oder `version-guard.yml` abschwächen, um den Prozess zu umgehen

## Erzwingung

- CI: `.github/workflows/version-guard.yml` blockiert Version-Upgrades ohne Release-Commit
- Skript: `scripts/check-release-version.sh` (lokal und in CI)
- Cursor: `.cursor/rules/release-version.mdc`

## Einmalig: GHCR-Images public

Home Assistant kann **keine privaten** GHCR-Images pullen. GitHub bietet dafür **keine** API – einmal pro Architektur in der Web-UI:

1. [growatt-cloud/amd64 → Package settings](https://github.com/users/5snowflake5/packages/container/growatt-cloud%2Famd64/settings) → Danger Zone → **Change visibility** → **Public**
2. [growatt-cloud/aarch64 → Package settings](https://github.com/users/5snowflake5/packages/container/growatt-cloud%2Faarch64/settings) → **Public**

Neue Version-Tags nutzen dieselbe Sichtbarkeit – nicht bei jedem Release wiederholen.

Der Release-Workflow warnt, falls der anonyme Pull noch fehlschlägt (HTTP ≠ 200).

## HA-Update (Reihenfolge)

1. GHCR public (siehe oben), falls Update bisher mit Pull-Fehler scheitert
2. Warten bis Release-Workflow grün
3. Einstellungen → Apps → Repository aktualisieren
4. Growatt Cloud → Aktualisieren
