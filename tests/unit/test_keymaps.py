"""Unit tests for keymaps.py — XKB keymap enumeration.

Requires mocking gi.repository.GnomeDesktop.XkbInfo since
GnomeDesktop is not available in CI without a display.
"""

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock


def _build_keymap_stubs():
    """Install gi.repository stubs sufficient for keymaps.py module import."""
    sys.modules.pop("gi", None)
    sys.modules.pop("gi.repository", None)
    sys.modules.pop("gi.repository.GnomeDesktop", None)

    gi = types.ModuleType("gi")
    gi.require_version = lambda *args, **kwargs: None

    repo = types.ModuleType("gi.repository")
    gnome_desktop = types.ModuleType("GnomeDesktop")

    class XkbInfo:
        """Mock implementation — tests inject a callable via _xkb_info_factory."""
        def __init__(self):
            factory = getattr(sys.modules[__name__], "_xkb_info_factory", None)
            if factory:
                self._delegate = factory()
            else:
                self._delegate = MagicMock()

        def get_all_layouts(self):
            return self._delegate.get_all_layouts()

        def get_layout_info(self, layout):
            return self._delegate.get_layout_info(layout)

    gnome_desktop.XkbInfo = XkbInfo
    repo.GnomeDesktop = gnome_desktop
    gi.repository = repo

    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repo
    sys.modules["gi.repository.GnomeDesktop"] = gnome_desktop


def _make_xkb_mock(layouts_info):
    """Build a mock XkbInfo from a list of (layout, display_name, short_name, xkb_layout, xkb_variant)."""
    mock = MagicMock()
    mock.get_all_layouts.return_value = [li[0] for li in layouts_info]

    layout_map = {}
    for layout, display_name, short_name, xkb_layout, xkb_variant in layouts_info:
        # get_layout_info returns a tuple: index-0 is unused, then display_name, short_name, xkb_layout, xkb_variant
        layout_map[layout] = (None, display_name, short_name, xkb_layout, xkb_variant)

    mock.get_layout_info.side_effect = lambda layout: layout_map[layout]
    return mock


class TestKeyMaps(unittest.TestCase):
    """Unit tests for bootc_installer.core.keymaps.KeyMaps."""

    @classmethod
    def setUpClass(cls):
        _build_keymap_stubs()
        import bootc_installer.core.keymaps as mod
        cls.mod = importlib.reload(mod)

    def setUp(self):
        # Reset the factory so each test controls its own mock data.
        globals()["_xkb_info_factory"] = None

    def _set_factory(self, factory):
        globals()["_xkb_info_factory"] = factory

    def test_list_all_returns_expected_structure(self):
        """list_all returns a dict keyed by country, each with layout sub-dicts."""
        mock = _make_xkb_mock([
            ("us", "United States", "US", "us", ""),
            ("de", "Germany", "DE", "de", ""),
            ("fr", "France", "FR", "fr", ""),
        ])
        self._set_factory(lambda: mock)

        km = self.mod.KeyMaps()
        result = km.list_all

        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 3)
        for country, layouts in result.items():
            self.assertIsInstance(layouts, dict)
            for layout_name, info in layouts.items():
                self.assertIn("display_name", info)
                self.assertIn("short_name", info)
                self.assertIn("xkb_layout", info)
                self.assertIn("xkb_variant", info)

    def test_layouts_grouped_by_country(self):
        """Multiple layouts from the same country group together."""
        mock = _make_xkb_mock([
            ("us", "United States", "US", "us", ""),
            ("us_intl", "United States (Intl)", "US", "us", "intl"),
            ("de", "Germany", "DE", "de", ""),
        ])
        self._set_factory(lambda: mock)

        km = self.mod.KeyMaps()
        result = km.list_all

        self.assertIn("United", result)
        self.assertEqual(len(result["United"]), 2)
        self.assertIn("us", result["United"])
        self.assertIn("us_intl", result["United"])

    def test_country_key_is_first_word_of_display_name(self):
        """Country grouping uses the first space-delimited word of display_name."""
        mock = _make_xkb_mock([
            ("fr", "France", "FR", "fr", ""),
            ("br", "Brazil", "BR", "br", ""),
        ])
        self._set_factory(lambda: mock)

        km = self.mod.KeyMaps()
        result = km.list_all

        self.assertIn("France", result)
        self.assertIn("Brazil", result)

    def test_cleanup_rule_A_is_filtered_out(self):
        """Layouts whose country is 'A' are excluded per cleanup_rules."""
        mock = _make_xkb_mock([
            ("us", "United States", "US", "us", ""),
            ("ad", "Andorra", "AD", "ad", ""),   # country = "Andorra" — starts with 'A' but not 'A' alone
            ("ar_foo", "A", "AR", "ar", "foo"),   # country = "A" — should be filtered
        ])
        self._set_factory(lambda: mock)

        km = self.mod.KeyMaps()
        result = km.list_all

        self.assertIn("United", result)
        self.assertIn("Andorra", result)
        # "A" country should be filtered out
        self.assertNotIn("A", result)

    def test_results_sorted_alphabetically_by_country(self):
        """Countries are sorted alphabetically in the returned dict."""
        mock = _make_xkb_mock([
            ("de", "Germany", "DE", "de", ""),
            ("us", "United States", "US", "us", ""),
            ("fr", "France", "FR", "fr", ""),
        ])
        self._set_factory(lambda: mock)

        km = self.mod.KeyMaps()
        result = km.list_all

        countries = list(result.keys())
        self.assertEqual(countries, sorted(countries))

    def test_xkb_variant_is_empty_string_when_no_variant(self):
        """Layouts with no variant have xkb_variant set to empty string."""
        mock = _make_xkb_mock([
            ("us", "United States", "US", "us", ""),
        ])
        self._set_factory(lambda: mock)

        km = self.mod.KeyMaps()
        result = km.list_all

        self.assertEqual(result["United"]["us"]["xkb_variant"], "")

    def test_xkb_variant_preserved_for_variant_layouts(self):
        """Layouts with variants preserve the variant string."""
        mock = _make_xkb_mock([
            ("us", "United States", "US", "us", ""),
            ("us_dvorak", "United States (Dvorak)", "US", "us", "dvorak"),
        ])
        self._set_factory(lambda: mock)

        km = self.mod.KeyMaps()
        result = km.list_all

        self.assertEqual(result["United"]["us_dvorak"]["xkb_variant"], "dvorak")


if __name__ == "__main__":
    unittest.main()
