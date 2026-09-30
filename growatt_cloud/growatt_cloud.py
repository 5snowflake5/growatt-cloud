#!/usr/bin/env python3
"""Growatt Cloud → MQTT für Home Assistant (Noah, Nexa, Wechselrichter)."""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from api import (
    GrowattApiError,
    GrowattCloudApi,
    MIN_INTERVAL_NOAH_S,
    MIN_INTERVAL_OTHER_S,
)
from ha_env import resolve_mqtt, resolve_timezone
from mqtt_ha import HaMqtt, slug
from sensors import apply_derived_values, ensure_storage_slots, is_reading_stale, merge_device_values

# VERSION = config.yaml version; nur Release-Workflow ändert beides
VERSION = "0.1.30"
OPTIONS_PATHS = ("/data/options.json", "options.json")
SOLAR_SPLIT_ENERGY_PATH = "/data/growatt_solar_split_energy.json"
_LEGACY_TOWER_ENERGY_PATH = "/data/growatt_tower_energy.json"
ENERGY_SAVE_INTERVAL_S = 300
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
                return json.load(fh)
    return {}


def env_or(opts: dict[str, Any], key: str, default: Any = "") -> Any:
    env_key = f"GROWATT_{key.upper()}"
    if env_key in os.environ and os.environ[env_key] != "":
        return os.environ[env_key]
    return opts.get(key, default)


def _poll_seconds(opts: dict[str, Any], key: str, default: int, recommended_min: int) -> int:
    """Supervisor allows 1–86400; we warn below Growatt's published minimum but do not clamp."""
    try:
        value = int(env_or(opts, key, default))
    except (TypeError, ValueError):
        value = default
    value = max(1, min(value, 86400))
    if value < recommended_min:
        LOG.warning(
            "%s=%ss is below Growatt's recommended minimum (%ss) – code 102 / lockout possible",
            key,
            value,
            recommended_min,
        )
    return value


class Bridge:
    def __init__(self, opts: dict[str, Any]) -> None:
        self.opts = opts
        self.stop = False
        token = str(env_or(opts, "api_token", "")).strip()
        server = str(env_or(opts, "server_url", "https://openapi.growatt.com")).strip()
        self.api = GrowattCloudApi(token=token, server_url=server)

        self.poll_storage_s = _poll_seconds(opts, "poll_storage_seconds", MIN_INTERVAL_NOAH_S, MIN_INTERVAL_NOAH_S)
        self.poll_inverter_s = _poll_seconds(
            opts, "poll_inverter_seconds", MIN_INTERVAL_OTHER_S, MIN_INTERVAL_OTHER_S
        )
        self.poll_devices_s = _poll_seconds(opts, "poll_devices_seconds", 3600, 300)
        self.sensor_mode = str(env_or(opts, "sensor_mode", "useful")).strip().lower() or "useful"
        if self.sensor_mode not in ("useful", "full"):
            LOG.warning("sensor_mode=%s ungültig – nutze useful", self.sensor_mode)
            self.sensor_mode = "useful"
        if self.sensor_mode == "full":
            LOG.warning(
                "sensor_mode=full → viele Entities. Für schlanke Sensoren in der App-Config "
                "sensor_mode auf 'useful' stellen."
            )

        try:
            self.pack_capacity_wh = float(env_or(opts, "pack_capacity_wh", 2048) or 0)
        except (TypeError, ValueError):
            self.pack_capacity_wh = 2048.0
        try:
            self.stale_after_hours = float(env_or(opts, "stale_after_hours", 24) or 24)
        except (TypeError, ValueError):
            self.stale_after_hours = 24.0
        self.stale_after_hours = max(1.0, min(self.stale_after_hours, 720.0))
        raw_skip = str(env_or(opts, "skip_serials", "") or "")
        self.skip_serials = {s.strip().lower() for s in re.split(r"[,\s;]+", raw_skip) if s.strip()}
        self.tz_name = resolve_timezone(str(env_or(opts, "timezone", "") or ""))
        try:
            self._tz = ZoneInfo(self.tz_name)
        except Exception:
            self._tz = ZoneInfo("UTC")
            self.tz_name = "UTC"

        mqtt_host, mqtt_port, mqtt_user, mqtt_password = resolve_mqtt(
            str(env_or(opts, "mqtt_host", "core-mosquitto")),
            int(env_or(opts, "mqtt_port", 1883) or 1883),
            str(env_or(opts, "mqtt_user", "") or ""),
            str(env_or(opts, "mqtt_password", "") or ""),
        )
        self.mqtt = HaMqtt(
            host=mqtt_host,
            port=mqtt_port,
            username=mqtt_user,
            password=mqtt_password,
            discovery_prefix=str(env_or(opts, "mqtt_discovery_prefix", "homeassistant")),
            state_prefix=str(env_or(opts, "mqtt_state_prefix", "growatt_cloud")),
            sensor_mode=self.sensor_mode,
        )

        self.devices: list[dict[str, Any]] = []
        self._last_devices = 0.0
        self._last_storage: dict[str, float] = {}
        self._last_inverter: dict[str, float] = {}
        self._pack_floor: dict[str, int] = {}
        self._energy_wh: dict[str, dict[str, float]] = {}
        self._last_energy_save = 0.0
        self._energy_dirty = False
        self._stale_known: dict[str, bool] = {}
        self._load_energy_state()

    def request_stop(self, *_args) -> None:
        self.stop = True

    def _local_now(self) -> datetime:
        return datetime.now(self._tz)

    def _local_day(self) -> str:
        return self._local_now().strftime("%Y-%m-%d")

    def _load_energy_state(self) -> None:
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
                            "charge": float(state.get("charge") or 0.0),
                            "discharge": float(state.get("discharge") or 0.0),
                            "ts": float(state.get("ts") or 0.0),
                        }
                    self._energy_wh = migrated
                    return
            except Exception as exc:
                LOG.debug("Energy-State laden (%s): %s", path, exc)
        self._energy_wh = {}

    def _save_energy_state(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and not self._energy_dirty:
            return
        if not force and (now - self._last_energy_save) < ENERGY_SAVE_INTERVAL_S:
            return
        try:
            os.makedirs(os.path.dirname(SOLAR_SPLIT_ENERGY_PATH), exist_ok=True)
            with open(SOLAR_SPLIT_ENERGY_PATH, "w", encoding="utf-8") as fh:
                json.dump(self._energy_wh, fh)
            self._last_energy_save = now
            self._energy_dirty = False
        except Exception as exc:
            LOG.debug("Energy-State speichern: %s", exc)

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

    def _accumulate_energy(self, sn: str, values: dict[str, Any], poll_s: int) -> None:
        """Tages-kWh aus Live-Leistung (PV-Split, Laden, Entladen)."""
        now = time.time()
        day = self._local_day()
        state = self._energy_wh.get(sn) or {
            "day": day,
            "strings": 0.0,
            "other": 0.0,
            "charge": 0.0,
            "discharge": 0.0,
            "ts": now,
        }
        if state.get("day") != day:
            state = {
                "day": day,
                "strings": 0.0,
                "other": 0.0,
                "charge": 0.0,
                "discharge": 0.0,
                "ts": now,
            }
        last = float(state.get("ts") or 0.0)
        max_dt_h = max(2 * poll_s, 30) / 3600.0
        dt_h = 0.0
        if last > 0:
            dt_h = max(0.0, min((now - last) / 3600.0, max_dt_h))
        strings_w = float(values.get("solar_power_storage1") or 0.0)
        other_w = float(values.get("solar_power_other_storage") or 0.0)
        charge_w = float(values.get("charging_power") or 0.0)
        discharge_w = float(values.get("discharge_power") or 0.0)
        if last and dt_h > 0:
            state["strings"] = float(state.get("strings") or 0.0) + strings_w * dt_h
            state["other"] = float(state.get("other") or 0.0) + other_w * dt_h
            state["charge"] = float(state.get("charge") or 0.0) + charge_w * dt_h
            state["discharge"] = float(state.get("discharge") or 0.0) + discharge_w * dt_h
        state["ts"] = now
        state["day"] = day
        self._energy_wh[sn] = state
        self._energy_dirty = True
        values["generation_today_storage1"] = round(float(state["strings"]) / 1000.0, 3)
        values["generation_today_other_storage"] = round(float(state["other"]) / 1000.0, 3)
        values["charged_today"] = round(float(state["charge"]) / 1000.0, 3)
        values["discharged_today"] = round(float(state["discharge"]) / 1000.0, 3)
        self._save_energy_state()

    def _is_skipped(self, sn: str) -> bool:
        key = (sn or "").strip().lower()
        if not key:
            return False
        return key in self.skip_serials or slug(sn) in self.skip_serials

    def _poll_interval(self, sn: str, live_s: int) -> int:
        if self._stale_known.get(sn):
            return max(live_s, self.poll_devices_s)
        return live_s

    def _mark_stale(self, sn: str, values: dict[str, Any], reason: str) -> None:
        already = bool(self._stale_known.get(sn))
        self._stale_known[sn] = True
        self.mqtt.set_available(sn, False)
        if already:
            return
        LOG.warning(
            "%s %s ist veraltet (%s, last_update=%s) – HA: unavailable, Poll nur noch stündlich",
            values.get("label") or "Gerät",
            sn,
            reason,
            values.get("last_update"),
        )

    def refresh_devices(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and self.devices and (now - self._last_devices) < self.poll_devices_s:
            return
        rows = self.api.list_devices()
        self.devices = rows
        self._last_devices = now
        for row in rows:
            sn = str(row.get("deviceSn") or row.get("device_sn") or "").strip()
            dtype = str(row.get("deviceType") or row.get("device_type") or "").strip().lower()
            LOG.info("Gerät: sn=%s type=%s", sn, dtype)
            if sn and self._is_skipped(sn):
                self.mqtt.set_available(sn, False)
                LOG.info("Überspringe %s (skip_serials)", sn)

    def storage_targets(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for row in self.devices:
            sn = str(row.get("deviceSn") or row.get("device_sn") or "").strip()
            dtype = str(row.get("deviceType") or row.get("device_type") or "").strip().lower()
            if sn and dtype in STORAGE_TYPES and not self._is_skipped(sn):
                out.append((sn, "noah"))
        return out

    def inverter_targets(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for row in self.devices:
            sn = str(row.get("deviceSn") or row.get("device_sn") or "").strip()
            dtype = str(row.get("deviceType") or row.get("device_type") or "").strip().lower()
            if sn and dtype in INVERTER_TYPES and not self._is_skipped(sn):
                api_type = "min" if dtype in ("min", "tlx", "inv") else dtype
                out.append((sn, api_type))
        return out

    def _enrich(self, sn: str, api_type: str, energy: dict[str, Any], kind: str) -> dict[str, Any]:
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
        values = merge_device_values(
            energy, info, kind=kind, wifi_dbm=wifi, serial=sn, mode=self.sensor_mode
        )
        apply_derived_values(
            values,
            kind=kind,
            tz_name=self.tz_name,
            pack_capacity_wh=self.pack_capacity_wh,
        )
        return values

    def poll_storage(self) -> None:
        now = time.monotonic()
        for sn, api_type in self.storage_targets():
            if now - self._last_storage.get(sn, 0.0) < self._poll_interval(sn, self.poll_storage_s):
                continue
            try:
                raw = self.api.query_last_data(sn, api_type)
                values = self._enrich(sn, api_type, raw, "storage")
                self._apply_sticky_packs(sn, values)
                apply_derived_values(
                    values,
                    kind="storage",
                    tz_name=self.tz_name,
                    pack_capacity_wh=self.pack_capacity_wh,
                )
                stale = is_reading_stale(
                    values, tz_name=self.tz_name, max_age_hours=self.stale_after_hours
                )
                self._last_storage[sn] = time.monotonic()
                if stale:
                    self.mqtt.ensure_discovery(sn, values["label"], values)
                    self._mark_stale(sn, values, f">{self.stale_after_hours:.0f}h")
                    continue
                self._stale_known[sn] = False
                self._accumulate_energy(sn, values, self.poll_storage_s)
                self.mqtt.ensure_discovery(sn, values["label"], values)
                self.mqtt.publish_states(sn, values)
                entity_n = len([k for k in values if k not in ("family", "label", "time", "device_name")])
                LOG.info(
                    "%s %s SoC=%s%% PV=%.0fW PV1-4=%.0fW Other=%.0fW "
                    "Out=%.0fW Today=%.2fkWh Charge=%.2f Discharge=%.2fkWh packs=%s mode=%s entities=%s tz=%s",
                    values["label"],
                    sn,
                    values.get("soc"),
                    values.get("solar_power") or 0,
                    values.get("solar_power_storage1") or 0,
                    values.get("solar_power_other_storage") or 0,
                    values.get("output_power") or 0,
                    values.get("generation_today") or 0,
                    values.get("charged_today") or 0,
                    values.get("discharged_today") or 0,
                    values.get("battery_num"),
                    self.sensor_mode,
                    entity_n,
                    self.tz_name,
                )
            except GrowattApiError as exc:
                LOG.error("Speicher %s: %s", sn, exc)
                if exc.code in (100, 102, 10012):
                    self._last_storage[sn] = time.monotonic()

    def poll_inverter(self) -> None:
        now = time.monotonic()
        for sn, api_type in self.inverter_targets():
            last = self._last_inverter.get(sn, 0.0)
            if now - last < self._poll_interval(sn, self.poll_inverter_s):
                continue
            try:
                raw = self.api.query_last_data(sn, api_type)
                values = self._enrich(sn, api_type, raw, "min")
                stale = is_reading_stale(
                    values, tz_name=self.tz_name, max_age_hours=self.stale_after_hours
                )
                self._last_inverter[sn] = time.monotonic()
                if stale:
                    self.mqtt.ensure_discovery(sn, values["label"], values)
                    self._mark_stale(sn, values, f">{self.stale_after_hours:.0f}h")
                    continue
                self._stale_known[sn] = False
                self.mqtt.ensure_discovery(sn, values["label"], values)
                self.mqtt.publish_states(sn, values)
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
        LOG.info(
            "growatt_cloud %s start (Geräte auto, sensor_mode=%s, tz=%s, pack_wh=%s, stale>%sh)",
            VERSION,
            self.sensor_mode,
            self.tz_name,
            self.pack_capacity_wh,
            self.stale_after_hours,
        )
        if self.skip_serials:
            LOG.info("skip_serials=%s", ",".join(sorted(self.skip_serials)))
        self.mqtt.connect()
        if not self.mqtt.wait_connected(5):
            LOG.warning("Starte Poll-Loop trotzdem – MQTT-Reconnect läuft im Hintergrund")
        self.mqtt.forget_plant()
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
        self._save_energy_state(force=True)
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
