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
# Noah/Nexa energy (queryLastData): 1/min account-weit
# andere Geräte energy: 1/5min account-weit
# Device-Liste: 1/5s · DeviceInfo: ~5min · WiFi: ~5s
MIN_INTERVAL_NOAH_S = 60
MIN_INTERVAL_OTHER_S = 300
MIN_INTERVAL_LIST_S = 5
MIN_INTERVAL_AUX_S = 3  # höfliche Pause zwischen Info/WiFi


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
        # Nur queryLastData teilt sich den strengen Energy-Slot (Noah 60s / andere 300s)
        self._last_noah_energy = 0.0
        self._last_other_energy = 0.0
        self._last_aux = 0.0
        self._backoff_until = 0.0

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
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

    def _wait_backoff(self) -> None:
        now = time.monotonic()
        if now < self._backoff_until:
            time.sleep(self._backoff_until - now)

    def _wait_energy_slot(self, dtype: str) -> None:
        """Nur für queryLastData – Noah/Nexa teilen sich 1 Slot/Min."""
        self._wait_backoff()
        now = time.monotonic()
        if dtype == "noah":
            wait = MIN_INTERVAL_NOAH_S - (now - self._last_noah_energy)
        else:
            wait = MIN_INTERVAL_OTHER_S - (now - self._last_other_energy)
        if wait > 0:
            LOG.info("Energy-Slot warte %.0fs (type=%s, Fair-Share bei mehreren Geräten)", wait, dtype)
            time.sleep(wait)

    def _mark_energy_slot(self, dtype: str) -> None:
        now = time.monotonic()
        if dtype == "noah":
            self._last_noah_energy = now
        else:
            self._last_other_energy = now

    def _wait_aux_slot(self) -> None:
        """Kurze Pause für DeviceInfo/WiFi – verbraucht keinen Energy-Slot."""
        self._wait_backoff()
        now = time.monotonic()
        wait = MIN_INTERVAL_AUX_S - (now - self._last_aux)
        if wait > 0:
            time.sleep(wait)

    def _mark_aux_slot(self) -> None:
        self._last_aux = time.monotonic()

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
        """Live-Messwerte. device_type z.B. noah | min."""
        dtype = self._normalize_type(device_type)
        self._wait_energy_slot(dtype)
        payload = self._request(
            "POST",
            "new-api/queryLastData",
            params={"deviceSn": device_sn, "deviceType": dtype},
        )
        self._mark_energy_slot(dtype)
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
        """Details (Firmware, …). Cache ~5 Min – kein Energy-Slot."""
        dtype = self._normalize_type(device_type)
        key = f"{dtype}:{device_sn}"
        now = time.monotonic()
        last = self._last_info.get(key, 0.0)
        if key in self._info_cache and (now - last) < min_interval_s:
            return self._info_cache[key]
        self._wait_aux_slot()
        payload = self._request(
            "POST",
            "new-api/queryDeviceInfo",
            params={"deviceSn": device_sn, "deviceType": dtype},
        )
        self._mark_aux_slot()
        self._last_info[key] = time.monotonic()
        info = self._unwrap_device_block(payload, dtype)
        self._info_cache[key] = info
        return info

    def wifi_strength(self, device_sn: str, device_type: str, min_interval_s: float = 300.0) -> float | None:
        """WLAN dBm. Cache wie DeviceInfo – kein Energy-Slot."""
        dtype = self._normalize_type(device_type)
        key = f"{dtype}:{device_sn}"
        now = time.monotonic()
        last = self._last_wifi.get(key, 0.0)
        if key in self._wifi_cache and (now - last) < min_interval_s:
            return self._wifi_cache[key]
        self._wait_aux_slot()
        try:
            payload = self._request(
                "POST",
                "new-api/getWiFiSignalByDevice",
                params={"deviceSn": device_sn, "deviceType": dtype},
            )
        except GrowattApiError as exc:
            LOG.debug("WiFi %s: %s", device_sn, exc)
            return self._wifi_cache.get(key)
        self._mark_aux_slot()
        self._last_wifi[key] = time.monotonic()
        raw = payload.get("message")
        if raw in (None, "", "SUCCESSFUL_OPERATION"):
            raw = payload.get("data")
        try:
            dbm = float(raw)
        except (TypeError, ValueError):
            return self._wifi_cache.get(key)
        self._wifi_cache[key] = dbm
        return dbm
