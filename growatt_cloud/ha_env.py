"""Home Assistant Supervisor: MQTT credentials and timezone."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

LOG = logging.getLogger("growatt-cloud.ha")

SUPERVISOR_BASE = "http://supervisor"


def _supervisor_token() -> str:
    return str(os.environ.get("SUPERVISOR_TOKEN") or "").strip()


def _supervisor_get(path: str, timeout: float = 5.0) -> dict[str, Any] | None:
    token = _supervisor_token()
    if not token:
        return None
    url = f"{SUPERVISOR_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        LOG.debug("Supervisor %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def supervisor_mqtt() -> dict[str, Any]:
    """MQTT host/user/password from the Supervisor MQTT service."""
    data = _supervisor_get("/services/mqtt")
    if not data:
        return {}
    out: dict[str, Any] = {}
    for src, dest in (
        ("host", "host"),
        ("port", "port"),
        ("username", "username"),
        ("password", "password"),
    ):
        if data.get(src) not in (None, ""):
            out[dest] = data[src]
    return out


def supervisor_timezone() -> str | None:
    """IANA timezone from Home Assistant core config."""
    data = _supervisor_get("/core/api/config")
    if not data:
        return None
    tz = data.get("time_zone") or data.get("timeZone")
    text = str(tz or "").strip()
    return text or None


def resolve_timezone(configured: str) -> str:
    """Add-on option first, then Home Assistant, then UTC.

    Growatt's `timezone` field is usually an offset or internal id, not IANA,
    so it is not used as the clock for day boundaries.
    """
    text = (configured or "").strip()
    if text:
        if _zoneinfo_ok(text):
            return text
        LOG.warning("timezone=%s is not a valid IANA zone – trying Home Assistant", text)
    ha_tz = supervisor_timezone()
    if ha_tz and _zoneinfo_ok(ha_tz):
        LOG.info("Zeitzone von Home Assistant: %s", ha_tz)
        return ha_tz
    LOG.info("Zeitzone: UTC (HA-Config nicht erreichbar, Option leer)")
    return "UTC"


def _zoneinfo_ok(name: str) -> bool:
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(name)
        return True
    except Exception:
        return False


def resolve_mqtt(
    host: str,
    port: int,
    username: str,
    password: str,
) -> tuple[str, int, str, str]:
    """Fill blank MQTT settings from Supervisor when the add-on uses mqtt:need."""
    host = (host or "").strip()
    username = (username or "").strip()
    password = password or ""
    port = int(port or 0)

    needs_auto = (not host or host == "core-mosquitto") and not username
    if not needs_auto and host and username:
        return host, (port or 1883), username, password

    auto = supervisor_mqtt()
    if auto:
        host = host or str(auto.get("host") or "core-mosquitto")
        if not port:
            try:
                port = int(auto.get("port") or 1883)
            except (TypeError, ValueError):
                port = 1883
        if not username:
            username = str(auto.get("username") or "")
        if not password:
            password = str(auto.get("password") or "")
        LOG.info("MQTT-Zugangsdaten vom Supervisor (%s:%s)", host, port or 1883)
    return host or "core-mosquitto", port or 1883, username, password
