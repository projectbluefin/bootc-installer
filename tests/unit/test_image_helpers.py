"""Unit tests for image.py helpers — no GTK required."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Stub out gi.repository so image.py can be imported without a display.
for _mod in ("gi", "gi.repository", "gi.repository.Adw", "gi.repository.Gdk",
             "gi.repository.Gio", "gi.repository.GLib", "gi.repository.Gtk"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Patch Gio.resources_lookup_data so _load_manifest() uses our fixture manifest.
_FIXTURE_MANIFEST = {
    "fallback_flatpaks": ["org.mozilla.firefox"],
    "default_image": "",
    "images": [
        {
            "name": "Aurora",
            "icon": "resource:///org/bootcinstaller/Installer/images/aurora.svg",
            "children": [
                {
                    "name": "Stable",
                    "imgref": "ghcr.io/ublue-os/aurora:stable",
                    "desc": "Stable build",
                },
                {
                    "name": "Aurora DX",
                    "children": [
                        {
                            "name": "Stable",
                            "imgref": "ghcr.io/ublue-os/aurora-dx:stable",
                            "desc": "DX stable",
                        },
                    ],
                },
            ],
        },
        {
            "name": "Bluefin",
            "icon": "resource:///org/bootcinstaller/Installer/images/bluefin.png",
            "children": [
                {
                    "name": "Latest",
                    "imgref": "ghcr.io/ublue-os/bluefin:latest",
                    "icon": "resource:///org/bootcinstaller/Installer/images/bluefin-lts.png",
                },
            ],
        },
        {
            "name": "NoIcon",
            "children": [
                {
                    "name": "Leaf",
                    "imgref": "ghcr.io/example/noicon:latest",
                },
            ],
        },
    ],
}

import json as _json

_mock_gio_data = MagicMock()
_mock_gio_data.get_data.return_value = _json.dumps(_FIXTURE_MANIFEST).encode()
sys.modules["gi.repository"].Gio.resources_lookup_data.return_value = _mock_gio_data
sys.modules["gi.repository"].Gio.ResourceLookupFlags.NONE = 0

from bootc_installer.defaults.image import _find_icon_for_imgref  # noqa: E402


class TestFindIconForImgref(unittest.TestCase):

    def test_direct_child_inherits_parent_icon(self):
        icon = _find_icon_for_imgref("ghcr.io/ublue-os/aurora:stable")
        self.assertEqual(icon, "resource:///org/bootcinstaller/Installer/images/aurora.svg")

    def test_nested_child_inherits_grandparent_icon(self):
        icon = _find_icon_for_imgref("ghcr.io/ublue-os/aurora-dx:stable")
        self.assertEqual(icon, "resource:///org/bootcinstaller/Installer/images/aurora.svg")

    def test_leaf_with_own_icon_overrides_parent(self):
        # Bluefin:latest has its own icon (bluefin-lts.png) which overrides parent's
        icon = _find_icon_for_imgref("ghcr.io/ublue-os/bluefin:latest")
        self.assertEqual(icon, "resource:///org/bootcinstaller/Installer/images/bluefin-lts.png")

    def test_missing_imgref_returns_none(self):
        icon = _find_icon_for_imgref("ghcr.io/does/not/exist:latest")
        self.assertIsNone(icon)

    def test_empty_imgref_returns_none(self):
        icon = _find_icon_for_imgref("")
        self.assertIsNone(icon)

    def test_node_with_no_icon_returns_none(self):
        icon = _find_icon_for_imgref("ghcr.io/example/noicon:latest")
        self.assertIsNone(icon)


class TestDistroInfoDefaultImageIcon(unittest.TestCase):
    """Verify the distro_info pattern used by builder.py."""

    def test_no_default_image_gives_none_icon(self):
        icon = _find_icon_for_imgref("")
        self.assertIsNone(icon)

    def test_default_image_with_icon_resolves(self):
        icon = _find_icon_for_imgref("ghcr.io/ublue-os/aurora:stable")
        self.assertIsNotNone(icon)
        self.assertTrue(icon.startswith("resource://"))


if __name__ == "__main__":
    unittest.main()
