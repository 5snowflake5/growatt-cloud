"""Growatt Open API (token) – v4 new-api. Noah und Nexa teilen deviceType=noah."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

LOG = logging.getLogger("growatt-cloud.api")

DEFAULT_SERVER = "https://openapi.growatt.com"

# Offizielle Limits (Showdoc / growatt-public-api):
# Noah/Nexa energy: 1/min · andere Geräte energy: 1/5min · Device-Liste: 1/5s
MIN_INTERVAL_NOAH_S = 60
MIN_INTERVAL_OTHER_S = 300
MIN_INTERVAL_LIST_S = 5


class GrowattApiError(RuntimeError):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class GrowattCloudApi:
    def __init__(self, token: str, server_url: str = DEFAULT_SERVER) -> None:
        self.token = (token or "").strip()
        self.server_url = (server_url or DEFAULT_SERVER).rstrip("/")
        if not self.token:
            raise ValueError("Growatt API-Token fehlt")
        self._last_list = 0.0
        self._last_energy: dict[str, float] = {}
        self._last_info: dict[str, float] = {}
        self._last_wifi: dict[str, float] = {}
        self._info_cache: dict[str, dict[str, Any]] = {}
        self._wifi_cache: dict[str, float] = {}
        # Account-Limits sind typ-weit, nicht pro Gerät (2× Noah = trotzdem max 1/min)
        self._last_noah_call = 0.0
        self._last_other_call = 0.0
        self._backoff_until = 0.0

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        # Session der Lib nutzt base .../v4 + endpoint; beides funktioniert.
        url = f"{self.server_url}/v4/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        body = None
        headers = {"token": self.token, "Accept": "application/json"}
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise GrowattApiError(f"HTTP {exc.code}: {raw[:300]}", code=exc.code) from exc
        except urllib.error.URLError as exc:
            raise GrowattApiError(f"Netzwerk: {exc.reason}") from exc

        if "<html" in raw.lower() and "login" in raw.lower():
            raise GrowattApiError("Growatt zeigt Login-Seite (Token ungültig oder Server falsch)")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GrowattApiError(f"Keine JSON-Antwort: {raw[:200]}") from exc

        code = payload.get("error_code")
        if code is None:
            code = payload.get("code")
        if code not in (None, 0, "0", ""):
            msg = payload.get("error_msg") or payload.get("message") or "API-Fehler"
            err = GrowattApiError(
                f"{msg} (code={code})",
                code=int(code) if str(code).lstrip("-").isdigit() else None,
            )
            if err.code in (102, 10012):
                self._backoff_until = time.monotonic() + 65.0
                LOG.warning("Rate-Limit – Pause 65 s")
            raise err
        return payload

    def _wait_type_slot(self, dtype: str) -> None:
        """Growatt limitiert Noah/Nexa und andere Geräte account-weit."""
        now = time.monotonic()
        if now < self._backoff_until:
            time.sleep(self._backoff_until - now)
            now = time.monotonic()
        if dtype == "noah":
            wait = MIN_INTERVAL_NOAH_S - (now - self._last_noah_call)
        else:
            wait = MIN_INTERVAL_OTHER_S - (now - self._last_other_call)
        if wait > 0:
            LOG.debug("API-Warte %.0fs (type=%s)", wait, dtype)
            time.sleep(wait)

    def _mark_type_slot(self, dtype: str) -> None:
        now = time.monotonic()
        if dtype == "noah":
            self._last_noah_call = now
        else:
            self._last_other_call = now

    def list_devices(self, page: int = 1) -> list[dict[str, Any]]:
        now = time.monotonic()
        wait = MIN_INTERVAL_LIST_S - (now - self._last_list)
        if wait > 0:
            time.sleep(wait)
        payload = self._request("POST", "new-api/queryDeviceList", params={"page": page})
        self._last_list = time.monotonic()
        data = payload.get("data") or {}
        rows = data.get("data") or []
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict)]

    def query_last_data(self, device_sn: str, device_type: str) -> dict[str, Any]:
        """Rohdaten von queryLastData. device_type z.B. noah | min | inv."""
        dtype = self._normalize_type(device_type)
        self._wait_type_slot(dtype)

        payload = self._request(
            "POST",
            "new-api/queryLastData",
            params={"deviceSn": device_sn, "deviceType": dtype},
        )
        self._mark_type_slot(dtype)
        self._last_energy[f"{dtype}:{device_sn}"] = time.monotonic()

        return self._unwrap_device_block(payload, dtype)

    @staticmethod
    def _normalize_type(device_type: str) -> str:
        dtype = (device_type or "").strip().lower()
        if dtype in ("nexa", "noah/nexa"):
            return "noah"
        if dtype in ("tlx", "inv"):
            return "min"
        return dtype

    def _unwrap_device_block(self, payload: dict[str, Any], dtype: str) -> dict[str, Any]:
        block = (payload.get("data") or {}).get(dtype)
        if isinstance(block, list) and block:
            return block[0] if isinstance(block[0], dict) else {}
        if isinstance(block, dict):
            return block
        data = payload.get("data") or {}
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
                if isinstance(value, dict):
                    return value
        return {}

    def query_device_info(self, device_sn: str, device_type: str, min_interval_s: float = 300.0) -> dict[str, Any]:
        """Geräte-Details (Firmware, Limits, Zeitfenster, …). Rate limit ~5 Min."""
        dtype = self._normalize_type(device_type)
        key = f"{dtype}:{device_sn}"
        now = time.monotonic()
        last = self._last_info.get(key, 0.0)
        if key in self._info_cache and (now - last) < min_interval_s:
            return self._info_cache[key]
        self._wait_type_slot(dtype)
        payload = self._request(
            "POST",
            "new-api/queryDeviceInfo",
            params={"deviceSn": device_sn, "deviceType": dtype},
        )
        self._mark_type_slot(dtype)
        self._last_info[key] = time.monotonic()
        info = self._unwrap_device_block(payload, dtype)
        self._info_cache[key] = info
        return info

    def wifi_strength(self, device_sn: str, device_type: str, min_interval_s: float = 300.0) -> float | None:
        """WLAN-Signal in dBm. Offizielles Limit 5 s; wir cachen länger mit den Details."""
        dtype = self._normalize_type(device_type)
        key = f"{dtype}:{device_sn}"
        now = time.monotonic()
        last = self._last_wifi.get(key, 0.0)
        if key in self._wifi_cache and (now - last) < min_interval_s:
            return self._wifi_cache[key]
        self._wait_type_slot(dtype)
        try:
            payload = self._request(
                "POST",
                "new-api/getWiFiSignalByDevice",
                params={"deviceSn": device_sn, "deviceType": dtype},
            )
        except GrowattApiError as exc:
            LOG.debug("WiFi %s: %s", device_sn, exc)
            return self._wifi_cache.get(key)
        self._mark_type_slot(dtype)
        self._last_wifi[key] = time.monotonic()
        # Erfolg: Signal oft in message, nicht in data
        raw = payload.get("message")
        if raw in (None, "", "SUCCESSFUL_OPERATION"):
            raw = payload.get("data")
        try:
            dbm = float(raw)
        except (TypeError, ValueError):
            return self._wifi_cache.get(key)
        self._wifi_cache[key] = dbm
        return dbm

