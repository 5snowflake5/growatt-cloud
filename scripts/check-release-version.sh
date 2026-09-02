#!/usr/bin/env bash
# Version in config.yaml / growatt_cloud.py darf nur steigen via
# Commit: "Release x.y.z (image published first)."
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CONFIG="$ROOT/growatt_cloud/config.yaml"
PY="$ROOT/growatt_cloud/growatt_cloud.py"

cfg_ver=$(sed -n 's/^version: "\(.*\)"/\1/p' "$CONFIG" | head -1)
py_ver=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$PY" | head -1)

if [[ -z "$cfg_ver" || -z "$py_ver" ]]; then
  echo "Version in config.yaml oder growatt_cloud.py nicht gefunden."
  exit 1
fi

if [[ "$cfg_ver" != "$py_ver" ]]; then
  echo "Version mismatch: config.yaml=$cfg_ver growatt_cloud.py=$py_ver"
  exit 1
fi

# Nur bei Push-Event mit Vorgänger-Commit prüfen (CI)
if [[ "${GITHUB_EVENT_NAME:-}" == "push" && -n "${GITHUB_SHA:-}" ]]; then
  OLD_CFG=$(git show HEAD~1:growatt_cloud/config.yaml 2>/dev/null | sed -n 's/^version: "\(.*\)"/\1/p' || true)
  MSG=$(git log -1 --format=%s)

  if [[ -n "$OLD_CFG" && "$OLD_CFG" != "$cfg_ver" ]]; then
    if [[ "$MSG" =~ ^Release\ .*\ \(image\ published\ first\)\.$ ]]; then
      echo "Release-Commit OK: $OLD_CFG → $cfg_ver"
      exit 0
    fi
    higher=$(printf '%s\n' "$OLD_CFG" "$cfg_ver" | sort -V | tail -1)
    if [[ "$higher" == "$cfg_ver" && "$cfg_ver" != "$OLD_CFG" ]]; then
      echo "FEHLER: Version $OLD_CFG → $cfg_ver ohne Release-Workflow-Commit."
      echo "Siehe RELEASE.md – Feature-Commits dürfen version nicht erhöhen."
      exit 1
    fi
  fi
fi

echo "Version OK: $cfg_ver"
