# welcome.py
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

import os
import pathlib
import subprocess

from gi.repository import Adw, Gtk

from bootc_installer.views.done import apply_icon
from bootc_installer.windows.dialog_recovery import VanillaRecoveryDialog
from bootc_installer.windows.dialog_poweroff import VanillaPoweroffDialog

_IN_FLATPAK = os.path.exists("/.flatpak-info")


def _needs_bluetooth_pairing() -> bool:
    """Return True if a Bluetooth adapter exists but no wired HID is present."""
    bt_adapters = list(pathlib.Path("/sys/class/bluetooth").glob("hci*"))
    if not bt_adapters:
        return False

    input_path = pathlib.Path("/sys/class/input")
    for dev in input_path.glob("event*"):
        device_path = dev / "device"
        if not device_path.exists():
            continue

        phys_file = device_path / "phys"
        if not phys_file.exists():
            continue

        try:
            phys = phys_file.read_text().strip()
        except OSError:
            continue

        if "usb" not in phys.lower():
            continue

        cap_file = device_path / "capabilities" / "ev"
        if not cap_file.exists():
            continue

        try:
            caps = int(cap_file.read_text().strip(), 16)
        except (OSError, ValueError):
            continue

        if caps & 0x2 or caps & 0x4:
            return False

    return True


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/default-welcome.ui")
class VanillaDefaultWelcome(Adw.Bin):
    __gtype_name__ = "VanillaDefaultWelcome"

    page_header = Gtk.Template.Child()
    row_install = Gtk.Template.Child()
    row_bluetooth = Gtk.Template.Child()
    row_recovery = Gtk.Template.Child()
    row_poweroff = Gtk.Template.Child()
    btn_credits = Gtk.Template.Child()

    def __init__(self, window, distro_info, key, step, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__distro_info = distro_info
        self.__key = key
        self.__step = step
        self.delta = False

        fallback_logo = self.__distro_info.get("logo", "org.bootcinstaller.Installer")
        icon_spec = self.__distro_info.get("default_image_icon") or fallback_logo

        apply_icon(self.page_header, icon_spec)
        welcome_title = self.__distro_info.get("welcome_title") or "bootc Installer"
        self.page_header.title = welcome_title
        welcome_subtitle = self.__distro_info.get("welcome_subtitle", "")
        if welcome_subtitle:
            self.page_header.subtitle = welcome_subtitle

        try:
            self.row_bluetooth.set_visible(_needs_bluetooth_pairing())
        except Exception:
            self.row_bluetooth.set_visible(False)

        # signals
        self.row_install.connect("activated", self.__install)
        self.row_bluetooth.connect("activated", self.__on_bluetooth_clicked)
        self.row_recovery.connect("activated", self.__on_recovery_clicked)
        self.row_poweroff.connect("activated", self.__on_poweroff_clicked)
        self.btn_credits.connect("clicked", self.__on_credits_clicked)

    def should_show(self, context: dict) -> bool:
        return True

    def test_auto_advance(self):
        self.row_install.emit("activated")

    def get_finals(self):
        return {}

    def __on_bluetooth_clicked(self, row):
        commands = [
            ["gnome-control-center", "bluetooth"],
            ["gnome-bluetooth-panel"],
            ["blueman-manager"],
        ]

        for command in commands:
            if _IN_FLATPAK:
                command = ["flatpak-spawn", "--host"] + command
            try:
                subprocess.Popen(command)
                return
            except FileNotFoundError:
                continue
            except Exception:
                return

    def __on_recovery_clicked(self, row):
        VanillaRecoveryDialog(self.__window).show()

    def __on_poweroff_clicked(self, row):
        VanillaPoweroffDialog(self.__window).show()

    def __on_credits_clicked(self, button):
        from bootc_installer.windows.dialog_credits import TunaCreditsWindow
        TunaCreditsWindow(self.__window).show()

    def __install(self, _):
        if self.__window.install_mode == 1:
            self.__window.rebuild_ui(0)
        self.__window.next()
