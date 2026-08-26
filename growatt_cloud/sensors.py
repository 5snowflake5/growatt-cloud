"""Rohdaten Growatt v4 → flache Sensor-Maps (Keys = MQTT object_id).

Strategie: ALLE skalaren Felder aus queryLastData (+ optional queryDeviceInfo)
werden als Sensoren veröffentlicht. Zusätzlich bleiben freundliche Aliase
(soc, solar_power, …) für Dashboards und Abwärtskompatibilität.
"""

from __future__ import annotations

import re
from typing import Any

WORK_MODE = {0: "load_first", 1: "battery_first", 2: "smart"}
CHARGE_STATUS = {0: "idle", 1: "charging", 2: "discharging"}

# Keine eigenen Entities (IDs / verschachtelte Blobs)
_SKIP_KEYS = {
    "device_sn",
    "datalogger_sn",
    "serial_num",
    "bat_sn",
    "battery_sn",
    "plant_id",
    "address",
    "tlx_bean",
    "inv_set_bean",
    "record",
    "children",
    "optimizer_list",
    "energy_day_map",
    "family",
    "label",
}


def _camel_to_snake(name: str) -> str:
    text = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return text.replace("-", "_").lower()


def _num(data: dict[str, Any], *keys: str, default: float | None = 0.0) -> float | None:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            try:
                return float(data[key])
            except (TypeError, ValueError):
                continue
    return default


def _int(data: dict[str, Any], *keys: str, default: int = 0) -> int:
    value = _num(data, *keys, default=float(default))
    return int(value if value is not None else default)


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def detect_storage_label(raw: dict[str, Any], serial: str | None = None) -> str:
    """Noah vs Nexa: API-Typ ist bei beiden 'noah' – Unterscheidung über Model/Alias/SN.

    Typische Serial-Präfixe: 0PVP… = Noah, 0HVR… = Nexa.
    """
    sn = str(
        serial
        or raw.get("deviceSn")
        or raw.get("device_sn")
        or raw.get("datalogSn")
        or raw.get("datalog_sn")
        or raw.get("dataloggerSn")
        or raw.get("datalogger_sn")
        or ""
    ).strip().upper()

    blob = " ".join(
        str(x)
        for x in (
            raw.get("model"),
            raw.get("modelName"),
            raw.get("model_name"),
            raw.get("alias"),
            raw.get("manName"),
            raw.get("man_name"),
        )
        if x
    ).lower()

    # Explizite Model-/Alias-Treffer zuerst (nicht "neo" – das ist der Balkon-WR)
    if re.search(r"\bnexa\b", blob) or "nexa 2000" in blob or "nexa2000" in blob:
        return "Nexa"
    if re.search(r"\bnoah\b", blob) or "noah 2000" in blob or "noah2000" in blob:
        return "Noah"

    if sn.startswith("0HVR") or sn.startswith("HVR"):
        return "Nexa"
    if sn.startswith("0PVP") or sn.startswith("PVP"):
        return "Noah"

    # Fallback: API liefert type=noah für beide
    return "Noah"


def storage_device_name(raw: dict[str, Any], label: str, serial: str) -> str:
    alias = _pick(raw, "alias", "Alias")
    if alias and str(alias).strip() and str(alias).strip().upper() != serial.upper():
        return str(alias).strip()
    model = _pick(raw, "model", "Model")
    if model and str(model).strip():
        return str(model).strip()
    return f"{label} {serial}"


def flatten_raw(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Alle skalaren API-Keys → snake_case Sensorwerte."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            continue
        snake = _camel_to_snake(str(key))
        if snake in _SKIP_KEYS or snake.startswith("_"):
            continue
        if isinstance(value, bool):
            out[snake] = "ON" if value else "OFF"
            continue
        if isinstance(value, (int, float)):
            out[snake] = value
            continue
        text = str(value).strip()
        if not text:
            continue
        # numerische Strings als Zahl (HA mag das für Charts)
        try:
            if re.fullmatch(r"-?\d+", text):
                out[snake] = int(text)
                continue
            if re.fullmatch(r"-?\d+\.\d+", text):
                out[snake] = float(text)
                continue
        except ValueError:
            pass
        low = text.lower()
        if low in ("true", "false"):
            out[snake] = "ON" if low == "true" else "OFF"
            continue
        out[snake] = text
    return out


def _curated_storage(raw: dict[str, Any]) -> dict[str, Any]:
    bat = _num(raw, "totalBatteryPackChargingPower", "total_battery_pack_charging_power") or 0.0
    status = _int(raw, "totalBatteryPackChargingStatus", "total_battery_pack_charging_status")
    if status == 1:
        charge_w, discharge_w = abs(bat), 0.0
    elif status == 2:
        charge_w, discharge_w = 0.0, abs(bat)
    else:
        charge_w = max(bat, 0.0)
        discharge_w = abs(min(bat, 0.0))

    label = detect_storage_label(raw)
    packs = _int(raw, "batteryPackageQuantity", "battery_package_quantity", default=1)
    packs = max(1, min(packs, 4))
    work = _int(raw, "workMode", "work_mode")
    heating = _int(raw, "heatingStatus", "heating_status")
    lost = raw.get("lost") in (True, 1, "1", "true", "True")
    sn = str(
        _pick(raw, "deviceSn", "device_sn", "datalogSn", "datalog_sn", "dataloggerSn", "datalogger_sn") or ""
    )
    # Label nochmal mit SN absichern (falls Model fehlt)
    label = detect_storage_label(raw, sn or None)

    out: dict[str, Any] = {
        "family": label.lower(),
        "label": label,
        "device_name": storage_device_name(raw, label, sn or "storage"),
        "soc": _num(raw, "totalBatteryPackSoc", "total_battery_pack_soc", "soc"),
        "solar_power": _num(raw, "ppv"),
        "output_power": abs(_num(raw, "pac") or 0.0),
        "charging_power": charge_w,
        "discharge_power": discharge_w,
        "generation_today": _num(raw, "eacToday", "eac_today"),
        "generation_total": _num(raw, "eacTotal", "eac_total"),
        "generation_month": _num(raw, "eacMonth", "eac_month"),
        "generation_year": _num(raw, "eacYear", "eac_year"),
        "battery_num": packs,
        "system_temp": _num(raw, "systemTemp", "system_temp"),
        "ct_power": _num(raw, "ctSelfPower", "ct_self_power"),
        "household_load": _num(raw, "totalHouseholdLoad", "total_household_load"),
        "on_grid_power": _num(raw, "onGridPower", "on_grid_power"),
        "off_grid_power": _num(raw, "offGridPower", "off_grid_power"),
        "charge_soc_limit": _num(
            raw, "chargeSocLimit", "charge_soc_limit", "chargingSocHighLimit", "charging_soc_high_limit"
        ),
        "discharge_soc_limit": _num(
            raw, "dischargeSocLimit", "discharge_soc_limit", "chargingSocLowLimit", "charging_soc_low_limit"
        ),
        "battery_soh": _num(raw, "batterySoh", "battery_soh"),
        "battery_cycles": _num(raw, "batteryCycles", "battery_cycles"),
        "work_mode": WORK_MODE.get(work, str(work)),
        "work_mode_code": work,
        "charge_status": CHARGE_STATUS.get(status, str(status)),
        "status_code": _int(raw, "status"),
        "heating": "ON" if heating else "OFF",
        "connectivity": "OFF" if lost else "ON",
        "last_update": _pick(raw, "timeStr", "time_str", "time", "lastUpdateTimeText", "last_update_time_text"),
    }

    for i in range(1, 5):
        if i > packs:
            continue
        soc = _num(raw, f"battery{i}Soc", f"battery{i}_soc", default=None)
        temp = _num(raw, f"battery{i}Temp", f"battery{i}_temp", default=None)
        out[f"battery{i}_soc"] = soc if soc is not None else 0.0
        out[f"battery{i}_temp"] = temp if temp is not None else 0.0

    for i in range(1, 5):
        v = _num(raw, f"pv{i}Voltage", f"pv{i}_voltage", default=None)
        a = _num(raw, f"pv{i}Current", f"pv{i}_current", default=None)
        if v is None and a is None:
            continue
        vv, aa = v or 0.0, a or 0.0
        out[f"pv{i}_voltage"] = vv
        out[f"pv{i}_current"] = aa
        out[f"pv{i}_power"] = round(vv * aa, 1)

    return out


def _curated_min(raw: dict[str, Any]) -> dict[str, Any]:
    status = _pick(raw, "statusText", "status_text", "status")
    return {
        "family": "min",
        "label": "Wechselrichter",
        "ac_power": _num(raw, "pac"),
        "ac_power_r": _num(raw, "pac1", "pacr"),
        "ac_power_s": _num(raw, "pac2"),
        "ac_power_t": _num(raw, "pac3"),
        "energy_today": _num(raw, "eacToday", "eac_today", "powerToday", "power_today"),
        "energy_total": _num(raw, "eacTotal", "eac_total", "powerTotal", "power_total"),
        "energy_today_input_1": _num(raw, "epv1Today", "epv1_today"),
        "energy_today_input_2": _num(raw, "epv2Today", "epv2_today"),
        "energy_today_input_3": _num(raw, "epv3Today", "epv3_today"),
        "energy_today_input_4": _num(raw, "epv4Today", "epv4_today"),
        "energy_total_input_1": _num(raw, "epv1Total", "epv1_total"),
        "energy_total_input_2": _num(raw, "epv2Total", "epv2_total"),
        "energy_total_input_3": _num(raw, "epv3Total", "epv3_total"),
        "energy_total_input_4": _num(raw, "epv4Total", "epv4_total"),
        "energy_total_pv": _num(raw, "epvTotal", "epv_total"),
        "ppv": _num(raw, "ppv"),
        "ppv1": _num(raw, "ppv1"),
        "ppv2": _num(raw, "ppv2"),
        "ppv3": _num(raw, "ppv3"),
        "ppv4": _num(raw, "ppv4"),
        "ipv1": _num(raw, "ipv1"),
        "ipv2": _num(raw, "ipv2"),
        "ipv3": _num(raw, "ipv3"),
        "ipv4": _num(raw, "ipv4"),
        "vpv1": _num(raw, "vpv1"),
        "vpv2": _num(raw, "vpv2"),
        "vpv3": _num(raw, "vpv3"),
        "vpv4": _num(raw, "vpv4"),
        "vac1": _num(raw, "vac1", "vacr"),
        "vac2": _num(raw, "vac2"),
        "vac3": _num(raw, "vac3"),
        "iac1": _num(raw, "iac1", "iacr"),
        "iac2": _num(raw, "iac2"),
        "iac3": _num(raw, "iac3"),
        "fac": _num(raw, "fac"),
        "temperature": _num(raw, "temp1", "temperature"),
        "temperature_2": _num(raw, "temp2"),
        "temperature_3": _num(raw, "temp3"),
        "temperature_4": _num(raw, "temp4"),
        "temperature_5": _num(raw, "temp5"),
        "pf": _num(raw, "pf"),
        "export_power": _num(raw, "pacToGridTotal", "pac_to_grid_total"),
        "import_power": _num(raw, "pacToUserTotal", "pac_to_user_total"),
        "local_load_power": _num(raw, "pacToLocalLoad", "pac_to_local_load"),
        "energy_to_grid_today": _num(raw, "eToGridToday", "e_to_grid_today"),
        "energy_to_grid_total": _num(raw, "eToGridTotal", "e_to_grid_total"),
        "energy_to_user_today": _num(raw, "eToUserToday", "e_to_user_today"),
        "energy_to_user_total": _num(raw, "eToUserTotal", "e_to_user_total"),
        "energy_local_load_today": _num(raw, "eLocalLoadToday", "e_local_load_today"),
        "energy_local_load_total": _num(raw, "eLocalLoadTotal", "e_local_load_total"),
        "status": status if status is not None else "unknown",
        "status_code": _int(raw, "status") if isinstance(_pick(raw, "status"), (int, float, str)) else 0,
        "connectivity": "OFF" if raw.get("lost") in (True, 1, "1", "true", "True") else "ON",
        "last_update": _pick(raw, "time", "timeStr", "time_str"),
    }


# Keys die im Modus "useful" zusätzlich zu den Aliasen erlaubt sind
_USEFUL_EXTRA_STORAGE = {
    "wifi_signal",
    "fw_version",
    "model",
    "alias",
    "max_cell_voltage",
    "min_cell_voltage",
    "fault_status",
    "on_grid_voltage",
    "on_grid_current",
    "off_grid_voltage",
    "off_grid_current",
    "pv1_temp",
    "pv2_temp",
    "pv3_temp",
    "pv4_temp",
    "device_to_grid_power",
    "grid_to_device_power",
    "allow_grid_charging",
}

_USEFUL_EXTRA_MIN = {
    "wifi_signal",
    "fw_version",
    "inner_version",
    "model_text",
    "pmax",
    "status_text",
}

# Roh-Duplikate der freundlichen Aliase
_RAW_DUPES = {
    "total_battery_pack_soc",
    "total_battery_pack_charging_power",
    "total_battery_pack_charging_status",
    "eac_today",
    "eac_total",
    "eac_month",
    "eac_year",
    "ct_self_power",
    "total_household_load",
    "household_load_apart_from_groplug",
    "battery_package_quantity",
    "charging_soc_high_limit",
    "charging_soc_low_limit",
    "heating_status",
    "ppv",
    "pac",
    "pac1",
    "pacr",
    "status",
    "lost",
    "time_str",
    "last_update_time",
    "last_update_time_text",
    "sys_time",
    "sys_time_text",
    "datalog_sn",
    "datalogger_sn",
    "data_log_sn",
    "epv1_today",
    "epv2_today",
    "epv3_today",
    "epv4_today",
    "epv1_total",
    "epv2_total",
    "epv3_total",
    "epv4_total",
    "epv_total",
    "e_to_grid_today",
    "e_to_grid_total",
    "e_to_user_today",
    "e_to_user_total",
    "e_local_load_today",
    "e_local_load_total",
    "elocal_load_today",
    "elocal_load_total",
    "eto_grid_today",
    "eto_grid_total",
    "eto_user_today",
    "eto_user_total",
    "pac_to_grid_total",
    "pac_to_user_total",
    "pac_to_local_load",
    "temp1",
    "temp2",
    "temp3",
    "temp4",
    "temp5",
    "status_text",
}

_ALWAYS_DROP_SUFFIXES = ("_temp_f",)
_ALWAYS_DROP_KEYS = {
    "is_again",
    "again",
    "address",
    "addr",
    "timezone",
    "temp_type",
    "settable_time_period",
    "ebm_order_num",
    "eastron_ammeter_control_pair",
    "ammeter_unbind",
    "ota_device_type_code_high",
    "ota_device_type_code_low",
    "port_name",
    "man_name",
    "manufacturer",
    "associated_inv_man_and_model",
    "associated_inv_sn",
    "calendar",
    "day",
    "with_time",
    "time_total",
    "total_working_time",
    "group_id",
    "id",
    "level",
    "img_path",
    "parent_id",
    "tree_id",
    "tcp_server_ip",
    "debug1",
    "debug2",
    "updating",
    "com_address",
    "device_type",
    "dtc",
    "modbus_version",
    "hw_version",
    "version_flag",
    "priority_choose",
    "traker_model",
    "wselect_baudrate",
    "str_num",
    "pv_num",
    "battery_no",
    "battery_type",
    "bat_cluster_num",
    "bat_parallel_num",
    "bat_series_num",
    "b_merter_connect_flag",
    "baging_test_step",
    "bct_adjust",
    "bct_mode",
    "bcu_version",
    "bdc_authversion",
    "bdc_link_num",
    "bdc1_model",
    "bdc1_version",
    "country_selected",
    "safety_version",
    "vpp_open",
    "vpp_version",
    "mppt",
    "vnormal",
    "inv_delay_time",
    "restart_time",
    "start_time",
    "real_op_percent",
    "load_percent",
    "op_fullwatt",
    "operating_mode",
    "uw_sys_work_mode",
    "bsystem_work_mode",
    "derating_mode",
    "dry_contact_status",
    "gfci",
    "iso",
    "pex1",
    "pex2",
    "eex1_today",
    "eex1_total",
    "eex2_today",
    "eex2_total",
    "power",
    "power_of_grid_feed",
    "power_of_grid_take",
    "power_of_load",
    "power_of_photovoltaic",
    "p_charge",
    "p_discharge",
    "charge_power_of_battery",
    "dis_charge_power_of_battery",
    "pself",
    "psystem",
    "e_today",
    "e_total",
    "energy_month",
    "energy_month_text",
    "warn_text",
    "error_text",
    "iacr",
    "vacr",
    "vacrs",
    "vac_rs",
    "vac_st",
    "vac_tr",
    "n_bus_voltage",
    "p_bus_voltage",
    "dc_voltage",
    "dci_r",
    "dci_s",
    "dci_t",
    "fault_type",
    "fault_type1",
    "new_warn_code",
    "new_warn_sub_code",
    "warn_code",
    "warn_code1",
    "mtnc_mode",
    "mtnc_rqst",
}

# Prefixes: bei Balkon-WR ohne echte Batterie komplett weg; sonst nur Nullwerte
_MIN_BATTERY_PREFIXES = (
    "bdc",
    "bms_",
    "bat_",
    "eps_",
    "win_",
    "soc1",
    "soc2",
    "vbat_",
    "sys_fault_word",
)

_MIN_ALIAS_MAP = {
    "pac": "ac_power",
    "pac1": "ac_power_r",
    "pacr": "ac_power_r",
    "pac2": "ac_power_s",
    "pac3": "ac_power_t",
    "eac_today": "energy_today",
    "eac_total": "energy_total",
    "epv1_today": "energy_today_input_1",
    "epv2_today": "energy_today_input_2",
    "epv3_today": "energy_today_input_3",
    "epv4_today": "energy_today_input_4",
    "epv1_total": "energy_total_input_1",
    "epv2_total": "energy_total_input_2",
    "epv3_total": "energy_total_input_3",
    "epv4_total": "energy_total_input_4",
    "epv_total": "energy_total_pv",
    "pac_to_grid_total": "export_power",
    "pac_to_user_total": "import_power",
    "pac_to_local_load": "local_load_power",
    "e_to_grid_today": "energy_to_grid_today",
    "eto_grid_today": "energy_to_grid_today",
    "e_to_grid_total": "energy_to_grid_total",
    "eto_grid_total": "energy_to_grid_total",
    "e_to_user_today": "energy_to_user_today",
    "eto_user_today": "energy_to_user_today",
    "e_to_user_total": "energy_to_user_total",
    "eto_user_total": "energy_to_user_total",
    "e_local_load_today": "energy_local_load_today",
    "elocal_load_today": "energy_local_load_today",
    "e_local_load_total": "energy_local_load_total",
    "elocal_load_total": "energy_local_load_total",
    "temp1": "temperature",
    "temp2": "temperature_2",
    "temp3": "temperature_3",
    "temp4": "temperature_4",
    "temp5": "temperature_5",
    "status_text": "status",
    "lost": "connectivity",
    "time_str": "last_update",
    "last_update_time_text": "last_update",
    "last_update_time": "last_update",
}


def _near_zero(value: Any, eps: float = 0.05) -> bool:
    try:
        return abs(float(value)) <= eps
    except (TypeError, ValueError):
        return False


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, str) and value.strip().lower() in ("unknown", "unbekannt", "none", "null", "-"):
        return True
    return False


def _is_epoch_ms(value: Any) -> bool:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    return 1_000_000_000_000 <= n <= 4_000_000_000_000


def _prune_inactive_pv(out: dict[str, Any]) -> None:
    for i in range(1, 5):
        power = out.get(f"pv{i}_power")
        if power is None:
            power = out.get(f"ppv{i}")
        volts = out.get(f"pv{i}_voltage")
        if volts is None:
            volts = out.get(f"vpv{i}")
        amps = out.get(f"pv{i}_current")
        if amps is None:
            amps = out.get(f"ipv{i}")
        active = False
        for v in (power, volts, amps):
            try:
                if v is not None and abs(float(v)) > 0.05:
                    active = True
                    break
            except (TypeError, ValueError):
                continue
        if active:
            continue
        for key in (
            f"pv{i}_power",
            f"pv{i}_voltage",
            f"pv{i}_current",
            f"pv{i}_temp",
            f"ppv{i}",
            f"vpv{i}",
            f"ipv{i}",
            f"energy_today_input_{i}",
            f"energy_total_input_{i}",
            f"epv{i}_today",
            f"epv{i}_total",
        ):
            out.pop(key, None)


def _has_min_battery(out: dict[str, Any]) -> bool:
    for key in ("bms_soc", "bdc1_soc", "bdc1_vbat", "soc1", "bms_vbat"):
        try:
            if abs(float(out.get(key) or 0)) > 0.5:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _prune_min_phases(out: dict[str, Any]) -> None:
    """Einphasig: S/T und unnötige Phasen-Leistungen weg."""
    multiphase = False
    for key in ("vac2", "vac3", "iac2", "iac3", "ac_power_s", "ac_power_t", "pac2", "pac3"):
        if key in out and not _near_zero(out[key]):
            multiphase = True
            break
    if multiphase:
        return
    for key in (
        "vac2",
        "vac3",
        "iac2",
        "iac3",
        "ac_power_r",
        "ac_power_s",
        "ac_power_t",
        "pac1",
        "pac2",
        "pac3",
        "pacr",
        "vac_st",
        "vac_tr",
    ):
        out.pop(key, None)


def _prune_zero_temps(out: dict[str, Any]) -> None:
    for key in ("temperature_2", "temperature_3", "temperature_4", "temperature_5", "temp2", "temp3", "temp4", "temp5"):
        if key in out and _near_zero(out[key]):
            out.pop(key, None)


def _prune_min_noise(out: dict[str, Any], *, aggressive: bool) -> None:
    """Balkon-WR: Batterie/EPS/BMS-Nullfelder und Admin-Müll entfernen."""
    keep_battery = _has_min_battery(out)
    for key in list(out.keys()):
        if key.startswith(_MIN_BATTERY_PREFIXES) or key in ("soc1", "soc2"):
            if not keep_battery or (aggressive and _near_zero(out[key])):
                out.pop(key, None)
                continue
        if key in _ALWAYS_DROP_KEYS:
            out.pop(key, None)
            continue
        # kryptische model-Zahl
        if key == "model" and isinstance(out[key], (int, float)) and float(out[key]) > 1e6:
            out.pop(key, None)
            continue
        if aggressive and key.startswith(("eac_charge", "echarge", "edischarge", "eself", "esystem")):
            if _near_zero(out[key]):
                out.pop(key, None)
        if aggressive and key in (
            "export_power",
            "import_power",
            "local_load_power",
            "energy_to_grid_today",
            "energy_to_grid_total",
            "energy_to_user_today",
            "energy_to_user_total",
            "energy_local_load_today",
            "energy_local_load_total",
        ):
            if _near_zero(out[key]):
                out.pop(key, None)


def _drop_alias_dupes(out: dict[str, Any], kind: str) -> None:
    alias_map = dict(_MIN_ALIAS_MAP) if kind == "min" else {}
    if kind == "storage":
        alias_map.update(
            {
                "total_battery_pack_soc": "soc",
                "total_battery_pack_charging_power": "charging_power",
                "total_battery_pack_charging_status": "charge_status",
                "eac_today": "generation_today",
                "eac_total": "generation_total",
                "eac_month": "generation_month",
                "eac_year": "generation_year",
                "ct_self_power": "ct_power",
                "total_household_load": "household_load",
                "ppv": "solar_power",
                "pac": "output_power",
                "lost": "connectivity",
                "heating_status": "heating",
                "time_str": "last_update",
                "last_update_time_text": "last_update",
                "last_update_time": "last_update",
            }
        )
    for raw_key, alias in alias_map.items():
        if raw_key in out and alias in out and raw_key != alias:
            out.pop(raw_key, None)
    # status vs status_code: Text behalten, Code behalten – raw status int weg wenn status Text
    if "status" in out and "status_code" in out:
        if isinstance(out["status"], str):
            pass
        elif out["status"] == out["status_code"]:
            out.pop("status", None)


def filter_published_values(
    values: dict[str, Any],
    *,
    kind: str,
    mode: str = "useful",
) -> dict[str, Any]:
    """Rauschen entfernen. mode=useful (Default) oder full."""
    mode = (mode or "useful").strip().lower()
    if mode not in ("useful", "full"):
        mode = "useful"

    out = dict(values)
    meta = {k: out.pop(k) for k in ("family", "label", "device_name") if k in out}

    for key in list(out.keys()):
        val = out[key]
        if _is_empty(val):
            out.pop(key, None)
            continue
        if key in _ALWAYS_DROP_KEYS or any(key.endswith(s) for s in _ALWAYS_DROP_SUFFIXES):
            out.pop(key, None)
            continue
        if _is_epoch_ms(val) and ("time" in key or key.startswith("sys_") or key == "calendar"):
            out.pop(key, None)
            continue
        if re.match(r"^time[1-9]_(start|end|enable)$", key):
            out.pop(key, None)
            continue
        if key.endswith("_serial_num") and (val in (0, "0") or _is_empty(val)):
            out.pop(key, None)
            continue

    _prune_inactive_pv(out)
    if kind == "min":
        _prune_min_phases(out)
        _prune_zero_temps(out)
        _prune_min_noise(out, aggressive=True)
    _drop_alias_dupes(out, kind)

    if mode == "useful":
        extras = _USEFUL_EXTRA_STORAGE if kind == "storage" else _USEFUL_EXTRA_MIN
        keep = set(_CURATED_KEEP_STORAGE if kind == "storage" else _CURATED_KEEP_MIN)
        keep |= extras
        out = {k: v for k, v in out.items() if k in keep}
        out = {k: v for k, v in out.items() if not re.match(r"^time[1-9]_", k)}
        if "allow_grid_charging" in out:
            try:
                out["allow_grid_charging"] = "ON" if int(float(out["allow_grid_charging"])) else "OFF"
            except (TypeError, ValueError):
                out.pop("allow_grid_charging", None)
        for key in list(out.keys()):
            if key.endswith(("_protect_status", "_warn_status")) or key in (
                "ac_couple_protect_status",
                "ac_couple_warn_status",
                "mppt_protect_status",
                "pd_warn_status",
                "fault_status",
            ):
                try:
                    if float(out[key]) == 0:
                        out.pop(key, None)
                except (TypeError, ValueError):
                    out.pop(key, None)
        if kind == "min":
            _prune_min_phases(out)
            _prune_zero_temps(out)
            # optionale Null-Energien im useful-Modus weg
            for key in list(out.keys()):
                if key.startswith(("energy_to_", "energy_local_", "export_", "import_", "local_load_")):
                    if _near_zero(out[key]):
                        out.pop(key, None)
    else:
        # full: weiterhin stark bereinigt (kein Balkon-Wahnsinn), aber Extra-Felder erlaubt
        for key in list(out.keys()):
            if key.endswith(("_protect_status", "_warn_status")) or key in (
                "ac_couple_protect_status",
                "ac_couple_warn_status",
                "mppt_protect_status",
                "pd_warn_status",
                "fault_status",
            ):
                try:
                    if float(out[key]) == 0:
                        out.pop(key, None)
                except (TypeError, ValueError):
                    pass
        if kind == "min":
            _prune_min_noise(out, aggressive=True)

    out.update(meta)
    return out


# Alias-Keys die im useful-Modus immer Kandidaten sind
_CURATED_KEEP_STORAGE = {
    "soc",
    "solar_power",
    "output_power",
    "charging_power",
    "discharge_power",
    "generation_today",
    "generation_total",
    "generation_month",
    "generation_year",
    "battery_num",
    "system_temp",
    "ct_power",
    "household_load",
    "on_grid_power",
    "off_grid_power",
    "charge_soc_limit",
    "discharge_soc_limit",
    "battery_soh",
    "battery_cycles",
    "work_mode",
    "charge_status",
    "status_code",
    "heating",
    "connectivity",
    "last_update",
    "battery1_soc",
    "battery1_temp",
    "battery2_soc",
    "battery2_temp",
    "battery3_soc",
    "battery3_temp",
    "battery4_soc",
    "battery4_temp",
    "pv1_power",
    "pv1_voltage",
    "pv1_current",
    "pv2_power",
    "pv2_voltage",
    "pv2_current",
    "pv3_power",
    "pv3_voltage",
    "pv3_current",
    "pv4_power",
    "pv4_voltage",
    "pv4_current",
}

# Schlanker MIN-Kern (~Growatt-Server „sinnvoll“)
_CURATED_KEEP_MIN = {
    "ac_power",
    "ac_power_r",
    "ac_power_s",
    "ac_power_t",
    "energy_today",
    "energy_total",
    "energy_today_input_1",
    "energy_today_input_2",
    "energy_today_input_3",
    "energy_today_input_4",
    "energy_total_input_1",
    "energy_total_input_2",
    "energy_total_input_3",
    "energy_total_input_4",
    "energy_total_pv",
    "ppv",
    "ppv1",
    "ppv2",
    "ppv3",
    "ppv4",
    "ipv1",
    "ipv2",
    "ipv3",
    "ipv4",
    "vpv1",
    "vpv2",
    "vpv3",
    "vpv4",
    "vac1",
    "vac2",
    "vac3",
    "iac1",
    "iac2",
    "iac3",
    "fac",
    "temperature",
    "temperature_2",
    "pf",
    "export_power",
    "import_power",
    "local_load_power",
    "energy_to_grid_today",
    "energy_to_grid_total",
    "energy_to_user_today",
    "energy_to_user_total",
    "energy_local_load_today",
    "energy_local_load_total",
    "status",
    "status_code",
    "connectivity",
    "last_update",
}

SENSOR_META_HINTS = _CURATED_KEEP_STORAGE | _CURATED_KEEP_MIN


def merge_device_values(
    energy: dict[str, Any],
    info: dict[str, Any] | None = None,
    *,
    kind: str,
    wifi_dbm: float | None = None,
    serial: str | None = None,
    mode: str = "useful",
) -> dict[str, Any]:
    """info (Details) + energy (LastData) + Aliase, dann Filter (useful/full)."""
    combined = {**(info or {}), **(energy or {})}
    if serial:
        combined.setdefault("deviceSn", serial)
    flat = {**flatten_raw(info), **flatten_raw(energy)}
    if kind == "storage":
        curated = _curated_storage(combined)
        packs = int(curated.get("battery_num") or 1)
        for i in range(packs + 1, 5):
            for suffix in ("soc", "temp", "temp_f", "serial_num", "protect_status", "warn_status"):
                flat.pop(f"battery{i}_{suffix}", None)
                curated.pop(f"battery{i}_{suffix}", None)
        for i in range(1, packs + 1):
            flat.pop(f"battery{i}_temp_f", None)
    else:
        curated = _curated_min(combined)
    out = {**flat, **curated}
    if wifi_dbm is not None:
        out["wifi_signal"] = wifi_dbm
    return filter_published_values(out, kind=kind, mode=mode)


def normalize_storage(raw: dict[str, Any], info: dict[str, Any] | None = None) -> dict[str, Any]:
    return merge_device_values(raw, info, kind="storage")


def normalize_min(raw: dict[str, Any], info: dict[str, Any] | None = None) -> dict[str, Any]:
    return merge_device_values(raw, info, kind="min")
