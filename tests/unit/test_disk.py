"""Unit tests for defaults/disk.py pure logic.

GTK widgets are stubbed at import time, and widget subclasses are instantiated
with __new__ plus manual attribute injection so no display is required.
"""

import copy
import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock


class _StubWidget:
    def __init__(self, *args, **kwargs):
        pass

    def get_text(self):
        return ""

    def set_text(self, value):
        pass

    def get_active(self):
        return False

    def set_visible(self, value):
        pass

    def get_visible(self):
        return False


class _Template:
    def __call__(self, *args, **kwargs):
        return lambda cls: cls

    def Child(self, *args, **kwargs):
        return None


def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()
    gtk_mod.Box = _StubWidget
    gtk_mod.CheckButton = _StubWidget
    gtk_mod.Image = types.SimpleNamespace(new_from_icon_name=lambda *a, **kw: _StubWidget())
    gtk_mod.DropDown = types.SimpleNamespace(new_from_strings=lambda *a, **kw: _StubWidget())
    gtk_mod.StringList = types.SimpleNamespace(new=lambda *a, **kw: [])
    gtk_mod.Align = types.SimpleNamespace(CENTER=0)

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = _StubWidget
    adw_mod.ActionRow = _StubWidget
    adw_mod.Window = _StubWidget
    adw_mod.EntryRow = _StubWidget
    adw_mod.ComboRow = _StubWidget
    adw_mod.SwitchRow = _StubWidget
    adw_mod.PreferencesGroup = _StubWidget
    adw_mod.PreferencesPage = _StubWidget
    adw_mod.ExpanderRow = _StubWidget
    adw_mod.Toast = types.SimpleNamespace(new=lambda *a, **kw: MagicMock())

    gobject_mod = types.ModuleType("gi.repository.GObject")
    gobject_mod.Property = lambda *a, **kw: (lambda f: property(f))
    gobject_mod.SignalFlags = types.SimpleNamespace(RUN_FIRST=0)

    gio_mod = types.ModuleType("gi.repository.Gio")
    glib_mod = MagicMock()
    gdk_mod = MagicMock()

    for name, mod in [
        ("Gtk", gtk_mod),
        ("Adw", adw_mod),
        ("GObject", gobject_mod),
        ("Gio", gio_mod),
        ("GLib", glib_mod),
        ("Gdk", gdk_mod),
    ]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _build_core_stubs():
    disks_mod = types.ModuleType("bootc_installer.core.disks")

    class _DisksManager:
        def all_disks(self, include_removable=False):
            return []

    class _Diskutils:
        @staticmethod
        def pretty_size(size):
            return f"{size} B"

    class _Partition:
        def __init__(self, size=0, partition="/dev/fake1", fs_type="", pretty_size=""):
            self.size = size
            self.partition = partition
            self.fs_type = fs_type
            self.pretty_size = pretty_size or str(size)

        def __lt__(self, other):
            return self.partition < other.partition

    disks_mod.DisksManager = _DisksManager
    disks_mod.Diskutils = _Diskutils
    disks_mod.Partition = _Partition
    sys.modules["bootc_installer.core.disks"] = disks_mod

    system_mod = types.ModuleType("bootc_installer.core.system")

    class _Systeminfo:
        @staticmethod
        def is_uefi():
            return True

        @staticmethod
        def generate_hostname():
            return "generated-host"

    system_mod.Systeminfo = _Systeminfo
    sys.modules["bootc_installer.core.system"] = system_mod


def _import_disk_fresh():
    managed_modules = [
        "gi",
        "gi.repository",
        "gi.repository.Gtk",
        "gi.repository.Adw",
        "gi.repository.GObject",
        "gi.repository.Gio",
        "gi.repository.GLib",
        "gi.repository.Gdk",
        "bootc_installer.core.disks",
        "bootc_installer.core.system",
    ]
    originals = {name: sys.modules.get(name) for name in managed_modules}

    _build_gi_stubs()
    _build_core_stubs()
    sys.modules.pop("bootc_installer.defaults.disk", None)
    import bootc_installer.defaults as defaults_pkg
    defaults_pkg.__dict__.pop("disk", None)

    try:
        return importlib.import_module("bootc_installer.defaults.disk")
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class _FakeStyleContext:
    def __init__(self, initial_classes=None):
        self.classes = set(initial_classes or [])

    def has_class(self, name):
        return name in self.classes

    def add_class(self, name):
        self.classes.add(name)

    def remove_class(self, name):
        self.classes.discard(name)


class _FakeExpandRow:
    def __init__(self, initial_classes=None):
        self._style = _FakeStyleContext(initial_classes)

    def get_style_context(self):
        return self._style


class _FakeErrorRow:
    def __init__(self):
        self.visible = None
        self.description = None

    def set_visible(self, value):
        self.visible = value

    def set_description(self, value):
        self.description = value


class TestBootcDefaultDiskShouldShow(unittest.TestCase):
    def setUp(self):
        self.mod = _import_disk_fresh()

    def test_should_show_uses_disk_count_threshold(self):
        obj = self.mod.BootcDefaultDisk.__new__(self.mod.BootcDefaultDisk)
        cases = [
            ({"disk_count": 0}, False),
            ({"disk_count": 1}, False),
            ({"disk_count": 2}, True),
            ({}, True),
        ]

        for context, expected in cases:
            with self.subTest(context=context):
                self.assertIs(obj.should_show(context), expected)


class TestBootcDefaultDiskGetFinals(unittest.TestCase):
    def setUp(self):
        self.mod = _import_disk_fresh()

    def _make_obj(
        self,
        *,
        partition_recipe=None,
        filesystem="xfs",
        hostname="myhost",
        use_virtual_disk=False,
        var_disk_active=False,
        var_disk_selected=None,
        keep_visible=False,
        keep_active=False,
        loop_device=None,
    ):
        obj = self.mod.BootcDefaultDisk.__new__(self.mod.BootcDefaultDisk)
        setattr(obj, "_BootcDefaultDisk__partition_recipe", partition_recipe)
        setattr(obj, "_BootcDefaultDisk__use_virtual_disk", use_virtual_disk)
        setattr(obj, "_BootcDefaultDisk__var_disk_selected", var_disk_selected)
        setattr(obj, "_BootcDefaultDisk__get_selected_filesystem", lambda: filesystem)
        if loop_device is not None:
            setattr(obj, "_BootcDefaultDisk__loop_device", loop_device)

        obj.hostname_entry = MagicMock()
        obj.hostname_entry.get_text.return_value = hostname
        obj.var_disk_switch = MagicMock()
        obj.var_disk_switch.get_active.return_value = var_disk_active
        obj.group_var_disk_existing = MagicMock()
        obj.group_var_disk_existing.get_visible.return_value = keep_visible
        obj.var_disk_keep_switch = MagicMock()
        obj.var_disk_keep_switch.get_active.return_value = keep_active
        return obj

    def test_get_finals_sets_xfs_filesystem_and_btrfs_flag_false(self):
        obj = self._make_obj(partition_recipe={"auto": {"disk": "/dev/sda", "size": 100}})

        result = obj.get_finals()

        self.assertEqual(result["disk"]["filesystem"], "xfs")
        self.assertFalse(result["disk"]["btrfsSubvolumes"])
        self.assertEqual(result["hostname"], "myhost")

    def test_get_finals_sets_btrfs_subvolumes_true_for_btrfs(self):
        obj = self._make_obj(
            partition_recipe={"auto": {"disk": "/dev/nvme0n1", "size": 500}},
            filesystem="btrfs",
        )

        result = obj.get_finals()

        self.assertEqual(result["disk"]["filesystem"], "btrfs")
        self.assertTrue(result["disk"]["btrfsSubvolumes"])

    def test_get_finals_returns_empty_disk_when_partition_recipe_missing(self):
        obj = self._make_obj(partition_recipe=None)

        result = obj.get_finals()

        self.assertEqual(result["disk"], {})

    def test_get_finals_returns_empty_string_for_blank_hostname(self):
        obj = self._make_obj(hostname="   ")

        result = obj.get_finals()

        self.assertEqual(result["hostname"], "")

    def test_get_finals_includes_var_disk_selection(self):
        var_disk = types.SimpleNamespace(disk="/dev/sdb")
        obj = self._make_obj(
            partition_recipe={"auto": {"disk": "/dev/sda", "size": 100}},
            var_disk_active=True,
            var_disk_selected=var_disk,
            keep_visible=True,
            keep_active=True,
        )

        result = obj.get_finals()

        self.assertEqual(
            result["var_disk"],
            {"disk": "/dev/sdb", "keep_existing": True},
        )

    def test_get_finals_disables_var_disk_keep_existing_when_row_hidden(self):
        var_disk = types.SimpleNamespace(disk="/dev/sdb")
        obj = self._make_obj(
            partition_recipe={"auto": {"disk": "/dev/sda", "size": 100}},
            var_disk_active=True,
            var_disk_selected=var_disk,
            keep_visible=False,
            keep_active=True,
        )

        result = obj.get_finals()

        self.assertFalse(result["var_disk"]["keep_existing"])

    def test_get_finals_includes_virtual_disk_details(self):
        obj = self._make_obj(
            partition_recipe={"auto": {"disk": "/dev/loop0", "size": 0}},
            use_virtual_disk=True,
            loop_device="/dev/loop0",
        )

        result = obj.get_finals()

        self.assertEqual(result["virtual_disk_img"], self.mod.BootcDefaultDisk._VIRTUAL_DISK_IMG)
        self.assertEqual(result["virtual_disk_loop"], "/dev/loop0")


class TestBootcDefaultDiskAutoPartitionRecipe(unittest.TestCase):
    def setUp(self):
        self.mod = _import_disk_fresh()

    def test_set_auto_partition_recipe_populates_expected_keys(self):
        obj = self.mod.BootcDefaultDisk.__new__(self.mod.BootcDefaultDisk)
        update_next_button = MagicMock()
        setattr(obj, "_BootcDefaultDisk__update_next_button", update_next_button)
        disk = types.SimpleNamespace(disk="/dev/nvme0n1", size=500, pretty_size="500 GB")

        obj._set_auto_partition_recipe(disk)

        self.assertEqual(
            getattr(obj, "_BootcDefaultDisk__partition_recipe"),
            {
                "auto": {
                    "disk": "/dev/nvme0n1",
                    "pretty_size": "500 GB",
                    "size": 500,
                    "vgs_to_remove": [],
                    "pvs_to_remove": [],
                }
            },
        )
        update_next_button.assert_called_once_with()


class TestBootcDefaultDiskAutoSelectSingleDisk(unittest.TestCase):
    def setUp(self):
        self.mod = _import_disk_fresh()

    def _make_obj(self, all_disks_side_effect):
        obj = self.mod.BootcDefaultDisk.__new__(self.mod.BootcDefaultDisk)
        setattr(obj, "_BootcDefaultDisk__disks", MagicMock())
        getattr(obj, "_BootcDefaultDisk__disks").all_disks.side_effect = all_disks_side_effect
        setattr(obj, "_BootcDefaultDisk__selected_disks", [])
        setattr(obj, "_BootcDefaultDisk__selected_disks_sum", 0)
        setattr(obj, "_BootcDefaultDisk__registry_disks", [])
        setattr(obj, "_BootcDefaultDisk__use_virtual_disk", True)
        setattr(obj, "_BootcDefaultDisk__update_action_buttons", MagicMock())
        setattr(obj, "_BootcDefaultDisk__update_next_button", MagicMock())
        return obj

    def test_auto_select_single_disk_returns_false_when_no_disks_exist(self):
        obj = self._make_obj([[], []])

        result = obj.auto_select_single_disk()

        self.assertFalse(result)

    def test_auto_select_single_disk_returns_false_when_multiple_disks_exist(self):
        disk1 = types.SimpleNamespace(disk="/dev/sda", size=100)
        disk2 = types.SimpleNamespace(disk="/dev/sdb", size=200)
        obj = self._make_obj([[disk1, disk2]])

        result = obj.auto_select_single_disk()

        self.assertFalse(result)

    def test_auto_select_single_disk_selects_the_only_installable_disk(self):
        disk = types.SimpleNamespace(disk="/dev/nvme0n1", size=500, pretty_size="500 GB")
        obj = self._make_obj([[disk]])

        result = obj.auto_select_single_disk()

        self.assertTrue(result)
        self.assertEqual(getattr(obj, "_BootcDefaultDisk__selected_disks"), [disk])
        self.assertEqual(getattr(obj, "_BootcDefaultDisk__selected_disks_sum"), 500)
        self.assertFalse(getattr(obj, "_BootcDefaultDisk__use_virtual_disk"))
        self.assertEqual(
            getattr(obj, "_BootcDefaultDisk__partition_recipe")["auto"]["disk"],
            "/dev/nvme0n1",
        )
        getattr(obj, "_BootcDefaultDisk__update_action_buttons").assert_called_once_with()


class TestPartitionSelectorCheckSelectedPartitionsSizes(unittest.TestCase):
    def setUp(self):
        self.mod = _import_disk_fresh()

    def _make_selector(self, selected_partitions):
        selector = self.mod.PartitionSelector.__new__(self.mod.PartitionSelector)
        setattr(selector, "_PartitionSelector__selected_partitions", selected_partitions)
        setattr(selector, "_PartitionSelector__valid_partition_sizes", False)

        selector.boot_small_error = _FakeErrorRow()
        selector.efi_small_error = _FakeErrorRow()
        selector.bios_small_error = _FakeErrorRow()
        selector.root_small_error = _FakeErrorRow()
        selector.var_small_error = _FakeErrorRow()

        selector.boot_part_expand = _FakeExpandRow(["error"])
        selector.efi_part_expand = _FakeExpandRow(["error"])
        selector.bios_part_expand = _FakeExpandRow(["error"])
        selector.root_part_expand = _FakeExpandRow(["error"])
        selector.var_part_expand = _FakeExpandRow(["error"])
        return selector

    def test_check_selected_partitions_sizes_marks_small_uefi_partitions_invalid(self):
        selected = {
            "boot_part_expand": {"min_size": 100, "partition": types.SimpleNamespace(size=99)},
            "efi_part_expand": {"min_size": 200, "partition": types.SimpleNamespace(size=200)},
            "root_part_expand": {"min_size": 300, "partition": types.SimpleNamespace(size=250)},
            "var_part_expand": {"min_size": 400, "partition": types.SimpleNamespace(size=400)},
        }
        selector = self._make_selector(copy.deepcopy(selected))

        self.mod.PartitionSelector.check_selected_partitions_sizes(selector)

        self.assertFalse(getattr(selector, "_PartitionSelector__valid_partition_sizes"))
        self.assertTrue(selector.boot_small_error.visible)
        self.assertEqual(selector.boot_small_error.description, "Partition must be at least 100 B")
        self.assertIn("error", selector.boot_part_expand.get_style_context().classes)
        self.assertTrue(selector.root_small_error.visible)
        self.assertEqual(selector.root_small_error.description, "Partition must be at least 300 B")
        self.assertFalse(selector.efi_small_error.visible)

    def test_check_selected_partitions_sizes_flags_bios_partition_that_is_not_exact_size(self):
        selected = {
            "boot_part_expand": {"min_size": 100, "partition": types.SimpleNamespace(size=100)},
            "bios_part_expand": {"min_size": 256, "partition": types.SimpleNamespace(size=128)},
            "root_part_expand": {"min_size": 300, "partition": types.SimpleNamespace(size=300)},
            "var_part_expand": {"min_size": 400, "partition": types.SimpleNamespace(size=400)},
        }
        selector = self._make_selector(copy.deepcopy(selected))
        self.mod.Systeminfo.is_uefi = staticmethod(lambda: False)

        self.mod.PartitionSelector.check_selected_partitions_sizes(selector)

        self.assertTrue(selector.bios_small_error.visible)
        self.assertEqual(selector.bios_small_error.description, "Partition must EXACTLY 256 B")
        self.assertIn("error", selector.bios_part_expand.get_style_context().classes)


class TestBootcDefaultDiskRefreshFromImageStep(unittest.TestCase):
    def setUp(self):
        self.mod = _import_disk_fresh()

    def _make_obj(self, current_hostname, finals):
        obj = self.mod.BootcDefaultDisk.__new__(self.mod.BootcDefaultDisk)
        image_step = MagicMock()
        image_step.get_finals.return_value = finals
        window = types.SimpleNamespace(image_step=image_step)
        setattr(obj, "_BootcDefaultDisk__window", window)
        setattr(obj, "_BootcDefaultDisk__setup_filesystem_row", MagicMock())
        obj.hostname_entry = MagicMock()
        obj.hostname_entry.get_text.return_value = current_hostname
        return obj

    def test_refresh_from_image_step_applies_default_hostname_to_empty_entry(self):
        obj = self._make_obj("", {"default_hostname": "bluefin", "supported_filesystems": ["xfs", "btrfs"]})

        obj._BootcDefaultDisk__refresh_from_image_step()

        # Code appends hardware suffix from Systeminfo.generate_hostname() ("generated-host" → suffix "host")
        obj.hostname_entry.set_text.assert_called_once_with("bluefin-host")
        getattr(obj, "_BootcDefaultDisk__setup_filesystem_row").assert_called_once_with(["xfs", "btrfs"])

    def test_refresh_from_image_step_preserves_custom_hostname(self):
        obj = self._make_obj("custom-host", {"default_hostname": "bluefin", "supported_filesystems": ["xfs"]})

        obj._BootcDefaultDisk__refresh_from_image_step()

        obj.hostname_entry.set_text.assert_not_called()
        getattr(obj, "_BootcDefaultDisk__setup_filesystem_row").assert_called_once_with(["xfs"])


if __name__ == "__main__":
    unittest.main()
