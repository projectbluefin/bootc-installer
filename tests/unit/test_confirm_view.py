"""Unit tests for views/confirm.py pure logic.

GTK is fully stubbed so BootcChoiceEntry / BootcConfirm can be imported
without a display.  BootcChoiceEntry is replaced with a MagicMock factory
after import so process_keyboards() and update() can execute.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock


def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    class _Template:
        def __call__(self, *args, **kwargs):
            return lambda cls: cls

        def Child(self, *args, **kwargs):
            return MagicMock()

    class _StubBase:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()
    gtk_mod.Box = _StubBase

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = _StubBase
    adw_mod.ActionRow = _StubBase
    adw_mod.ExpanderRow = _StubBase

    gobject_mod = types.ModuleType("gi.repository.GObject")
    gobject_mod.Property = lambda *a, **kw: (lambda f: property(f))
    gobject_mod.SignalFlags = types.SimpleNamespace(RUN_FIRST=0)

    for name, mod in [
        ("Gtk", gtk_mod),
        ("Adw", adw_mod),
        ("GObject", gobject_mod),
    ]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


_build_gi_stubs()

# Stub for core.system — NOT installed at module level to avoid contaminating
# test_system.py which imports the real bootc_installer.core.system.
# Tests that call update() install it via patch.dict in setUp().
_core_system_stub = types.ModuleType("bootc_installer.core.system")


class _Systeminfo:
    @staticmethod
    def gpu_display_string():
        return None  # No GPU — keeps tests deterministic.

    @staticmethod
    def gpu_icon_name():
        return "gpu-symbolic"


_core_system_stub.Systeminfo = _Systeminfo

# confirm.py only imports gi.repository at module load time (core.system is
# imported lazily inside update()).  So we can import it directly here.
import bootc_installer.views.confirm as confirm_mod  # noqa: E402

# Replace GTK-widget factories with simple MagicMock factories so
# process_keyboards() and update() can build active_widgets without GTK.
confirm_mod.BootcChoiceEntry = lambda title, subtitle, icon, **kw: MagicMock()
confirm_mod.BootcChoiceExpanderEntry = lambda title, subtitle, icon, **kw: MagicMock()


class TestProcessKeyboards(unittest.TestCase):
    def _make_obj(self):
        obj = confirm_mod.BootcConfirm.__new__(confirm_mod.BootcConfirm)
        obj.active_widgets = []
        return obj

    def test_single_keyboard_no_variant_adds_one_widget(self):
        obj = self._make_obj()
        obj.process_keyboards([{"layout": "us", "variant": ""}])
        self.assertEqual(len(obj.active_widgets), 1)

    def test_single_keyboard_with_variant_combines_layout_and_variant(self):
        obj = self._make_obj()
        obj.process_keyboards([{"layout": "us", "variant": "intl"}])
        self.assertEqual(len(obj.active_widgets), 1)

    def test_multiple_keyboards_each_add_a_widget(self):
        obj = self._make_obj()
        obj.process_keyboards([
            {"layout": "us", "variant": ""},
            {"layout": "fr", "variant": "azerty"},
        ])
        self.assertEqual(len(obj.active_widgets), 2)

    def test_empty_keyboards_list_adds_nothing(self):
        obj = self._make_obj()
        obj.process_keyboards([])
        self.assertEqual(len(obj.active_widgets), 0)


class TestConfirmUpdate(unittest.TestCase):
    def setUp(self):
        # Install core.system stub only for the duration of this test so
        # that update()'s lazy `from bootc_installer.core.system import Systeminfo`
        # gets our no-GPU stub and not the real module.
        self._orig_core_system = sys.modules.get("bootc_installer.core.system")
        sys.modules["bootc_installer.core.system"] = _core_system_stub

    def tearDown(self):
        if self._orig_core_system is None:
            sys.modules.pop("bootc_installer.core.system", None)
        else:
            sys.modules["bootc_installer.core.system"] = self._orig_core_system

    def _make_obj(self):
        obj = confirm_mod.BootcConfirm.__new__(confirm_mod.BootcConfirm)
        obj.active_widgets = []
        obj.group_changes = MagicMock()
        obj.btn_confirm = MagicMock()
        obj.page_header = MagicMock()
        return obj

    def test_update_with_language_adds_widget(self):
        obj = self._make_obj()
        obj.update([{"language": "en_US.UTF-8"}])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_with_timezone_adds_widget(self):
        obj = self._make_obj()
        obj.update([{"timezone": {"region": "America", "zone": "New_York"}}])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_with_users_adds_widget(self):
        obj = self._make_obj()
        obj.update([{"users": {"username": "jorge", "fullname": "Jorge Castro"}}])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_with_disk_auto_adds_widget(self):
        obj = self._make_obj()
        obj.update([{"disk": {"auto": {"disk": "/dev/sda", "pretty_size": "100 GB"}}}])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_with_encryption_none_adds_widget(self):
        obj = self._make_obj()
        obj.update([{"encryption": {"type": "none"}}])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_with_encryption_tpm2_adds_widget(self):
        obj = self._make_obj()
        obj.update([{"encryption": {"type": "tpm2-luks"}}])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_with_hostname_adds_widget(self):
        obj = self._make_obj()
        obj.update([{"hostname": "my-machine"}])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_with_selected_image_adds_widget(self):
        obj = self._make_obj()
        obj.update([{
            "selected_image": "ghcr.io/projectbluefin/bluefin:latest",
            "pretty_name": "Bluefin",
        }])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_with_custom_image_adds_widget(self):
        obj = self._make_obj()
        obj.update([{"custom_image": "ghcr.io/myorg/myimage:latest"}])
        self.assertGreater(len(obj.active_widgets), 0)

    def test_update_sets_btn_confirm_label(self):
        obj = self._make_obj()
        obj.update([])
        obj.btn_confirm.set_label.assert_called_once()

    def test_update_with_pt_br_language_uses_senna_quote(self):
        obj = self._make_obj()
        obj.update([{"language": "pt_BR.UTF-8"}])
        subtitle = obj.page_header.subtitle
        self.assertIn("Senna", subtitle)

    def test_update_with_other_language_uses_zavala_quote(self):
        obj = self._make_obj()
        obj.update([{"language": "en_US.UTF-8"}])
        subtitle = obj.page_header.subtitle
        self.assertIn("Zavala", subtitle)

    def test_update_resets_active_widgets_on_repeat_call(self):
        obj = self._make_obj()
        obj.update([{"hostname": "host1"}])
        count_first = len(obj.active_widgets)
        obj.update([{"hostname": "host2"}])
        # Second call resets list; should have same widget count.
        self.assertEqual(len(obj.active_widgets), count_first)


if __name__ == "__main__":
    unittest.main()
