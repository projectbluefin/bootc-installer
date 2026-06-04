# disk.py
#
# Copyright 2024 mirkobrombin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundationat version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Class overview (all are GTK widget subclasses — kept in one file due to
# tight coupling; extract only if they grow independent):
#
#   BootcDefaultDiskEntry      — single disk item row (auto-select list)
#   PartitionRow                 — single partition row in the manual selector
#   PartitionSelector            — full manual partition selector page
#   BootcDefaultDiskPartModal  — modal window wrapping PartitionSelector
#   BootcDefaultDiskConfirmModal — confirmation modal before manual install
#   BootcDefaultDisk           — main disk wizard step (auto + manual tabs)

import pathlib
import subprocess
from gettext import gettext as _
from typing import Union
import logging
import os

from gi.repository import Adw, GLib, GObject, Gtk

from bootc_installer.core.disks import DisksManager, Diskutils, Partition
from bootc_installer.core.system import Systeminfo

logger = logging.getLogger("Installer::Disk")


# ── Disk list row ──────────────────────────────────────────────────────────────

@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/widget-disk.ui")
class BootcDefaultDiskEntry(Adw.ActionRow):
    __gtype_name__ = "BootcDefaultDiskEntry"

    chk_button = Gtk.Template.Child()

    def __init__(self, parent, disk, role="system", **kwargs):
        super().__init__(**kwargs)
        self.__parent = parent
        self.__disk = disk
        self.set_title(disk.display_name)
        self.set_subtitle(f"{disk.disk} · {disk.pretty_size}")

        callback = (
            self.__parent.on_var_disk_entry_toggled
            if role == "var"
            else self.__parent.on_disk_entry_toggled
        )
        self.chk_button.connect("toggled", callback, self.disk)

    @property
    def is_active(self):
        if self.chk_button.get_active():
            return True

    @property
    def disk(self):
        return self.__disk

    @property
    def disk_block(self):
        return self.__partition.disk_block


# ── Manual partition row ───────────────────────────────────────────────────────

@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/widget-partition-row.ui")
class PartitionRow(Adw.ActionRow):
    __gtype_name__ = "PartitionRow"

    select_button = Gtk.Template.Child()
    suffix_bin = Gtk.Template.Child()

    __siblings: list

    __partition_fs_types = ["btrfs", "ext4", "ext3", "fat32", "xfs"]

    def __init__(self, page, parent, partition, modifiable, default_fs, **kwargs):
        super().__init__(**kwargs)
        self.__page = page
        self.__parent = parent
        self.__partition = partition
        self.__modifiable = modifiable
        self.__default_fs = default_fs

        self.set_title(partition.partition)
        self.set_subtitle(partition.pretty_size)

        self.select_button.connect("toggled", self.__on_check_button_toggled)

        if self.__modifiable:
            self.__add_dropdown()

    def __add_dropdown(self):
        if self.__partition.fs_type in self.__partition_fs_types:
            fs_dropdown = Gtk.DropDown.new_from_strings(["unformatted"] + self.__partition_fs_types)
        else:
            fs_dropdown = Gtk.DropDown.new_from_strings(self.__partition_fs_types)
        fs_dropdown.set_valign(Gtk.Align.CENTER)
        fs_dropdown.set_visible(False)

        selected_fs = self.__default_fs
        if self.__partition.fs_type in self.__partition_fs_types:
            selected_fs = self.__partition.fs_type

        fs_dropdown.set_selected(self.__partition_fs_types.index(selected_fs))
        fs_dropdown.connect("notify::selected", self.__on_dropdown_selected)
        self.suffix_bin.set_child(fs_dropdown)

    def add_siblings(self, siblings):
        self.__siblings = siblings

    def __on_check_button_toggled(self, widget):
        dropdown = self.suffix_bin.get_child()

        # Sets all sibling dropdowns as not visible
        for sibling in self.__siblings:
            sibling_dropdown = sibling.suffix_bin.get_child()
            if sibling_dropdown:
                sibling_dropdown.set_visible(False)

        # Only the currently selected partition can be edited
        if dropdown:
            dropdown.set_visible(True)
            fs_type = self.__partition_fs_types[dropdown.get_selected()]
            self.__parent.set_subtitle(f"{self.__partition.pretty_size} ({fs_type})")
        else:
            self.__parent.set_subtitle(f"{self.__partition.pretty_size}")

        self.__parent.set_title(self.__partition.partition)
        self.__page.selected_partitions[self.__parent.get_buildable_id()][
            "partition"
        ] = self.__partition

        # Sets already selected partitions as not sensitive
        self.__page.update_partition_rows()
        # Checks whether selected partitions are big enough
        self.__page.check_selected_partitions_sizes()
        # Checks whether we can proceed with installation
        self.__page.update_apply_button_status()

    def __on_dropdown_selected(self, widget, _):
        fs_type = self.__partition_fs_types[widget.get_selected()]
        size = self.__partition.pretty_size
        self.__page.selected_partitions[self.__parent.get_buildable_id()][
            "fstype"
        ] = fs_type
        self.__parent.set_subtitle(f"{size} ({fs_type})")


# ── Manual partition selector page ────────────────────────────────────────────

@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/widget-partition.ui")
class PartitionSelector(Adw.PreferencesPage):
    __gtype_name__ = "PartitionSelector"

    open_gparted_group = Gtk.Template.Child()
    open_gparted_row = Gtk.Template.Child()
    launch_gparted = Gtk.Template.Child()

    boot_part = Gtk.Template.Child()
    efi_part = Gtk.Template.Child()
    bios_part = Gtk.Template.Child()
    root_part = Gtk.Template.Child()
    var_part = Gtk.Template.Child()
    swap_part = Gtk.Template.Child()

    boot_part_expand = Gtk.Template.Child()
    efi_part_expand = Gtk.Template.Child()
    bios_part_expand = Gtk.Template.Child()
    root_part_expand = Gtk.Template.Child()
    var_part_expand = Gtk.Template.Child()
    swap_part_expand = Gtk.Template.Child()

    use_swap_part = Gtk.Template.Child()
    keep_efi_part = Gtk.Template.Child()

    boot_small_error = Gtk.Template.Child()
    efi_small_error = Gtk.Template.Child()
    bios_small_error = Gtk.Template.Child()
    root_small_error = Gtk.Template.Child()
    var_small_error = Gtk.Template.Child()

    # NOTE: Keys must be the same name as template children
    __selected_partitions: dict[str, dict[str, Union[Partition, str, None]]] = {
        "boot_part_expand": {
            "mountpoint": "/boot",
            "min_size": 943_718_400,  # 900 MB
            "partition": None,
            "fstype": None,
        },
        "efi_part_expand": {
            "mountpoint": "/boot/efi",
            "min_size": 536_870_912,  # 512 MB
            "partition": None,
            "fstype": None,
        },
        "bios_part_expand": {
            "mountpoint": "",
            "min_size": 1_048_576,  # 512 MB
            "partition": None,
            "fstype": None,
        },
        "root_part_expand": {
            "mountpoint": "/",
            "min_size": 22_523_707_392,  # 20.5 GB
            "partition": None,
            "fstype": None,
        },
        "var_part_expand": {
            "mountpoint": "/var",
            "min_size": 5_368_709_120,  # 5 GB
            "partition": None,
            "fstype": None,
        },
        "swap_part_expand": {
            "mountpoint": "swap",
            "partition": None,
            "fstype": None,
        },
    }
    __valid_partition_sizes = False

    def __init__(self, parent, partitions, **kwargs):
        super().__init__(**kwargs)
        self.__parent = parent
        self.__partitions = sorted(partitions)
        self.__recipe = self.__parent.recipe

        self.launch_gparted.connect("clicked", self.__on_launch_gparted)
        self.use_swap_part.connect("state-set", self.__on_use_swap_toggled)
        self.keep_efi_part.connect("state-set", self.__on_keep_efi_toggled)

        self.__boot_part_rows = self.__generate_partition_list_widgets(
            self.boot_part_expand, "ext4", False
        )
        for i, widget in enumerate(self.__boot_part_rows):
            self.boot_part_expand.add_row(widget)
            widget.add_siblings(
                self.__boot_part_rows[:i] + self.__boot_part_rows[i + 1 :]
            )
            self.__selected_partitions["boot_part_expand"]["fstype"] = "ext4"

        if Systeminfo.is_uefi():
            # Configure EFI rows
            self.__efi_part_rows = self.__generate_partition_list_widgets(
                self.efi_part_expand, "fat32", False
            )
            for i, widget in enumerate(self.__efi_part_rows):
                self.efi_part_expand.add_row(widget)
                widget.add_siblings(
                    self.__efi_part_rows[:i] + self.__efi_part_rows[i + 1 :]
                )
                self.__selected_partitions["efi_part_expand"]["fstype"] = "fat32"

            # Remove BIOS rows
            self.bios_part.set_visible(False)
            if "bios_part_expand" in self.__selected_partitions:
                del self.__selected_partitions["bios_part_expand"]
        else:
            # Configure BIOS rows
            self.__bios_part_rows = self.__generate_partition_list_widgets(
                self.bios_part_expand, "ext4", False
            )
            for i, widget in enumerate(self.__bios_part_rows):
                self.bios_part_expand.add_row(widget)
                widget.add_siblings(
                    self.__bios_part_rows[:i] + self.__bios_part_rows[i + 1 :]
                )
                self.__selected_partitions["bios_part_expand"]["fstype"] = "ext4"

            # Remove EFI rows
            self.efi_part.set_visible(False)
            if "efi_part_expand" in self.__selected_partitions:
                del self.__selected_partitions["efi_part_expand"]

        self.__root_part_rows = self.__generate_partition_list_widgets(
            self.root_part_expand, "btrfs", False
        )
        for i, widget in enumerate(self.__root_part_rows):
            self.root_part_expand.add_row(widget)
            widget.add_siblings(
                self.__root_part_rows[:i] + self.__root_part_rows[i + 1 :]
            )
            self.__selected_partitions["root_part_expand"]["fstype"] = "btrfs"

        self.__var_part_rows = self.__generate_partition_list_widgets(
            self.var_part_expand
        )
        for i, widget in enumerate(self.__var_part_rows):
            self.var_part_expand.add_row(widget)
            widget.add_siblings(
                self.__var_part_rows[:i] + self.__var_part_rows[i + 1 :]
            )
            self.__selected_partitions["var_part_expand"]["fstype"] = "btrfs"

        self.__swap_part_rows = self.__generate_partition_list_widgets(
            self.swap_part_expand, "swap", False
        )
        for i, widget in enumerate(self.__swap_part_rows):
            self.swap_part_expand.add_row(widget)
            widget.add_siblings(
                self.__swap_part_rows[:i] + self.__swap_part_rows[i + 1 :]
            )
            self.__selected_partitions["swap_part_expand"]["fstype"] = "swap"

        for widget in [self.boot_part, self.efi_part, self.root_part, self.var_part]:
            widget.set_description(widget.get_description() + self.get_partition_size_string(widget) + ".")
        self.update_apply_button_status()

    def __on_launch_gparted(self, widget):
        proc = subprocess.Popen(["ps", "-C", "gparted"])
        proc.wait()
        if proc.returncode == 0:
            partitions_changed_toast = Adw.Toast.new(
                _(
                    "GParted is already running. Only one instance of GParted is permitted."
                )
            )
            partitions_changed_toast.set_timeout(5)
            self.__parent.group_partitions.add_toast(partitions_changed_toast)
        else:
            subprocess.Popen(["/usr/sbin/gparted"])

    def __generate_partition_list_widgets(
        self, parent_widget, default_fs="btrfs", add_dropdowns=True
    ):
        partition_widgets = []

        for i, partition in enumerate(self.__partitions):
            partition_row = PartitionRow(
                self, parent_widget, partition, add_dropdowns, default_fs
            )
            if i != 0:
                partition_row.select_button.set_group(
                    partition_widgets[0].select_button
                )
            partition_widgets.append(partition_row)

        parent_widget.set_sensitive(len(partition_widgets) > 0)

        return partition_widgets

    def update_apply_button_status(self):
        for k, val in self.__selected_partitions.items():
            if val["partition"] is None and (
                k != "swap_part_expand" or self.use_swap_part.get_active()
            ):
                self.__parent.set_btn_apply_sensitive(False)
                return

        if self.__valid_partition_sizes:
            self.__parent.set_btn_apply_sensitive(True)

    def check_selected_partitions_sizes(self):
        # Clear any existing errors
        self.__valid_partition_sizes = True
        self.boot_small_error.set_visible(False)
        if Systeminfo.is_uefi():
            self.efi_small_error.set_visible(False)
        else:
            self.bios_small_error.set_visible(False)
        self.root_small_error.set_visible(False)
        self.var_small_error.set_visible(False)
        if self.boot_part_expand.get_style_context().has_class("error"):
            self.boot_part_expand.get_style_context().remove_class("error")
        if Systeminfo.is_uefi():
            if self.efi_part_expand.get_style_context().has_class("error"):
                self.efi_part_expand.get_style_context().remove_class("error")
        else:
            if self.bios_part_expand.get_style_context().has_class("error"):
                self.bios_part_expand.get_style_context().remove_class("error")
        if self.root_part_expand.get_style_context().has_class("error"):
            self.root_part_expand.get_style_context().remove_class("error")
        if self.var_part_expand.get_style_context().has_class("error"):
            self.var_part_expand.get_style_context().remove_class("error")

        for partition, info in self.__selected_partitions.items():
            if "min_size" in info and info["partition"] is not None:
                if info["min_size"] > info["partition"].size:
                    self.__valid_partition_sizes = False
                    error_description = _("Partition must be at least {}").format(
                        Diskutils.pretty_size(info["min_size"])
                    )
                    if partition == "boot_part_expand":
                        self.boot_part_expand.get_style_context().add_class("error")
                        self.boot_small_error.set_description(error_description)
                        self.boot_small_error.set_visible(True)
                    elif partition == "efi_part_expand":
                        self.efi_part_expand.get_style_context().add_class("error")
                        self.efi_small_error.set_description(error_description)
                        self.efi_small_error.set_visible(True)
                    elif partition == "root_part_expand":
                        self.root_part_expand.get_style_context().add_class("error")
                        self.root_small_error.set_description(error_description)
                        self.root_small_error.set_visible(True)
                    elif partition == "var_part_expand":
                        self.var_part_expand.get_style_context().add_class("error")
                        self.var_small_error.set_description(error_description)
                        self.var_small_error.set_visible(True)

        # Special case for BIOS, where the partitions needs to be EXACTLY 1 MiB
        if not Systeminfo.is_uefi():
            size = self.__selected_partitions["bios_part_expand"]["min_size"]
            partition = self.__selected_partitions["bios_part_expand"]["partition"]
            error_description = _("Partition must EXACTLY {}").format(
                Diskutils.pretty_size(size)
            )
            if partition is not None:
                if size != partition.size:
                    self.bios_part_expand.get_style_context().add_class("error")
                    self.bios_small_error.set_description(error_description)
                    self.bios_small_error.set_visible(True)

    def get_partition_size_string(self, widget):
        size = 0
        if widget == self.boot_part:
            size = self.__recipe["min_partition_sizes"]["/boot"]
        if widget == self.efi_part:
            size = self.__recipe["min_partition_sizes"]["/boot/efi"]
        if widget == self.root_part:
            size = self.__recipe["min_partition_sizes"]["/"]
        if widget == self.var_part:
            size = self.__recipe["min_partition_sizes"]["/var"]
        if size > 1024:
            return str(int(size/1024)) + "GiB"
        else:
            return str(size) + "MiB"


    def __on_use_swap_toggled(self, widget, state):
        if not state:
            for child_row in self.__swap_part_rows:
                child_row.select_button.set_active(False)

            self.__selected_partitions["swap_part_expand"]["partition"] = None
            self.swap_part_expand.set_title(_("No partition selected"))
            self.swap_part_expand.set_subtitle(
                _("Please select a partition from the options below")
            )
            self.update_partition_rows()

        self.update_apply_button_status()

    def __on_keep_efi_toggled(self, widget, state):
        if state:
            self.__selected_partitions["efi_part_expand"]["fstype"] = "unformatted"
        else:
            self.__selected_partitions["efi_part_expand"]["fstype"] = "fat32"

    def update_partition_rows(self):
        rows = [
            self.__boot_part_rows,
            self.__root_part_rows,
            self.__var_part_rows,
            self.__swap_part_rows,
        ]

        if Systeminfo.is_uefi():
            rows.append(self.__efi_part_rows)
        else:
            rows.append(self.__bios_part_rows)

        for row in rows:
            for child_row in row:
                row_partition = child_row.get_title()

                # The row where partition was selected still has to be sensitive
                if child_row.select_button.get_active():
                    child_row.set_sensitive(True)
                    continue

                is_used = False
                for __, val in self.__selected_partitions.items():
                    if (
                        val["partition"] is not None
                        and val["partition"].partition == row_partition
                    ):
                        is_used = True
                child_row.set_sensitive(not is_used)

    def cleanup(self):
        for partition, info in self.__selected_partitions.items():
            for k, __ in info.items():
                if k not in ["mountpoint", "min_size"]:
                    self.__selected_partitions[partition][k] = None

    @property
    def selected_partitions(self):
        return self.__selected_partitions


# ── Partition selection modal window ──────────────────────────────────────────

@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/dialog-disk.ui")
class BootcDefaultDiskPartModal(Adw.Window):
    __gtype_name__ = "BootcDefaultDiskPartModal"
    __gsignals__ = {
        "partitioning-set": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    group_partitions = Gtk.Template.Child()
    btn_cancel = Gtk.Template.Child()
    btn_apply = Gtk.Template.Child()

    def __init__(self, window, parent, disks, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__parent = parent
        self.__disks = disks
        self.set_transient_for(self.__window)
        self.recipe = window.recipe

        self.__partitions = []
        for disk in self.__disks:
            for part in disk.partitions:
                self.__partitions.append(part)

        # signals
        self.btn_cancel.connect("clicked", self.__on_btn_cancel_clicked)
        self.btn_apply.connect("clicked", self.__on_btn_apply_clicked)
        self.connect("notify::is-active", self.__on_window_active)

        self.__partition_selector = PartitionSelector(self, self.__partitions)
        self.group_partitions.set_child(self.__partition_selector)

    def __on_window_active(self, widget, value):
        # Only update partitions when window has gained focus
        if self.is_active():
            current_partitions = self.__partitions.copy()

            self.__partitions = []
            for disk in self.__disks:
                disk.update_partitions()
                for part in disk.partitions:
                    self.__partitions.append(part)

            if current_partitions != self.__partitions:
                self.__partition_selector.cleanup()
                self.__partition_selector.unrealize()
                self.__partition_selector = PartitionSelector(self, self.__partitions)
                self.group_partitions.set_child(self.__partition_selector)
                partitions_changed_toast = Adw.Toast.new(
                    _("Partitions have changed. Current selections have been cleared.")
                )
                partitions_changed_toast.set_timeout(5)
                self.group_partitions.add_toast(partitions_changed_toast)

    def __on_btn_cancel_clicked(self, widget):
        self.__partition_selector.cleanup()
        self.destroy()

    def __on_btn_apply_clicked(self, widget):
        self.__parent.set_partition_recipe(self.partition_recipe)
        self.emit("partitioning-set", "")
        self.destroy()

    def set_btn_apply_sensitive(self, val):
        self.btn_apply.set_sensitive(val)

    @property
    def partition_recipe(self):
        recipe = {}

        pv_list = Diskutils.fetch_lvm_pvs()

        for __, info in self.__partition_selector.selected_partitions.items():
            # Partition can be None if user didn't configure swap
            if not isinstance(info["partition"], Partition):
                continue

            pv_to_remove = None
            vg_to_remove = None
            for pv, vg in pv_list:
                if pv == info["partition"].partition:
                    pv_to_remove = pv
                    vg_to_remove = vg

            recipe[info["partition"].partition] = {
                "fs": info["fstype"],
                "mp": info["mountpoint"],
                "pretty_size": info["partition"].pretty_size,
                "size": info["partition"].size,
                "existing_pv": pv_to_remove,
                "existing_vg": vg_to_remove
            }

        return recipe


# ── Manual install confirmation modal ─────────────────────────────────────────

@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/dialog-disk-confirm.ui")
class BootcDefaultDiskConfirmModal(Adw.Window):
    __gtype_name__ = "BootcDefaultDiskConfirmModal"

    btn_cancel = Gtk.Template.Child()
    btn_apply = Gtk.Template.Child()
    group_partitions = Gtk.Template.Child()

    def __init__(self, window, partition_recipe, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.set_transient_for(self.__window)
        self.default_width, self.default_height = self.get_default_size()

        # signals
        self.btn_cancel.connect("clicked", self.__on_btn_cancel_clicked)
        self.btn_apply.connect("clicked", self.__on_btn_apply_clicked)

        for partition, values in partition_recipe.items():
            entry = Adw.ActionRow()
            if partition == "auto":
                entry.set_title(partition_recipe[partition]["disk"])
                entry.set_subtitle(_("Entire disk will be used."))
            else:
                if partition == "disk":
                    continue
                entry.set_title(partition)
                if partition_recipe[partition]["fs"] == "unformatted":
                    entry.set_subtitle(
                        _("Will be mounted in {}").format(
                            partition_recipe[partition]["mp"],
                        )
                    )
                else:
                    entry.set_subtitle(
                        _("Will be formatted in {} and mounted in {}").format(
                            partition_recipe[partition]["fs"],
                            partition_recipe[partition]["mp"],
                        )
                    )
            self.group_partitions.add(entry)

        if "auto" in partition_recipe:
            for vg in partition_recipe["auto"]["vgs_to_remove"]:
                entry = Adw.ActionRow()
                entry.set_title("LVM volume group: " + vg)
                entry.set_subtitle(_("Volume group will be removed."))
                self.group_partitions.add(entry)
            for pv in partition_recipe["auto"]["pvs_to_remove"]:
                entry = Adw.ActionRow()
                entry.set_title("LVM physical volume: " + pv)
                entry.set_subtitle(_("Physical volume will be removed."))
                self.group_partitions.add(entry)
        else:
            vgs_to_remove = []
            for partition, values in partition_recipe.items():
                if partition == "disk":
                    continue
                pv = values["existing_pv"]
                vg = values["existing_vg"]
                if pv is None:
                    continue
                if vg is not None and vg not in vgs_to_remove:
                    vgs_to_remove.append(values["existing_vg"])
                entry = Adw.ActionRow()
                entry.set_title("LVM physical volume: " + pv)
                entry.set_subtitle(_("Physical volume will be removed."))
                self.group_partitions.add(entry)
            for vg in vgs_to_remove:
                entry = Adw.ActionRow()
                entry.set_title("LVM volume group: " + vg)
                entry.set_subtitle(_("Volume group will be removed."))
                self.group_partitions.add(entry)

    def __on_btn_cancel_clicked(self, widget):
        self.destroy()

    def __on_btn_apply_clicked(self, widget):
        self.__window.next()
        self.destroy()


# ── Main disk wizard step ──────────────────────────────────────────────────────

@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/default-disk.ui")
class BootcDefaultDisk(Adw.Bin):
    __gtype_name__ = "BootcDefaultDisk"

    btn_next = Gtk.Template.Child()
    btn_auto = Gtk.Template.Child()
    btn_exit = Gtk.Template.Child()
    group_disks = Gtk.Template.Child()
    disk_space_err_box = Gtk.Template.Child()
    disk_space_err_label = Gtk.Template.Child()
    filesystem_row = Gtk.Template.Child()
    fs_tool_error_banner = Gtk.Template.Child()
    hostname_entry = Gtk.Template.Child()
    var_disk_switch = Gtk.Template.Child()
    group_var_disks = Gtk.Template.Child()
    group_var_disk_existing = Gtk.Template.Child()
    battery_banner = Gtk.Template.Child()
    var_disk_keep_row = Gtk.Template.Child()
    var_disk_keep_switch = Gtk.Template.Child()

    _VIRTUAL_DISK_IMG = "/var/home/james/bootc-virtual-disk.img"
    _VIRTUAL_DISK_SIZE = "50G"

    def __init__(self, window, distro_info, key, step, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__distro_info = distro_info
        self.__key = key
        self.__step = step
        self.delta = False
        self.__registry_disks = []
        self.__selected_disks = []
        self.__disks = DisksManager()
        self.__partition_recipe = None
        self.__selected_disks_sum = 0
        self.__use_virtual_disk = False
        self.__fs_tool_ok = True  # optimistic default; updated by __check_fs_tool
        self.__var_disk_selected = None  # Disk object for the optional /var disk
        self.__var_registry_disks = []   # BootcDefaultDiskEntry rows for var picker

        self.min_disk_size = self.__window.recipe.get("min_disk_size", 51200)
        self.disk_space_err_label.set_label(
            self.disk_space_err_label.get_label()
            % Diskutils.pretty_size(self.min_disk_size * 1_048_576)
        )

        # Append real disk rows
        for disk in self.__disks.all_disks(include_removable=False):
            entry = BootcDefaultDiskEntry(self, disk)
            self.group_disks.add(entry)
            self.__registry_disks.append(entry)

        # If no fixed disks found, immediately populate removable disks too
        if not self.__registry_disks:
            for disk in self.__disks.all_disks(include_removable=True):
                if disk.is_removable:
                    entry = BootcDefaultDiskEntry(self, disk)
                    self.group_disks.add(entry)
                    self.__registry_disks.append(entry)

        # Virtual disk row — always present
        self.__virtual_row = self.__build_virtual_disk_row()
        self.group_disks.add(self.__virtual_row)

        if hasattr(Adw, 'ButtonRow'):
            self.__all_disks_button = Adw.ButtonRow()
        else:
            # Fallback for libadwaita < 1.6 (e.g. Ubuntu 24.04)
            self.__all_disks_button = Adw.ActionRow()
            self.__all_disks_button.set_activatable(True)
        self.__all_disks_button.set_title(_("Show removable disks"))
        self.group_disks.add(self.__all_disks_button)
        # Hide the button if removable disks are already shown
        if not self.__disks.all_disks(include_removable=False):
            self.__all_disks_button.set_visible(False)

        try:
            self.__all_disks_button.connect("activated", self.__on_btn_all_disks)
        except TypeError:
            # ActionRow fallback doesn't have 'activated' signal;
            # users can still access removable disks when no fixed disks exist
            pass
        self.btn_next.connect("clicked", self.__on_btn_next_clicked)
        self.btn_auto.connect("clicked", self.__on_auto_clicked)
        self.btn_exit.connect("clicked", self.__on_btn_exit_clicked)
        self.var_disk_switch.connect("notify::active", self.__on_var_disk_switch_toggled)

        # Populate filesystem picker and hostname from the selected image's metadata.
        # We do the initial setup now, but also refresh when this page becomes active
        # (image selection happens on the previous step, so __init__ runs too early).
        self.__filesystem_options = ["xfs"]
        self.__window.carousel.connect("page-changed", self.__on_carousel_page_changed)
        self.__refresh_from_image_step()
        self.__set_default_hostname()
        self.auto_select_single_disk()

        # Auto-select virtual disk if still no physical disks are available
        if not self.__registry_disks:
            self.__select_virtual_disk()

        self.__check_battery()

    def __on_carousel_page_changed(self, carousel, idx):
        if carousel.get_nth_page(idx) is self:
            self.__refresh_from_image_step()
            self.__check_battery()

    def __set_default_hostname(self):
        """Seed the hostname field with a hardware-derived name when no image
        step has provided a better default, so users see a unique, meaningful
        value rather than the generic 'localhost' placeholder."""
        current = self.hostname_entry.get_text().strip()
        if current not in ("", "localhost"):
            return
        try:
            generated = Systeminfo.generate_hostname()
            if generated:
                self.hostname_entry.set_text(generated)
        except Exception:
            logger.debug("Could not generate hostname", exc_info=True)

    def __check_battery(self):
        on_battery = False
        try:
            for supply in pathlib.Path("/sys/class/power_supply").iterdir():
                supply_type_file = supply / "type"
                if not supply_type_file.exists():
                    continue

                try:
                    supply_type = supply_type_file.read_text().strip()
                except OSError:
                    continue

                if supply_type not in ("Mains", "UPS"):
                    continue

                online_file = supply / "online"
                if not online_file.exists():
                    continue

                try:
                    if online_file.read_text().strip() == "0":
                        on_battery = True
                        break
                except OSError:
                    continue
        except Exception:
            logger.debug("Failed to determine power state", exc_info=True)

        self.battery_banner.set_revealed(on_battery)

    def __refresh_from_image_step(self):
        """Re-read image metadata and update filesystem picker and hostname."""
        image_step = getattr(self.__window, "image_step", None)
        if image_step is None:
            return
        finals = image_step.get_finals()
        if not isinstance(finals, dict):
            finals = {}
        supported = finals.get("supported_filesystems") or []
        default_hostname = finals.get("default_hostname") or ""
        if not isinstance(default_hostname, str):
            default_hostname = ""
        current = self.hostname_entry.get_text().strip()
        if default_hostname and current in ("", "localhost"):
            # Append a short hardware-derived suffix so the default hostname is
            # unique per machine (e.g. "bluefin-a7c3" instead of "bluefin").
            try:
                generated = Systeminfo.generate_hostname()
                suffix = generated.rsplit("-", 1)[-1] if "-" in generated else generated[-4:]
                unique_hostname = f"{default_hostname}-{suffix}"
            except Exception:
                unique_hostname = default_hostname
            self.hostname_entry.set_text(unique_hostname)
        self.__setup_filesystem_row(supported)

    # Maps filesystem type → (required tool, package name)
    _FS_TOOLS = {
        "xfs": ("mkfs.xfs", "xfsprogs"),
        "btrfs": ("mkfs.btrfs", "btrfs-progs"),
        "zfs": ("zpool", "zfsutils-linux"),
    }

    def __setup_filesystem_row(self, filesystems):
        """Show a filesystem picker when the selected image supports multiple rootfs types."""
        self.__filesystem_options = filesystems if filesystems else ["xfs"]
        if len(self.__filesystem_options) <= 1:
            self.filesystem_row.set_visible(False)
            self.__check_fs_tool(self.__filesystem_options[0] if self.__filesystem_options else "xfs")
            return

        _LABELS = {"xfs": "XFS", "btrfs": "Btrfs (with subvolumes)", "zfs": "ZFS"}
        model = Gtk.StringList.new([_LABELS.get(fs, fs.upper()) for fs in self.__filesystem_options])
        self.filesystem_row.set_model(model)
        self.filesystem_row.set_selected(0)
        self.filesystem_row.set_visible(True)
        self.filesystem_row.connect("notify::selected", self.__on_filesystem_changed)
        self.__check_fs_tool(self.__filesystem_options[0])

    def __on_filesystem_changed(self, row, _pspec):
        self.__check_fs_tool(self.__get_selected_filesystem())

    def __check_fs_tool(self, fs):
        """Highlight the filesystem row and block Next if the required mkfs tool is missing."""
        tool, pkg = self._FS_TOOLS.get(fs, (None, None))
        if tool is None:
            self.__fs_tool_ok = True
            self.filesystem_row.remove_css_class("error")
            self.filesystem_row.set_subtitle("")
            self.fs_tool_error_banner.set_visible(False)
            self.__update_next_button()
            return
        try:
            result = subprocess.run(
                ["flatpak-spawn", "--host", "sh", "-c", f"command -v {tool}"],
                capture_output=True,
                timeout=3,
            )
            available = result.returncode == 0
        except Exception:
            available = True  # assume available if check fails
        self.__fs_tool_ok = available
        if available:
            self.filesystem_row.remove_css_class("error")
            self.filesystem_row.set_subtitle("")
            self.fs_tool_error_banner.set_visible(False)
        else:
            self.filesystem_row.add_css_class("error")
            self.filesystem_row.set_subtitle(
                _('Install the "{}" package on the host to use this filesystem').format(pkg)
            )
            self.fs_tool_error_banner.set_title(
                _('Missing host tool: "{}" — install the "{}" package').format(tool, pkg)
            )
            self.fs_tool_error_banner.set_visible(True)
        self.__update_next_button()

    def __update_next_button(self):
        """Enable Next only when a partition recipe exists and the fs tool is present."""
        ok = self.__partition_recipe is not None and self.__fs_tool_ok
        self.btn_next.set_visible(ok)
        self.btn_next.set_sensitive(ok)

    def __get_selected_filesystem(self):
        if not self.filesystem_row.get_visible():
            return self.__filesystem_options[0] if self.__filesystem_options else "xfs"
        idx = self.filesystem_row.get_selected()
        if 0 <= idx < len(self.__filesystem_options):
            return self.__filesystem_options[idx]
        return "xfs"

    def __on_btn_exit_clicked(self, button):
        self.__window.get_application().quit()

    def should_show(self, context: dict) -> bool:
        return context.get("disk_count", 2) > 1

    def _set_auto_partition_recipe(self, disk):
        self.__partition_recipe = {
            "auto": {
                "disk": disk.disk,
                "pretty_size": disk.pretty_size,
                "size": disk.size,
                "vgs_to_remove": [],
                "pvs_to_remove": [],
            }
        }
        self.__update_next_button()

    def auto_select_single_disk(self):
        disks = self.__disks.all_disks(include_removable=False)
        if not disks:
            disks = self.__disks.all_disks(include_removable=True)

        if len(disks) != 1:
            return False

        disk = disks[0]
        self.__use_virtual_disk = False

        if not self.__selected_disks or self.__selected_disks[0].disk != disk.disk:
            matched_entry = next(
                (entry for entry in self.__registry_disks if entry.disk.disk == disk.disk),
                None,
            )
            if matched_entry is not None:
                matched_entry.chk_button.set_active(True)
            else:
                self.__selected_disks = [disk]
                self.__selected_disks_sum = disk.size
                self.__update_action_buttons()

        self._set_auto_partition_recipe(disk)
        logger.info("Auto-selected only installable disk: %s", disk.disk)
        return True

    @property
    def installable_disk_count(self) -> int:
        return len(self.__registry_disks)

    def test_auto_advance(self):
        self.btn_auto.emit("clicked")

    def __select_virtual_disk(self):
        if self.__use_virtual_disk:
            return
        self.__use_virtual_disk = True
        self.__selected_disks = []
        self.__selected_disks_sum = 0
        self.disk_space_err_box.set_visible(False)
        self.btn_auto.set_sensitive(True)
        self.__virtual_check.set_active(True)
        logger.info("Virtual disk selected")

    def __build_virtual_disk_row(self):
        row = Adw.ActionRow()
        row.set_title(_("Virtual disk (for VMs / testing)"))
        row.set_subtitle(
            _("Creates a %s disk image and attaches it as a loop device") % self._VIRTUAL_DISK_SIZE
        )

        icon = Gtk.Image.new_from_icon_name("computer-symbolic")
        row.add_prefix(icon)

        self.__virtual_check = Gtk.CheckButton()
        row.add_suffix(self.__virtual_check)
        row.set_activatable_widget(self.__virtual_check)

        # Wire activation to the row AND the check button for reliability
        row.connect("activated", self.__on_virtual_row_activated)
        self.__virtual_check.connect("toggled", self.__on_virtual_check_toggled)

        # Deselect virtual row when a real disk row is selected
        for entry in self.__registry_disks:
            entry.chk_button.set_group(self.__virtual_check)

        return row

    def __on_virtual_row_activated(self, row):
        self.__select_virtual_disk()

    def __on_virtual_check_toggled(self, widget):
        if widget.get_active():
            self.__select_virtual_disk()

    def __setup_loopback(self) -> str | None:
        """Create the disk image and attach it as a loop device. Returns the device path."""
        import subprocess

        # If a loop device was pre-created outside the sandbox, use it directly.
        pre_created = os.environ.get("BOOTC_VIRTUAL_DISK", "")
        if pre_created:
            logger.info(f"Using pre-created virtual disk: {pre_created}")
            return pre_created

        img = self._VIRTUAL_DISK_IMG
        # Commands that need root must break out of the Flatpak sandbox via flatpak-spawn
        def host_run(cmd, **kw):
            return subprocess.run(["flatpak-spawn", "--host"] + cmd, **kw)

        def host_output(cmd, **kw):
            return subprocess.check_output(["flatpak-spawn", "--host"] + cmd, **kw)

        try:
            logger.info(f"Creating virtual disk image: {img} ({self._VIRTUAL_DISK_SIZE})")
            subprocess.run(["truncate", "-s", self._VIRTUAL_DISK_SIZE, img], check=True)
            host_run(["pkexec", "losetup", "-fP", img], check=True)
            out = host_output(
                ["losetup", "--list", "--output", "NAME,BACK-FILE", "--noheadings"],
                text=True,
            )
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == img:
                    logger.info(f"Loop device: {parts[0]}")
                    return parts[0]
            logger.error("Could not find loop device after setup")
            return None
        except Exception as e:
            logger.error(f"Failed to set up loop device: {e}")
            return None

    def get_finals(self):
        fs = self.__get_selected_filesystem()
        disk = dict(self.__partition_recipe) if self.__partition_recipe else {}
        if "auto" in disk:
            disk["filesystem"] = fs
            disk["btrfsSubvolumes"] = (fs == "btrfs")
        result = {
            "disk": disk,
            "hostname": self.hostname_entry.get_text().strip() or "localhost",
        }
        if self.__use_virtual_disk:
            result["virtual_disk_img"] = self._VIRTUAL_DISK_IMG
            result["virtual_disk_loop"] = getattr(self, "_BootcDefaultDisk__loop_device", None)
        if self.var_disk_switch.get_active() and self.__var_disk_selected:
            result["var_disk"] = {
                "disk": self.__var_disk_selected.disk,
                "keep_existing": self.var_disk_keep_switch.get_active()
                if self.group_var_disk_existing.get_visible() else False,
            }
        return result

    def __on_btn_all_disks(self, widget):
        self.__all_disks_button.set_visible(False)
        for disk in self.__disks.all_disks(include_removable=True):
            if disk.is_removable:
                entry = BootcDefaultDiskEntry(self, disk)
                self.group_disks.add(entry)
                self.__registry_disks.append(entry)

    def __on_auto_clicked(self, button):
        if self.__use_virtual_disk:
            loop_dev = self.__setup_loopback()
            if not loop_dev:
                logger.error("Virtual disk setup failed")
                return
            self.__loop_device = loop_dev
            self.__partition_recipe = {
                "auto": {
                    "disk": loop_dev,
                    "pretty_size": self._VIRTUAL_DISK_SIZE,
                    "size": 0,
                    "vgs_to_remove": [],
                    "pvs_to_remove": [],
                }
            }
        else:
            self._set_auto_partition_recipe(self.__selected_disks[0])
        # In test mode skip the confirm modal and advance directly
        if os.environ.get("BOOTC_TEST"):
            self.__window.next()
            return
        self.confirm_partition_changes()

    def __update_action_buttons(self):
        if (
            self.__selected_disks_sum / 1_048_576 < self.min_disk_size
            and self.__selected_disks_sum > 0
        ):
            self.disk_space_err_box.set_visible(True)
            self.btn_auto.set_sensitive(False)
        else:
            self.disk_space_err_box.set_visible(False)
            self.btn_auto.set_sensitive(len(self.__selected_disks) == 1)

    def on_disk_entry_toggled(self, widget, disk):
        self.__use_virtual_disk = False
        if widget.get_active():
            self.__selected_disks.append(disk)
            self.__selected_disks_sum += disk.size
        else:
            self.__selected_disks.remove(disk)
            self.__selected_disks_sum -= disk.size
        self.__update_action_buttons()
        # Rebuild var disk picker to exclude newly selected system disk
        if self.var_disk_switch.get_active():
            self.__rebuild_var_disk_picker()

    def __on_var_disk_switch_toggled(self, switch, _param):
        if switch.get_active():
            self.group_var_disks.set_visible(True)
            self.__rebuild_var_disk_picker()
        else:
            self.group_var_disks.set_visible(False)
            self.group_var_disk_existing.set_visible(False)
            self.__var_disk_selected = None

    def __rebuild_var_disk_picker(self):
        """Repopulate group_var_disks excluding the currently selected system disk."""
        # Remove old entries
        for entry in self.__var_registry_disks:
            self.group_var_disks.remove(entry)
        self.__var_registry_disks.clear()
        self.__var_disk_selected = None
        self.group_var_disk_existing.set_visible(False)

        system_disk = (
            self.__selected_disks[0].disk if self.__selected_disks else None
        )
        for d in self.__disks.all_disks(include_removable=False):
            if system_disk and d.disk == system_disk:
                continue
            entry = BootcDefaultDiskEntry(self, d, role="var")
            self.group_var_disks.add(entry)
            self.__var_registry_disks.append(entry)

    def on_var_disk_entry_toggled(self, widget, disk):
        """Called by BootcDefaultDiskEntry when role='var' and user toggles it."""
        if widget.get_active():
            self.__var_disk_selected = disk
            self.__check_var_disk_existing(disk)
        else:
            self.__var_disk_selected = None
            self.group_var_disk_existing.set_visible(False)

    def __check_var_disk_existing(self, disk):
        """Detect existing filesystem on disk and show the keep/format toggle."""
        import subprocess
        try:
            out = subprocess.check_output(
                ["flatpak-spawn", "--host", "lsblk", "-no", "FSTYPE", disk.disk],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
            # If lsblk returns a non-empty fstype the disk has a filesystem
            has_existing = bool(out)
        except Exception:
            has_existing = False
        if has_existing:
            logger.info("Existing filesystem detected on /var disk %s", disk.disk)
            self.group_var_disk_existing.set_visible(True)
            self.var_disk_keep_switch.set_active(True)
        else:
            self.group_var_disk_existing.set_visible(False)

    def set_partition_recipe(self, recipe):
        self.__partition_recipe = recipe

    def __on_btn_next_clicked(self, button):
        self.confirm_partition_changes()

    def confirm_partition_changes(self):
        modal = BootcDefaultDiskConfirmModal(self.__window, self.__partition_recipe)
        modal.present()
