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

## HA-Update (Reihenfolge)

1. Warten bis Release-Workflow grün
2. Einstellungen → Apps → Repository aktualisieren
3. Growatt Cloud → Aktualisieren
