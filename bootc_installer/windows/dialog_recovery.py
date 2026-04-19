# dialog_recovery.py
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

import subprocess
from gettext import gettext as _

from gi.repository import Adw, GLib, Gtk


def _host_binary_exists(name):
    """Return True if `name` is found on the host's PATH via flatpak-spawn."""
    try:
        result = subprocess.run(
            ["flatpak-spawn", "--host", "which", name],
            capture_output=True,
            timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/dialog-recovery.ui")
class VanillaRecoveryDialog(Adw.Window):
    __gtype_name__ = "VanillaRecoveryDialog"

    row_console = Gtk.Template.Child()
    row_documentation = Gtk.Template.Child()
    row_partition = Gtk.Template.Child()
    row_handbook = Gtk.Template.Child()
    row_web = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.set_transient_for(window)

        # Show the disk-manager row only when gnome-disks is present on the host
        if _host_binary_exists("gnome-disks"):
            self.row_partition.connect("activated", self.__on_partition_activated)
        else:
            self.row_partition.set_visible(False)

        # signals
        self.row_console.connect("activated", self.__on_console_activated)
        self.row_documentation.connect("activated", self.__on_documentation_activated)
        self.row_handbook.connect("activated", self.__on_handbook_activated)
        self.row_web.connect("activated", self.__on_web_activated)

    def __on_console_activated(self, row):
        GLib.spawn_command_line_async("flatpak-spawn --host /usr/bin/xdg-terminal-exec")

    def __on_documentation_activated(self, row):
        Gtk.show_uri(self, "https://docs.projectbluefin.io/", GLib.CURRENT_TIME)

    def __on_partition_activated(self, row):
        GLib.spawn_command_line_async("flatpak-spawn --host /usr/bin/gnome-disks")

    def __on_handbook_activated(self, row):
        Gtk.show_uri(self, "https://app.dosu.dev/e3630b91-3a35-46b9-a8d3-b0c1b3ef6331/ask", GLib.CURRENT_TIME)

    def __on_web_activated(self, row):
        Gtk.show_uri(self, "https://universal-blue.org/", GLib.CURRENT_TIME)
