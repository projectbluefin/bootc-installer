"""Unit tests for core/locale.py — Locale data class."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bootc_installer.core.locale import Locale


class TestLocale(unittest.TestCase):
    def _make(self, locales="en_US.UTF-8", region="America", location="New_York"):
        return Locale(locales, region, location)

    # --- attribute storage ---

    def test_stores_locales(self):
        loc = self._make(locales="fr_FR.UTF-8")
        self.assertEqual(loc.locales, "fr_FR.UTF-8")

    def test_stores_region(self):
        loc = self._make(region="Europe")
        self.assertEqual(loc.region, "Europe")

    def test_stores_location(self):
        loc = self._make(location="Paris")
        self.assertEqual(loc.location, "Paris")

    def test_accepts_list_for_locales(self):
        loc = Locale(["en_US.UTF-8", "en_GB.UTF-8"], "America", "New_York")
        self.assertEqual(loc.locales, ["en_US.UTF-8", "en_GB.UTF-8"])

    def test_accepts_none_values(self):
        loc = Locale(None, None, None)
        self.assertIsNone(loc.locales)
        self.assertIsNone(loc.region)
        self.assertIsNone(loc.location)

    # --- __str__ ---

    def test_str_contains_locales(self):
        loc = self._make(locales="de_DE.UTF-8")
        self.assertIn("de_DE.UTF-8", str(loc))

    def test_str_contains_region(self):
        loc = self._make(region="Europe")
        self.assertIn("Europe", str(loc))

    def test_str_contains_location(self):
        loc = self._make(location="Berlin")
        self.assertIn("Berlin", str(loc))

    def test_str_format(self):
        loc = Locale("en_US.UTF-8", "America", "New_York")
        self.assertEqual(str(loc), "<Locale: en_US.UTF-8 America New_York>")

    def test_str_with_list_locales(self):
        loc = Locale(["en_US.UTF-8", "en_GB.UTF-8"], "America", "New_York")
        result = str(loc)
        self.assertTrue(result.startswith("<Locale:"))
        self.assertIn("America", result)

    # --- __repr__ ---

    def test_repr_equals_str(self):
        loc = self._make()
        self.assertEqual(repr(loc), str(loc))

    def test_repr_format(self):
        loc = Locale("ja_JP.UTF-8", "Asia", "Tokyo")
        self.assertEqual(repr(loc), "<Locale: ja_JP.UTF-8 Asia Tokyo>")

    # --- identity / equality ---

    def test_two_equal_locales_not_same_object(self):
        a = Locale("en_US.UTF-8", "America", "New_York")
        b = Locale("en_US.UTF-8", "America", "New_York")
        self.assertIsNot(a, b)
        # Default object equality — they are distinct instances
        self.assertNotEqual(a, b)

    def test_same_object_is_same(self):
        loc = self._make()
        self.assertIs(loc, loc)


if __name__ == "__main__":
    unittest.main()
