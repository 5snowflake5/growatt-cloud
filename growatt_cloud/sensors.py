"""Rohdaten Growatt v4 → flache Sensor-Maps (Keys = MQTT object_id)."""

from __future__ import annotations

from typing import Any

WORK_MODE = {0: "load_first", 1: "battery_first", 2: "smart"}
CHARGE_STATUS = {0: "idle", 1: "charging", 2: "discharging"}


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


def detect_storage_label(raw: dict[str, Any]) -> str:
    blob = " ".join(
        str(x)
        for x in (
            raw.get("model"),
            raw.get("modelName"),
            raw.get("model_name"),
            raw.get("alias"),
            raw.get("deviceType"),
            raw.get("device_type"),
        )
        if x
    ).lower()
    return "Nexa" if "nexa" in blob else "Noah"


def normalize_storage(raw: dict[str, Any]) -> dict[str, Any]:
    """Noah/Nexa – Parität zu noah-mqtt + sinnvolle v4-Extras."""
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

    out: dict[str, Any] = {
        "family": label.lower(),
        "label": label,
        "soc": _num(raw, "totalBatteryPackSoc", "total_battery_pack_soc"),
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
        "charge_soc_limit": _num(raw, "chargeSocLimit", "charge_soc_limit"),
        "discharge_soc_limit": _num(raw, "dischargeSocLimit", "discharge_soc_limit"),
        "battery_soh": _num(raw, "batterySoh", "battery_soh"),
        "battery_cycles": _num(raw, "batteryCycles", "battery_cycles"),
        "work_mode": WORK_MODE.get(work, str(work)),
        "work_mode_code": work,
        "charge_status": CHARGE_STATUS.get(status, str(status)),
        "status_code": _int(raw, "status"),
        "heating": "ON" if heating else "OFF",
        "connectivity": "ON",
        "time": _pick(raw, "timeStr", "time_str", "time"),
    }

    for i in range(1, 5):
        soc = _num(raw, f"battery{i}Soc", f"battery{i}_soc", default=None)
        temp = _num(raw, f"battery{i}Temp", f"battery{i}_temp", default=None)
        if i <= packs or soc is not None:
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


def normalize_min(raw: dict[str, Any]) -> dict[str, Any]:
    """MIN/TLX-Wechselrichter – praxisnahe Menge (~Growatt-Server-Kernfelder)."""
    status = _pick(raw, "statusText", "status_text", "status")
    return {
        "family": "min",
        "label": "Wechselrichter",
        "ac_power": _num(raw, "pac"),
        "ac_power_r": _num(raw, "pac1", "pacr"),
        "energy_today": _num(raw, "eacToday", "eac_today", "powerToday", "power_today"),
        "energy_total": _num(raw, "eacTotal", "eac_total", "powerTotal", "power_total"),
        "energy_today_input_1": _num(raw, "epv1Today", "epv1_today"),
        "energy_today_input_2": _num(raw, "epv2Today", "epv2_today"),
        "energy_today_input_3": _num(raw, "epv3Today", "epv3_today"),
        "energy_today_input_4": _num(raw, "epv4Today", "epv4_today"),
        "energy_total_input_1": _num(raw, "epv1Total", "epv1_total"),
        "energy_total_input_2": _num(raw, "epv2Total", "epv2_total"),
        "energy_total_pv": _num(raw, "epvTotal", "epv_total"),
        "ppv": _num(raw, "ppv"),
        "ppv1": _num(raw, "ppv1"),
        "ppv2": _num(raw, "ppv2"),
        "ppv3": _num(raw, "ppv3"),
        "ppv4": _num(raw, "ppv4"),
        "ipv1": _num(raw, "ipv1"),
        "ipv2": _num(raw, "ipv2"),
        "vpv1": _num(raw, "vpv1"),
        "vpv2": _num(raw, "vpv2"),
        "vac1": _num(raw, "vac1", "vacr"),
        "iac1": _num(raw, "iac1", "iacr"),
        "fac": _num(raw, "fac"),
        "temperature": _num(raw, "temp1", "temperature"),
        "temperature_2": _num(raw, "temp2"),
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
        "connectivity": "OFF" if raw.get("lost") in (True, 1, "1", "true") else "ON",
        "time": _pick(raw, "time", "timeStr", "time_str"),
    }
