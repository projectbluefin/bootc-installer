"""Unit tests for the pure-Python logic in defaults/network.py.

network.py imports GTK and NetworkManager (NM) at the module level.
We stub out gi.repository before importing so these tests run without
a display or D-Bus connection.
"""

import sys
import types
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ── Stub out gi.repository ────────────────────────────────────────────────────

def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    gi_mod._stubbed = True
    repo_mod = types.ModuleType("gi.repository")

    class _Template:
        def __call__(self, *args, **kwargs):
            return lambda cls: cls

        def Child(self, *args, **kwargs):
            return None

    _template_instance = _Template()

    class _Stub:
        pass

    class _FakeNMClient:
        @staticmethod
        def new():
            return _FakeNMClient()

        def get_devices(self):
            return []

        def connect(self, *args, **kwargs):
            pass

    class _FakeNM:
        Template = _template_instance
        Client = _FakeNMClient
        DeviceType = type("DeviceType", (), {
            "ETHERNET": 1,
            "WIFI": 2,
        })
        DeviceState = type("DeviceState", (), {
            "ACTIVATED": 100,
            "NEED_AUTH": 60,
            "PREPARE": 40,
            "CONFIG": 50,
            "IP_CONFIG": 70,
            "IP_CHECK": 80,
            "SECONDARIES": 90,
            "DISCONNECTED": 30,
            "DEACTIVATING": 110,
            "FAILED": 120,
            "UNKNOWN": 0,
            "UNMANAGED": 10,
            "UNAVAILABLE": 20,
        })
        Device = _Stub
        DeviceWifi = _Stub
        DeviceEthernet = _Stub

    for lib in ("Gtk", "Adw", "GLib", "Gio", "Gdk", "NMA4"):
        stub = types.ModuleType(f"gi.repository.{lib}")
        stub.Template = _template_instance
        stub.Bin = _Stub
        stub.Box = _Stub
        stub.Label = _Stub
        stub.Spinner = _Stub
        stub.ActionRow = _Stub
        stub.PreferencesRow = _Stub
        stub.SwitchRow = _Stub
        stub.Orientation = type("Orientation", (), {"HORIZONTAL": 0, "VERTICAL": 1})
        stub.Align = type("Align", (), {"CENTER": 0, "FILL": 1, "START": 2})
        setattr(repo_mod, lib, stub)
        sys.modules[f"gi.repository.{lib}"] = stub

    repo_mod.NM = _FakeNM
    sys.modules["gi.repository.NM"] = _FakeNM

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod

    # Remove cached bootc_installer modules that were loaded with old stubs.
    for mod_name in list(sys.modules):
        if "bootc_installer" in mod_name and "network" in mod_name:
            del sys.modules[mod_name]


_build_gi_stubs()

from bootc_installer.defaults.network import (  # noqa: E402
    VanillaDefaultNetwork,
    AP_SECURITY_TYPES,
)


# ── AP_SECURITY_TYPES lookup table ───────────────────────────────────────────────

class TestSecurityTypes:
    """The AP_SECURITY_TYPES map controls which WiFi networks display a lock icon."""

    def test_wpa_is_secure(self):
        secure, _ = AP_SECURITY_TYPES["wpa"]
        assert secure is True

    def test_wpa2_is_secure(self):
        secure, _ = AP_SECURITY_TYPES["wpa2"]
        assert secure is True

    def test_sae_wpa3_is_secure(self):
        secure, _ = AP_SECURITY_TYPES["sae"]
        assert secure is True

    def test_wep_is_insecure(self):
        secure, _ = AP_SECURITY_TYPES["wep"]
        assert secure is False

    def test_none_is_insecure(self):
        # "none" uses (None, None) — open network, no explicit security flag
        secure, label = AP_SECURITY_TYPES.get("none", (False, ""))
        assert secure is None  # open network

    def test_all_entries_have_label(self):
        for key, (_, label) in AP_SECURITY_TYPES.items():
            if label is not None:
                assert isinstance(label, str) and label, f"Empty label for {key!r}"


# ── get_finals ────────────────────────────────────────────────────────────────

class TestNetworkGetFinals:
    """Network step contributes nothing to the fisherman recipe."""

    def test_get_finals_returns_empty_dict(self):
        from types import SimpleNamespace
        step = SimpleNamespace()
        result = VanillaDefaultNetwork.get_finals(step)
        assert result == {}
