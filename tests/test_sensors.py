#!/usr/bin/env python3
"""Unit tests for sensor mapping (run: python3 -m unittest tests.test_sensors)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "growatt_cloud"))

from sensors import (  # noqa: E402
    apply_derived_values,
    filter_published_values,
    merge_device_values,
    split_signed_power,
    to_iso_timestamp,
    _num,
)


class NumTests(unittest.TestCase):
    def test_missing_is_none(self):
        self.assertIsNone(_num({}, "soc"))

    def test_zero_is_zero(self):
        self.assertEqual(_num({"soc": 0}, "soc"), 0.0)


class FilterTests(unittest.TestCase):
    def test_keeps_zero_energy_at_night(self):
        values = merge_device_values(
            {
                "pac": 0,
                "eacToday": 1.25,
                "epv1Today": 0.8,
                "ppv1": 0,
                "vpv1": 0,
                "ipv1": 0,
            },
            kind="min",
            mode="useful",
        )
        self.assertEqual(values.get("energy_today"), 1.25)
        self.assertEqual(values.get("energy_today_input_1"), 0.8)
        self.assertIn("ac_power", values)

    def test_keeps_fault_zero(self):
        values = merge_device_values(
            {"pac": 10, "faultStatus": 0, "allowGridCharging": 0},
            kind="storage",
            mode="useful",
            serial="0PVPTESTSERIAL01",
        )
        self.assertEqual(values.get("fault_status"), 0)
        self.assertEqual(values.get("allow_grid_charging"), "OFF")
        self.assertIn("work_mode_code", values)

    def test_missing_soc_not_zero(self):
        values = merge_device_values({"ppv": 100, "pac": 50}, kind="storage", mode="useful")
        self.assertNotIn("soc", values)


class DerivedTests(unittest.TestCase):
    def test_iso_timestamp(self):
        iso = to_iso_timestamp("2026-09-30 10:15:00", "UTC")
        self.assertTrue(str(iso).startswith("2026-09-30T10:15:00"))

    def test_split_ct(self):
        self.assertEqual(split_signed_power(120), (120.0, 0.0))
        self.assertEqual(split_signed_power(-40), (0.0, 40.0))

    def test_battery_energy(self):
        values = {"soc": 50.0, "battery_num": 2, "ct_power": -30.0, "discharge_power": 200.0}
        apply_derived_values(values, kind="storage", tz_name="UTC", pack_capacity_wh=2048)
        self.assertEqual(values["battery_energy"], 2048.0)
        self.assertEqual(values["grid_export_power"], 30.0)
        self.assertEqual(values["grid_import_power"], 0.0)
        self.assertGreater(values["time_to_empty"], 0)


class NoSerialLeakTests(unittest.TestCase):
    FORBIDDEN = (
        "".join(("0PVP", "00ED", "26UT", "03E9")),
        "".join(("0pvp", "00ed", "26ut", "03e9")),
        "".join(("0HVR", "D0ZR", "247T", "000V")),
        "".join(("0hvr", "d0zr", "247t", "000v")),
        "".join(("BZP4", "NXX1", "8C")),
        "".join(("bzp4", "nxx1", "8c")),
    )

    def test_homeassistant_examples(self):
        base = ROOT / "homeassistant"
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for token in self.FORBIDDEN:
                self.assertNotIn(token, text, msg=f"{path} contains {token}")


if __name__ == "__main__":
    unittest.main()
