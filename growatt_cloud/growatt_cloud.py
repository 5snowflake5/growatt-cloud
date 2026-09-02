#!/usr/bin/env python3
"""Growatt Cloud → MQTT für Home Assistant.

Ein Login (API-Token), Open API v4:
  - Noah und Nexa (deviceType=noah, Auto-Erkennung)
  - MIN-Wechselrichter (Auto aus Geräteliste)

Keine manuellen Serials nötig.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from typing import Any

from api import (
    GrowattApiError,
    GrowattCloudApi,
    MIN_INTERVAL_NOAH_S,
    MIN_INTERVAL_OTHER_S,
)
from mqtt_ha import HaMqtt
from sensors import ensure_storage_slots, merge_device_values

# VERBINDLICH: muss config.yaml version entsprechen – nur Release-Workflow ändert beides.
VERSION = "0.1.27"
OPTIONS_PATHS = ("/data/options.json", "options.json")
SOLAR_SPLIT_ENERGY_PATH = "/data/growatt_solar_split_energy.json"
# Legacy-Pfad (Migration)
_LEGACY_TOWER_ENERGY_PATH = "/data/growatt_tower_energy.json"
LOG = logging.getLogger("growatt-cloud")

STORAGE_TYPES = {"noah", "nexa"}
INVERTER_TYPES = {"min", "inv", "tlx"}
INFO_INTERVAL_S = 300  # queryDeviceInfo / WiFi – offizielles Details-Limit


def setup_logging(level_name: str = "info") -> None:
    level = logging.DEBUG if str(level_name).lower() == "debug" else logging.INFO
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)


def load_options() -> dict[str, Any]:
    for path in OPTIONS_PATHS:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                import json

                return json.load(fh)
    return {}


def env_or(opts: dict[str, Any], key: str, default: Any = "") -> Any:
    env_key = f"GROWATT_{key.upper()}"
    if env_key in os.environ and os.environ[env_key] != "":
        return os.environ[env_key]
    return opts.get(key, default)


class Bridge:
    def __init__(self, opts: dict[str, Any]) -> None:
        self.opts = opts
        self.stop = False
        token = str(env_or(opts, "api_token", "")).strip()
        server = str(env_or(opts, "server_url", "https://openapi.growatt.com")).strip()
        self.api = GrowattCloudApi(token=token, server_url=server)

        self.poll_storage_s = max(
            MIN_INTERVAL_NOAH_S,
            int(env_or(opts, "poll_storage_seconds", MIN_INTERVAL_NOAH_S)),
        )
        self.poll_inverter_s = max(
            MIN_INTERVAL_OTHER_S,
            int(env_or(opts, "poll_inverter_seconds", MIN_INTERVAL_OTHER_S)),
        )
        self.poll_devices_s = max(300, int(env_or(opts, "poll_devices_seconds", 3600)))
        self.sensor_mode = str(env_or(opts, "sensor_mode", "useful")).strip().lower() or "useful"
        if self.sensor_mode not in ("useful", "full"):
            LOG.warning("sensor_mode=%s ungültig – nutze useful", self.sensor_mode)
            self.sensor_mode = "useful"
        if self.sensor_mode == "full":
            LOG.warning(
                "sensor_mode=full → viele Entities. Für schlanke Sensoren in der App-Config "
                "sensor_mode auf 'useful' stellen."
            )

        self.mqtt = HaMqtt(
            host=str(env_or(opts, "mqtt_host", "core-mosquitto")),
            port=int(env_or(opts, "mqtt_port", 1883)),
            username=str(env_or(opts, "mqtt_user", "")),
            password=str(env_or(opts, "mqtt_password", "")),
            discovery_prefix=str(env_or(opts, "mqtt_discovery_prefix", "homeassistant")),
            state_prefix=str(env_or(opts, "mqtt_state_prefix", "growatt_cloud")),
            sensor_mode=self.sensor_mode,
        )

        self.devices: list[dict[str, Any]] = []
        self._last_devices = 0.0
        self._last_storage: dict[str, float] = {}
        self._last_inverter: dict[str, float] = {}
        self._pack_floor: dict[str, int] = {}  # SN → max gesehene Packs (nie runter)
        self._solar_split_wh: dict[str, dict[str, float]] = {}  # SN → {day, strings, other, ts}
        self._load_solar_split_energy()

    def request_stop(self, *_args) -> None:
        self.stop = True

    def _load_solar_split_energy(self) -> None:
        import json

        for path in (SOLAR_SPLIT_ENERGY_PATH, _LEGACY_TOWER_ENERGY_PATH):
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    raw = json.load(fh)
                if isinstance(raw, dict):
                    migrated: dict[str, dict[str, float]] = {}
                    for sn, state in raw.items():
                        if not isinstance(state, dict):
                            continue
                        migrated[sn] = {
                            "day": state.get("day"),
                            "strings": float(state.get("strings") or state.get("t1") or 0.0),
                            "other": float(state.get("other") or state.get("t2") or 0.0),
                            "ts": float(state.get("ts") or 0.0),
                        }
                    self._solar_split_wh = migrated
                    return
            except Exception as exc:
                LOG.debug("Solar-Split laden (%s): %s", path, exc)
        self._solar_split_wh = {}

    def _save_solar_split_energy(self) -> None:
        try:
            os.makedirs(os.path.dirname(SOLAR_SPLIT_ENERGY_PATH), exist_ok=True)
            import json

            with open(SOLAR_SPLIT_ENERGY_PATH, "w", encoding="utf-8") as fh:
                json.dump(self._solar_split_wh, fh)
        except Exception as exc:
            LOG.debug("Solar-Split speichern: %s", exc)

    def _apply_sticky_packs(self, sn: str, values: dict[str, Any]) -> None:
        packs = int(values.get("battery_num") or 1)
        packs = max(1, min(packs, 4))
        floor = max(packs, self._pack_floor.get(sn, 1))
        self._pack_floor[sn] = floor
        values["battery_num"] = packs
        ensure_storage_slots(values)
        if floor > packs:
            for i in range(packs + 1, floor + 1):
                values.setdefault(f"battery{i}_soc", 0.0)
                values.setdefault(f"battery{i}_temp", 0.0)

    def _accumulate_solar_split_energy(self, sn: str, values: dict[str, Any]) -> None:
        """Tages-kWh für PV1–4 (Master) und Other Storage aus Live-Leistung integrieren."""
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        state = self._solar_split_wh.get(sn) or {"day": day, "strings": 0.0, "other": 0.0, "ts": now}
        if state.get("day") != day:
            state = {"day": day, "strings": 0.0, "other": 0.0, "ts": now}
        last = float(state.get("ts") or now)
        dt_h = max(0.0, min((now - last) / 3600.0, 2.0))
        strings_w = float(values.get("solar_power_storage1") or 0.0)
        other_w = float(values.get("solar_power_other_storage") or 0.0)
        if last and dt_h > 0:
            state["strings"] = float(state.get("strings") or 0.0) + strings_w * dt_h
            state["other"] = float(state.get("other") or 0.0) + other_w * dt_h
        state["ts"] = now
        state["day"] = day
        self._solar_split_wh[sn] = state
        values["generation_today_storage1"] = round(float(state["strings"]) / 1000.0, 3)
        values["generation_today_other_storage"] = round(float(state["other"]) / 1000.0, 3)
        self._save_solar_split_energy()

    def refresh_devices(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and self.devices and (now - self._last_devices) < self.poll_devices_s:
            return
        rows = self.api.list_devices()
        self.devices = rows
        self._last_devices = now
        for row in rows:
            LOG.info(
                "Gerät: sn=%s type=%s",
                row.get("deviceSn") or row.get("device_sn"),
                row.get("deviceType") or row.get("device_type"),
            )

    def storage_targets(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for row in self.devices:
            sn = str(row.get("deviceSn") or row.get("device_sn") or "").strip()
            dtype = str(row.get("deviceType") or row.get("device_type") or "").strip().lower()
            if sn and dtype in STORAGE_TYPES:
                out.append((sn, "noah"))
        return out

    def inverter_targets(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for row in self.devices:
            sn = str(row.get("deviceSn") or row.get("device_sn") or "").strip()
            dtype = str(row.get("deviceType") or row.get("device_type") or "").strip().lower()
            if sn and dtype in INVERTER_TYPES:
                api_type = "min" if dtype in ("min", "tlx", "inv") else dtype
                out.append((sn, api_type))
        return out

    def _enrich(self, sn: str, api_type: str, energy: dict[str, Any], kind: str) -> dict[str, Any]:
        """Info/WiFi nur aus Cache oder selten – blockieren nicht den Energy-Slot."""
        info: dict[str, Any] = {}
        wifi: float | None = None
        try:
            info = self.api.query_device_info(sn, api_type, min_interval_s=INFO_INTERVAL_S) or {}
        except GrowattApiError as exc:
            LOG.warning("DeviceInfo %s: %s", sn, exc)
        try:
            wifi = self.api.wifi_strength(sn, api_type, min_interval_s=INFO_INTERVAL_S)
        except GrowattApiError as exc:
            LOG.debug("WiFi %s: %s", sn, exc)
        return merge_device_values(
            energy, info, kind=kind, wifi_dbm=wifi, serial=sn, mode=self.sensor_mode
        )

    def poll_storage(self) -> None:
        """Alle fälligen Noah/Nexa pollen (Limit ist pro SN, nicht global)."""
        now = time.monotonic()
        for sn, api_type in self.storage_targets():
            if now - self._last_storage.get(sn, 0.0) < self.poll_storage_s:
                continue
            try:
                raw = self.api.query_last_data(sn, api_type)
                values = self._enrich(sn, api_type, raw, "storage")
                self._apply_sticky_packs(sn, values)
                self._accumulate_solar_split_energy(sn, values)
                self.mqtt.ensure_discovery(sn, values["label"], values)
                self.mqtt.publish_states(sn, values)
                self._last_storage[sn] = time.monotonic()
                entity_n = len([k for k in values if k not in ("family", "label", "time", "device_name")])
                LOG.info(
                    "%s %s SoC=%s%% PV=%.0fW PV1-4=%.0fW Other=%.0fW "
                    "Out=%.0fW Today=%.2fkWh PV1-4=%.2f Other=%.2fkWh packs=%s bat2=%s%% mode=%s entities=%s",
                    values["label"],
                    sn,
                    values.get("soc"),
                    values.get("solar_power") or 0,
                    values.get("solar_power_storage1") or 0,
                    values.get("solar_power_other_storage") or 0,
                    values.get("output_power") or 0,
                    values.get("generation_today") or 0,
                    values.get("generation_today_storage1") or 0,
                    values.get("generation_today_other_storage") or 0,
                    values.get("battery_num"),
                    values.get("battery2_soc"),
                    self.sensor_mode,
                    entity_n,
                )
            except GrowattApiError as exc:
                LOG.error("Speicher %s: %s", sn, exc)
                if exc.code in (100, 102, 10012):
                    self._last_storage[sn] = time.monotonic()

    def poll_inverter(self) -> None:
        now = time.monotonic()
        for sn, api_type in self.inverter_targets():
            last = self._last_inverter.get(sn, 0.0)
            if now - last < self.poll_inverter_s:
                continue
            try:
                raw = self.api.query_last_data(sn, api_type)
                values = self._enrich(sn, api_type, raw, "min")
                self.mqtt.ensure_discovery(sn, values["label"], values)
                self.mqtt.publish_states(sn, values)
                self._last_inverter[sn] = time.monotonic()
                entity_n = len([k for k in values if k not in ("family", "label", "time", "device_name")])
                LOG.info(
                    "WR %s AC=%.0fW Today=%.2fkWh In1=%.2f In2=%.2f mode=%s entities=%s",
                    sn,
                    values.get("ac_power") or 0,
                    values.get("energy_today") or 0,
                    values.get("energy_today_input_1") or 0,
                    values.get("energy_today_input_2") or 0,
                    self.sensor_mode,
                    entity_n,
                )
            except GrowattApiError as exc:
                LOG.error("WR %s: %s", sn, exc)
                if exc.code in (100, 102, 10012):
                    self._last_inverter[sn] = time.monotonic()

    def run(self) -> None:
        LOG.info("growatt_cloud %s start (Geräte auto, sensor_mode=%s)", VERSION, self.sensor_mode)
        self.mqtt.connect()
        if not self.mqtt.wait_connected(5):
            LOG.warning("Starte Poll-Loop trotzdem – MQTT-Reconnect läuft im Hintergrund")
        while not self.stop:
            try:
                self.refresh_devices(force=not self.devices)
                targets_s = self.storage_targets()
                targets_i = self.inverter_targets()
                if not targets_s and not targets_i:
                    LOG.warning("Keine Noah/Nexa/MIN-Geräte in der Geräteliste – Token/Plant prüfen")
                else:
                    LOG.debug("Ziele Speicher=%s WR=%s", targets_s, targets_i)
                self.poll_storage()
                self.poll_inverter()
            except GrowattApiError as exc:
                LOG.error("API: %s", exc)
            except Exception:
                LOG.exception("Unerwarteter Fehler")
            for _ in range(10):
                if self.stop:
                    break
                time.sleep(1)
        self.mqtt.stop()
        LOG.info("stopped")


def main() -> None:
    opts = load_options()
    setup_logging(str(opts.get("log_level") or "info"))
    if not str(opts.get("api_token") or os.environ.get("GROWATT_API_TOKEN") or "").strip():
        LOG.error("api_token fehlt – in der App-Config den Growatt Open-API-Token eintragen")
        sys.exit(1)
    bridge = Bridge(opts)
    signal.signal(signal.SIGTERM, bridge.request_stop)
    signal.signal(signal.SIGINT, bridge.request_stop)
    bridge.run()


if __name__ == "__main__":
    main()
