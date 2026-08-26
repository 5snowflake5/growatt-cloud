"""Home Assistant MQTT Discovery + State Publish."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any

LOG = logging.getLogger("growatt-cloud.mqtt")

# object_id → (name, unit|None, device_class|None, state_class|None, component)
# component: sensor | binary_sensor
SENSOR_META: dict[str, tuple[str, str | None, str | None, str | None, str]] = {
    "soc": ("SoC", "%", "battery", "measurement", "sensor"),
    "solar_power": ("Solar Power", "W", "power", "measurement", "sensor"),
    "output_power": ("Output Power", "W", "power", "measurement", "sensor"),
    "charging_power": ("Charging Power", "W", "power", "measurement", "sensor"),
    "discharge_power": ("Discharge Power", "W", "power", "measurement", "sensor"),
    "generation_today": ("Generation Today", "kWh", "energy", "total_increasing", "sensor"),
    "generation_total": ("Generation Total", "kWh", "energy", "total_increasing", "sensor"),
    "generation_month": ("Generation Month", "kWh", "energy", "total_increasing", "sensor"),
    "generation_year": ("Generation Year", "kWh", "energy", "total_increasing", "sensor"),
    "battery_num": ("Number Of Batteries", None, None, "measurement", "sensor"),
    "system_temp": ("System Temperature", "°C", "temperature", "measurement", "sensor"),
    "ct_power": ("CT Power", "W", "power", "measurement", "sensor"),
    "household_load": ("Household Load", "W", "power", "measurement", "sensor"),
    "on_grid_power": ("On Grid Power", "W", "power", "measurement", "sensor"),
    "off_grid_power": ("Off Grid Power", "W", "power", "measurement", "sensor"),
    "charge_soc_limit": ("Charging Limit", "%", "battery", "measurement", "sensor"),
    "discharge_soc_limit": ("Discharge Limit", "%", "battery", "measurement", "sensor"),
    "battery_soh": ("Battery SOH", "%", "battery", "measurement", "sensor"),
    "battery_cycles": ("Battery Cycles", None, None, "total_increasing", "sensor"),
    "work_mode": ("Work Mode", None, None, None, "sensor"),
    "work_mode_code": ("Work Mode Code", None, None, "measurement", "sensor"),
    "charge_status": ("Charge Status", None, None, None, "sensor"),
    "status_code": ("Status Code", None, None, "measurement", "sensor"),
    "heating": ("Heating", None, None, None, "binary_sensor"),
    "connectivity": ("Connectivity", None, "connectivity", None, "binary_sensor"),
    "wifi_signal": ("WiFi Signal", "dBm", "signal_strength", "measurement", "sensor"),
    "last_update": ("Last Update", None, "timestamp", None, "sensor"),
    "battery1_soc": ("Battery 1 SoC", "%", "battery", "measurement", "sensor"),
    "battery1_temp": ("Battery 1 Temperature", "°C", "temperature", "measurement", "sensor"),
    "battery2_soc": ("Battery 2 SoC", "%", "battery", "measurement", "sensor"),
    "battery2_temp": ("Battery 2 Temperature", "°C", "temperature", "measurement", "sensor"),
    "battery3_soc": ("Battery 3 SoC", "%", "battery", "measurement", "sensor"),
    "battery3_temp": ("Battery 3 Temperature", "°C", "temperature", "measurement", "sensor"),
    "battery4_soc": ("Battery 4 SoC", "%", "battery", "measurement", "sensor"),
    "battery4_temp": ("Battery 4 Temperature", "°C", "temperature", "measurement", "sensor"),
    "pv1_power": ("PV1 Power", "W", "power", "measurement", "sensor"),
    "pv1_voltage": ("PV1 Voltage", "V", "voltage", "measurement", "sensor"),
    "pv1_current": ("PV1 Current", "A", "current", "measurement", "sensor"),
    "pv2_power": ("PV2 Power", "W", "power", "measurement", "sensor"),
    "pv2_voltage": ("PV2 Voltage", "V", "voltage", "measurement", "sensor"),
    "pv2_current": ("PV2 Current", "A", "current", "measurement", "sensor"),
    "pv3_power": ("PV3 Power", "W", "power", "measurement", "sensor"),
    "pv3_voltage": ("PV3 Voltage", "V", "voltage", "measurement", "sensor"),
    "pv3_current": ("PV3 Current", "A", "current", "measurement", "sensor"),
    "pv4_power": ("PV4 Power", "W", "power", "measurement", "sensor"),
    "pv4_voltage": ("PV4 Voltage", "V", "voltage", "measurement", "sensor"),
    "pv4_current": ("PV4 Current", "A", "current", "measurement", "sensor"),
    "ac_power": ("AC Power", "W", "power", "measurement", "sensor"),
    "ac_power_r": ("AC Power R", "W", "power", "measurement", "sensor"),
    "ac_power_s": ("AC Power S", "W", "power", "measurement", "sensor"),
    "ac_power_t": ("AC Power T", "W", "power", "measurement", "sensor"),
    "energy_today": ("Energy Today", "kWh", "energy", "total_increasing", "sensor"),
    "energy_total": ("Energy Total", "kWh", "energy", "total_increasing", "sensor"),
    "energy_today_input_1": ("Energy Today Input 1", "kWh", "energy", "total_increasing", "sensor"),
    "energy_today_input_2": ("Energy Today Input 2", "kWh", "energy", "total_increasing", "sensor"),
    "energy_today_input_3": ("Energy Today Input 3", "kWh", "energy", "total_increasing", "sensor"),
    "energy_today_input_4": ("Energy Today Input 4", "kWh", "energy", "total_increasing", "sensor"),
    "energy_total_input_1": ("Energy Total Input 1", "kWh", "energy", "total_increasing", "sensor"),
    "energy_total_input_2": ("Energy Total Input 2", "kWh", "energy", "total_increasing", "sensor"),
    "energy_total_input_3": ("Energy Total Input 3", "kWh", "energy", "total_increasing", "sensor"),
    "energy_total_input_4": ("Energy Total Input 4", "kWh", "energy", "total_increasing", "sensor"),
    "energy_total_pv": ("Energy Total PV", "kWh", "energy", "total_increasing", "sensor"),
    "ppv": ("PV Power", "W", "power", "measurement", "sensor"),
    "ppv1": ("PV Power Input 1", "W", "power", "measurement", "sensor"),
    "ppv2": ("PV Power Input 2", "W", "power", "measurement", "sensor"),
    "ppv3": ("PV Power Input 3", "W", "power", "measurement", "sensor"),
    "ppv4": ("PV Power Input 4", "W", "power", "measurement", "sensor"),
    "ipv1": ("PV Current Input 1", "A", "current", "measurement", "sensor"),
    "ipv2": ("PV Current Input 2", "A", "current", "measurement", "sensor"),
    "ipv3": ("PV Current Input 3", "A", "current", "measurement", "sensor"),
    "ipv4": ("PV Current Input 4", "A", "current", "measurement", "sensor"),
    "vpv1": ("PV Voltage Input 1", "V", "voltage", "measurement", "sensor"),
    "vpv2": ("PV Voltage Input 2", "V", "voltage", "measurement", "sensor"),
    "vpv3": ("PV Voltage Input 3", "V", "voltage", "measurement", "sensor"),
    "vpv4": ("PV Voltage Input 4", "V", "voltage", "measurement", "sensor"),
    "vac1": ("Grid Voltage R", "V", "voltage", "measurement", "sensor"),
    "vac2": ("Grid Voltage S", "V", "voltage", "measurement", "sensor"),
    "vac3": ("Grid Voltage T", "V", "voltage", "measurement", "sensor"),
    "iac1": ("Grid Current R", "A", "current", "measurement", "sensor"),
    "iac2": ("Grid Current S", "A", "current", "measurement", "sensor"),
    "iac3": ("Grid Current T", "A", "current", "measurement", "sensor"),
    "fac": ("Grid Frequency", "Hz", "frequency", "measurement", "sensor"),
    "temperature": ("Temperature", "°C", "temperature", "measurement", "sensor"),
    "temperature_2": ("Temperature 2", "°C", "temperature", "measurement", "sensor"),
    "temperature_3": ("Temperature 3", "°C", "temperature", "measurement", "sensor"),
    "temperature_4": ("Temperature 4", "°C", "temperature", "measurement", "sensor"),
    "temperature_5": ("Temperature 5", "°C", "temperature", "measurement", "sensor"),
    "pf": ("Power Factor", None, "power_factor", "measurement", "sensor"),
    "export_power": ("Export Power", "W", "power", "measurement", "sensor"),
    "import_power": ("Import Power", "W", "power", "measurement", "sensor"),
    "local_load_power": ("Local Load Power", "W", "power", "measurement", "sensor"),
    "energy_to_grid_today": ("Energy To Grid Today", "kWh", "energy", "total_increasing", "sensor"),
    "energy_to_grid_total": ("Energy To Grid Total", "kWh", "energy", "total_increasing", "sensor"),
    "energy_to_user_today": ("Energy From Grid Today", "kWh", "energy", "total_increasing", "sensor"),
    "energy_to_user_total": ("Energy From Grid Total", "kWh", "energy", "total_increasing", "sensor"),
    "energy_local_load_today": ("Local Load Today", "kWh", "energy", "total_increasing", "sensor"),
    "energy_local_load_total": ("Local Load Total", "kWh", "energy", "total_increasing", "sensor"),
    "status": ("Status", None, None, None, "sensor"),
}

_META_SKIP = {"family", "label", "time", "device_name"}



def slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", (value or "").strip().lower())
    return text.strip("_") or "device"


def infer_meta(object_id: str) -> tuple[str, str | None, str | None, str | None, str]:
    """HA-Meta für bekannte Keys oder Heuristik aus dem Feldnamen."""
    if object_id in SENSOR_META:
        return SENSOR_META[object_id]

    name = object_id.replace("_", " ").strip().title() or object_id
    oid = object_id.lower()

    # Binary ON/OFF Namen (Wert entscheidet später nicht die Klasse – Heuristik)
    if oid in ("lost", "ct_flag", "shelly_flag", "smart_plan", "safety_enable") or oid.endswith("_enable"):
        return (name, None, None, None, "binary_sensor")

    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    component = "sensor"

    if oid.endswith("_soc") or oid in ("soc", "bms_soc", "soc1", "soc2") or re.search(r"(^|_)soc($|_)", oid):
        unit, device_class = "%", "battery"
    elif "temp" in oid and "template" not in oid and "type" not in oid:
        unit, device_class = "°C", "temperature"
    elif oid.endswith("_voltage") or re.match(r"^v(pv|ac|bat|bus)", oid) or oid in ("vacr", "vacrs", "dc_voltage"):
        unit, device_class = "V", "voltage"
    elif oid.endswith("_current") or re.match(r"^i(pv|ac|bat)", oid) or oid.startswith("ipv") or oid.startswith("iac"):
        unit, device_class = "A", "current"
    elif oid in ("fac", "eps_fac") or oid.endswith("_freq") or "frequency" in oid:
        unit, device_class = "Hz", "frequency"
    elif oid.endswith("_dbm") or "wifi" in oid or "signal" in oid:
        unit, device_class = "dBm", "signal_strength"
    elif (
        any(oid.endswith(s) or s in oid for s in ("_today", "_total", "_month", "_year"))
        and any(p in oid for p in ("eac", "epv", "energy", "e_to_", "e_local", "e_self", "e_system", "e_charge", "e_discharge", "generation", "eex"))
    ) or re.match(r"^e(ac|pv|_|to_|local|self|system|charge|discharge)", oid):
        unit, device_class, state_class = "kWh", "energy", "total_increasing"
    elif (
        oid.endswith("_power")
        or oid.startswith("ppv")
        or oid.startswith("pac")
        or oid in ("ppv", "pac", "pex1", "pex2", "p_self", "p_system", "groplug_power")
    ):
        unit, device_class = "W", "power"
    elif "soh" in oid:
        unit, device_class = "%", "battery"
    elif oid.endswith("_pf") or oid == "pf" or oid.startswith("eps_pf"):
        device_class = "power_factor"
        unit = None
    elif oid in ("last_update", "time_str", "sys_time", "sys_time_text") or oid.endswith("_time_text"):
        device_class = "timestamp"
        state_class = None
    elif oid.endswith("_cycles") or "icycle" in oid:
        state_class = "total_increasing"
        unit = None
    else:
        # reine Status-/Config-Texte ohne Messklasse
        if any(x in oid for x in ("text", "alias", "model", "version", "mode", "status", "warn", "fault", "sn")):
            state_class = None

    return (name, unit, device_class, state_class, component)


class HaMqtt:
    def __init__(
        self,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        discovery_prefix: str = "homeassistant",
        state_prefix: str = "growatt_cloud",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.discovery_prefix = discovery_prefix.rstrip("/") or "homeassistant"
        self.state_prefix = state_prefix.rstrip("/") or "growatt_cloud"
        self._client = None
        self._discovery_sig: dict[str, str] = {}
        self._discovery_keys: dict[str, set[str]] = {}
        self._connected = threading.Event()
        self._keys_path = "/data/growatt_discovery_keys.json"
        self._load_discovery_keys()

    def _load_discovery_keys(self) -> None:
        try:
            if not os.path.isfile(self._keys_path):
                return
            with open(self._keys_path, encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                self._discovery_keys = {k: set(v) for k, v in raw.items() if isinstance(v, list)}
        except Exception:
            self._discovery_keys = {}

    def _save_discovery_keys(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._keys_path), exist_ok=True)
            payload = {k: sorted(v) for k, v in self._discovery_keys.items()}
            with open(self._keys_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
        except Exception as exc:
            LOG.debug("Discovery-Keys speichern: %s", exc)

    def connect(self) -> None:
        import paho.mqtt.client as mqtt

        client_id = f"growatt-cloud-{os.getpid()}"
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id=client_id,
            )
        except (AttributeError, TypeError, ValueError):
            client = mqtt.Client(client_id=client_id)

        if self.username:
            client.username_pw_set(self.username, self.password or None)

        client.will_set(f"{self.state_prefix}/status", "offline", retain=True)

        def on_connect(c, _u, _f, rc, *_a):
            if rc == 0:
                LOG.info("MQTT verbunden (%s:%s)", self.host, self.port)
                self._discovery_sig.clear()
                self._discovery_keys.clear()
                c.publish(f"{self.state_prefix}/status", "online", retain=True)
                self._connected.set()
            else:
                LOG.error("MQTT Connect rc=%s", rc)
                self._connected.clear()

        def on_disconnect(_c, _u, rc, *_a):
            self._connected.clear()
            if rc != 0:
                LOG.warning("MQTT getrennt (rc=%s) – reconnect läuft", rc)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        LOG.info("MQTT verbindet zu %s:%s …", self.host, self.port)
        client.connect(self.host, self.port, keepalive=60)
        client.loop_start()
        self._client = client
        if not self._connected.wait(15):
            LOG.error(
                "MQTT nicht verbunden nach 15 s – Host/User/Pass prüfen "
                "(typisch core-mosquitto, ggf. MQTT-User der Mosquitto-App)"
            )

    def wait_connected(self, timeout: float = 15.0) -> bool:
        return self._connected.wait(timeout)

    def stop(self) -> None:
        if self._client:
            try:
                self._client.publish(f"{self.state_prefix}/status", "offline", retain=True)
            except Exception:
                pass
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected.clear()

    def _pub(self, topic: str, payload: str, retain: bool = True) -> None:
        if not self._client:
            return
        if not self._connected.is_set():
            self._connected.wait(2)
        info = self._client.publish(topic, payload, qos=1, retain=retain)
        if getattr(info, "rc", 0) != 0:
            LOG.warning("MQTT publish rc=%s topic=%s", info.rc, topic)

    def _device(self, serial: str, name: str, model: str) -> dict[str, Any]:
        return {
            "identifiers": [f"growatt_cloud_{slug(serial)}"],
            "name": name,
            "manufacturer": "Growatt",
            "model": model,
            "serial_number": serial,
        }

    def ensure_discovery(self, serial: str, label: str, values: dict[str, Any]) -> None:
        """Discovery für gefilterte Werte; entfernte Keys werden per leerem Config gelöscht."""
        keys = sorted(k for k in values if k not in _META_SKIP and values[k] is not None)
        device_name = str(values.get("device_name") or values.get("alias") or serial)
        model = str(values.get("model") or f"Growatt {label}")
        sig = f"{device_name}|{model}|{'|'.join(keys)}"
        if self._discovery_sig.get(serial) == sig:
            return
        device = self._device(serial, device_name, model)
        node = slug(serial)
        new_keys = set(keys)
        old_keys = self._discovery_keys.get(serial) or set()
        for gone in sorted(old_keys - new_keys):
            for component in ("sensor", "binary_sensor"):
                self._pub(f"{self.discovery_prefix}/{component}/{node}/{gone}/config", "", retain=True)
        count = 0
        for object_id in keys:
            name, unit, device_class, state_class, component = infer_meta(object_id)
            val = values.get(object_id)
            if isinstance(val, str) and val.upper() in ("ON", "OFF") and component == "sensor":
                if object_id in (
                    "heating",
                    "connectivity",
                    "allow_grid_charging",
                    "lost",
                    "ct_flag",
                    "shelly_flag",
                ) or object_id.endswith("_enable"):
                    component = "binary_sensor"
            unique = f"growatt_cloud_{node}_{object_id}"
            topic = f"{self.discovery_prefix}/{component}/{node}/{object_id}/config"
            state_topic = f"{self.state_prefix}/{node}/{object_id}"
            payload: dict[str, Any] = {
                "name": name,
                "unique_id": unique,
                "object_id": f"{node}_{object_id}",
                "state_topic": state_topic,
                "device": device,
                "availability_topic": f"{self.state_prefix}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            if component == "binary_sensor":
                payload["payload_on"] = "ON"
                payload["payload_off"] = "OFF"
            if unit:
                payload["unit_of_measurement"] = unit
            if device_class:
                payload["device_class"] = device_class
            if state_class:
                payload["state_class"] = state_class
            if device_class == "energy":
                payload["state_class"] = "total_increasing"
            if device_class == "timestamp" and not (isinstance(val, str) and "T" in val):
                payload.pop("device_class", None)
            self._pub(topic, json.dumps(payload), retain=True)
            count += 1
        self._discovery_sig[serial] = sig
        self._discovery_keys[serial] = new_keys
        self._save_discovery_keys()
        self._pub(f"{self.state_prefix}/status", "online", retain=True)
        LOG.info("HA-Discovery %s (%s) %s → %s Entities", label, device_name, serial, count)
        time.sleep(0.15)

    def ensure_storage_discovery(self, serial: str, label: str) -> None:
        self.ensure_discovery(
            serial,
            label,
            {
                "soc": 0,
                "solar_power": 0,
                "output_power": 0,
                "charging_power": 0,
                "discharge_power": 0,
                "generation_today": 0,
                "generation_total": 0,
                "battery_num": 1,
                "system_temp": 0,
                "ct_power": 0,
                "work_mode": "unknown",
                "heating": "OFF",
                "connectivity": "ON",
            },
        )

    def ensure_inverter_discovery(self, serial: str) -> None:
        self.ensure_discovery(
            serial,
            "Wechselrichter",
            {
                "ac_power": 0,
                "energy_today": 0,
                "energy_total": 0,
                "energy_today_input_1": 0,
                "energy_today_input_2": 0,
                "ppv": 0,
                "ppv1": 0,
                "ppv2": 0,
                "connectivity": "ON",
                "status": "unknown",
            },
        )

    def publish_states(self, serial: str, values: dict[str, Any]) -> None:
        node = slug(serial)
        for key, value in values.items():
            if key in _META_SKIP:
                continue
            if value is None:
                continue
            self._pub(f"{self.state_prefix}/{node}/{key}", str(value), retain=True)
        self._pub(f"{self.state_prefix}/status", "online", retain=True)
