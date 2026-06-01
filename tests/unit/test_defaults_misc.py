import importlib
import os
import sys
import types
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class _Template:
    def __call__(self, *args, **kwargs):
        return lambda cls: cls

    def Child(self, *args, **kwargs):
        return None

    def Callback(self, *args, **kwargs):
        return lambda func: func


@contextmanager
def _import_with_gi_stubs(module_name):
    managed = [
        "gi",
        "gi.repository",
        "gi.repository.Adw",
        "gi.repository.Gio",
        "gi.repository.GLib",
        "gi.repository.GObject",
        "gi.repository.Gdk",
        "gi.repository.Gtk",
        "gi.repository.NM",
        "gi.repository.NMA4",
        module_name,
        "bootc_installer.utils.run_async",
    ]
    saved = {name: sys.modules.get(name) for name in managed}

    for name in managed:
        sys.modules.pop(name, None)

    template = _Template()
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = template
    gtk_mod.Box = object

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = object
    adw_mod.ActionRow = object

    gio_mod = types.ModuleType("gi.repository.Gio")
    gio_mod.Settings = type("Settings", (), {"new": staticmethod(lambda _schema: MagicMock())})

    glib_mod = types.ModuleType("gi.repository.GLib")
    glib_mod.SOURCE_REMOVE = False
    glib_mod.idle_add = lambda *args, **kwargs: 1

    gdk_mod = types.ModuleType("gi.repository.Gdk")
    gdk_mod.Display = type("Display", (), {"get_default": staticmethod(lambda: None)})

    gobject_mod = types.ModuleType("gi.repository.GObject")
    gobject_mod.SignalFlags = type("SignalFlags", (), {"RUN_FIRST": 1})

    nm_mod = types.ModuleType("gi.repository.NM")
    nm_mod.Client = type("Client", (), {"new": staticmethod(lambda: MagicMock())})
    nm_mod.Device = object
    nm_mod.DeviceWifi = object
    nm_mod.DeviceEthernet = object
    nm_mod.AccessPoint = object
    nm_mod.DeviceState = type(
        "DeviceState",
        (),
        {
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
        },
    )
    nm_mod.DeviceType = type("DeviceType", (), {"ETHERNET": 1, "WIFI": 2})

    nma4_mod = types.ModuleType("gi.repository.NMA4")

    for name, module in {
        "Gtk": gtk_mod,
        "Adw": adw_mod,
        "Gio": gio_mod,
        "GLib": glib_mod,
        "GObject": gobject_mod,
        "Gdk": gdk_mod,
        "NM": nm_mod,
        "NMA4": nma4_mod,
    }.items():
        setattr(repo_mod, name, module)
        sys.modules[f"gi.repository.{name}"] = module

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *args, **kwargs: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod

    try:
        yield importlib.import_module(module_name)
    finally:
        for name in managed:
            sys.modules.pop(name, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module


class TestConnCheckShouldShow:
    def test_should_show_when_not_offline(self):
        with _import_with_gi_stubs("bootc_installer.defaults.conn_check") as mod:
            assert mod.BootcDefaultConnCheck.should_show(SimpleNamespace(), {}) is True

    def test_should_hide_for_offline_install(self):
        with _import_with_gi_stubs("bootc_installer.defaults.conn_check") as mod:
            assert mod.BootcDefaultConnCheck.should_show(
                SimpleNamespace(), {"offline_install": True}
            ) is False


class TestVmStepLogic:
    def test_use_vm_tools_sets_flag_and_advances(self):
        with _import_with_gi_stubs("bootc_installer.defaults.vm") as mod:
            fake = SimpleNamespace(use_vm_tools=None, _BootcDefaultVm__window=MagicMock())
            mod.BootcDefaultVm.use_vm_tools_fn(fake, None)
            assert fake.use_vm_tools is True
            fake._BootcDefaultVm__window.next.assert_called_once_with()
            assert mod.BootcDefaultVm.get_finals(fake) == {"vm": {"use-vm-tools": True}}

    def test_skip_vm_tools_sets_flag_and_advances(self):
        with _import_with_gi_stubs("bootc_installer.defaults.vm") as mod:
            fake = SimpleNamespace(use_vm_tools=None, _BootcDefaultVm__window=MagicMock())
            mod.BootcDefaultVm.skip_vm_tools_fn(fake, None)
            assert fake.use_vm_tools is False
            fake._BootcDefaultVm__window.next.assert_called_once_with()


class TestNvidiaStepLogic:
    def test_open_drivers_sets_false_and_advances(self):
        with _import_with_gi_stubs("bootc_installer.defaults.nvidia") as mod:
            fake = SimpleNamespace(use_proprietary=None, _BootcDefaultNvidia__window=MagicMock())
            mod.BootcDefaultNvidia.use_open_drivers(fake, None)
            assert fake.use_proprietary is False
            fake._BootcDefaultNvidia__window.next.assert_called_once_with()
            assert mod.BootcDefaultNvidia.get_finals(fake) == {
                "nvidia": {"use-proprietary": False}
            }

    def test_proprietary_drivers_sets_true_and_advances(self):
        with _import_with_gi_stubs("bootc_installer.defaults.nvidia") as mod:
            fake = SimpleNamespace(use_proprietary=None, _BootcDefaultNvidia__window=MagicMock())
            mod.BootcDefaultNvidia.use_proprietary_drivers(fake, None)
            assert fake.use_proprietary is True
            fake._BootcDefaultNvidia__window.next.assert_called_once_with()


class TestThemeStepLogic:
    def test_set_theme_dark_updates_gsettings(self):
        with _import_with_gi_stubs("bootc_installer.defaults.theme") as mod:
            settings = MagicMock()
            mod.Gio.Settings.new = MagicMock(return_value=settings)
            mod.BootcDefaultTheme._BootcDefaultTheme__set_theme(SimpleNamespace(), None, "dark")

            assert [call.args for call in settings.set_string.call_args_list] == [
                ("color-scheme", "prefer-dark"),
                ("gtk-theme", "Adwaita-dark"),
            ]

    def test_set_theme_light_updates_gsettings(self):
        with _import_with_gi_stubs("bootc_installer.defaults.theme") as mod:
            settings = MagicMock()
            mod.Gio.Settings.new = MagicMock(return_value=settings)
            mod.BootcDefaultTheme._BootcDefaultTheme__set_theme(SimpleNamespace(), None, "light")

            assert [call.args for call in settings.set_string.call_args_list] == [
                ("color-scheme", "default"),
                ("gtk-theme", "Adwaita"),
            ]


class TestNetworkDeviceStatus:
    def test_device_status_connected_state_reports_speed_ready_status(self):
        with _import_with_gi_stubs("bootc_installer.defaults.network") as mod:
            conn = SimpleNamespace(get_state=lambda: mod.NM.DeviceState.ACTIVATED)
            status, connected = mod.BootcDefaultNetwork._BootcDefaultNetwork__device_status(
                SimpleNamespace(), conn
            )
            assert status == "Connected"
            assert connected is True

    def test_device_status_need_auth_is_not_connected(self):
        with _import_with_gi_stubs("bootc_installer.defaults.network") as mod:
            conn = SimpleNamespace(get_state=lambda: mod.NM.DeviceState.NEED_AUTH)
            status, connected = mod.BootcDefaultNetwork._BootcDefaultNetwork__device_status(
                SimpleNamespace(), conn
            )
            assert status == "Authentication required"
            assert connected is False

    def test_device_status_connecting_states_map_to_connecting(self):
        with _import_with_gi_stubs("bootc_installer.defaults.network") as mod:
            for state in (
                mod.NM.DeviceState.PREPARE,
                mod.NM.DeviceState.CONFIG,
                mod.NM.DeviceState.IP_CONFIG,
                mod.NM.DeviceState.IP_CHECK,
                mod.NM.DeviceState.SECONDARIES,
            ):
                conn = SimpleNamespace(get_state=lambda state=state: state)
                status, connected = mod.BootcDefaultNetwork._BootcDefaultNetwork__device_status(
                    SimpleNamespace(), conn
                )
                assert status == "Connecting"
                assert connected is False
