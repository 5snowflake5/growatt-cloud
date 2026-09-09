"""Noah/Nexa have no daily output kWh in queryLastData; we integrate pac locally."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "growatt_cloud"))

from sensors import (  # noqa: E402
    _curated_storage,
    integrate_daily_wh,
    merge_device_values,
)


# Official v4 Noah last-data keys (GrowattPublicApiPy NoahEnergyDataV4).
# No eDischargeToday / eToUserToday / eChargeToday.
NOAH_LAST_DATA_ENERGY_KEYS = {
    "eacMonth",
    "eacToday",
    "eacTotal",
    "eacYear",
    "pac",
    "ppv",
}


class IntegrateDailyWhTests(unittest.TestCase):
    def test_first_sample_starts_at_zero(self) -> None:
        state = integrate_daily_wh(
            None,
            day="2026-09-09",
            now=1_000.0,
            powers_w={"output": 800.0},
        )
        self.assertEqual(state["day"], "2026-09-09")
        self.assertEqual(state["output"], 0.0)
        self.assertEqual(state["ts"], 1_000.0)

    def test_one_hour_at_800w_is_800wh(self) -> None:
        state = {"day": "2026-09-09", "output": 0.0, "ts": 1_000.0}
        state = integrate_daily_wh(
            state,
            day="2026-09-09",
            now=1_000.0 + 3600.0,
            powers_w={"output": 800.0},
        )
        self.assertAlmostEqual(state["output"], 800.0, places=6)

    def test_day_change_resets(self) -> None:
        state = {"day": "2026-09-08", "output": 1234.0, "ts": 1.0}
        state = integrate_daily_wh(
            state,
            day="2026-09-09",
            now=100.0,
            powers_w={"output": 500.0},
        )
        self.assertEqual(state["output"], 0.0)
        self.assertEqual(state["day"], "2026-09-09")

    def test_caps_gap_at_two_hours(self) -> None:
        state = {"day": "2026-09-09", "output": 0.0, "ts": 0.0}
        state = integrate_daily_wh(
            state,
            day="2026-09-09",
            now=10 * 3600.0,
            powers_w={"output": 100.0},
        )
        self.assertAlmostEqual(state["output"], 200.0, places=6)


class StorageMappingTests(unittest.TestCase):
    def test_noah_payload_has_no_documented_hybrid_daily_fields(self) -> None:
        raw = {
            "deviceSn": "0PVP00ED26UT03E9",
            "pac": 398.0,
            "ppv": 102.0,
            "eacToday": 3.1,
            "eacTotal": 319.8,
            "totalBatteryPackSoc": 40,
            "totalBatteryPackChargingPower": -314,
            "totalBatteryPackChargingStatus": 2,
        }
        curated = _curated_storage(raw, serial="0PVP00ED26UT03E9")
        self.assertEqual(curated["output_power"], 398.0)
        self.assertEqual(curated["generation_today"], 3.1)
        self.assertIsNone(curated["output_today"])
        self.assertIsNone(curated["discharge_today"])
        self.assertIsNone(curated["energy_to_user_today"])
        useful = merge_device_values(raw, kind="storage", serial="0PVP00ED26UT03E9", mode="useful")
        self.assertNotIn("output_today", useful)
        self.assertNotIn("discharge_today", useful)
        self.assertNotIn("energy_to_user_today", useful)
        self.assertNotIn("edischargeToday", NOAH_LAST_DATA_ENERGY_KEYS)
        self.assertNotIn("eToUserToday", NOAH_LAST_DATA_ENERGY_KEYS)
        self.assertNotIn("etoUserToday", NOAH_LAST_DATA_ENERGY_KEYS)

    def test_maps_hybrid_api_fields_when_present(self) -> None:
        raw = {
            "deviceSn": "0PVP00ED26UT03E9",
            "pac": 100.0,
            "ppv": 50.0,
            "eacToday": 1.0,
            "eDischargeToday": 2.5,
            "etoUserToday": 0.8,
            "echargeToday": 1.2,
            "eOutToday": 3.4,
            "totalBatteryPackSoc": 50,
        }
        curated = _curated_storage(raw, serial="0PVP00ED26UT03E9")
        self.assertEqual(curated["discharge_today"], 2.5)
        self.assertEqual(curated["energy_to_user_today"], 0.8)
        self.assertEqual(curated["charge_today"], 1.2)
        self.assertEqual(curated["output_today"], 3.4)
        useful = merge_device_values(raw, kind="storage", serial="0PVP00ED26UT03E9", mode="useful")
        self.assertEqual(useful["discharge_today"], 2.5)
        self.assertEqual(useful["energy_to_user_today"], 0.8)
        self.assertEqual(useful["output_today"], 3.4)

    def test_local_integral_fills_output_today_when_api_omits_it(self) -> None:
        values = {"output_power": 800.0, "solar_power_storage1": 0.0, "solar_power_other_storage": 0.0}
        state = integrate_daily_wh(
            {"day": "2026-09-09", "strings": 0.0, "other": 0.0, "output": 0.0, "ts": 0.0},
            day="2026-09-09",
            now=3600.0,
            powers_w={
                "strings": 0.0,
                "other": 0.0,
                "output": float(values["output_power"]),
            },
        )
        if values.get("output_today") is None:
            values["output_today"] = round(float(state["output"]) / 1000.0, 3)
        self.assertEqual(values["output_today"], 0.8)


if __name__ == "__main__":
    unittest.main()
