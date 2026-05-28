# dialog.py
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
import re
from gettext import gettext as _

_ENC_LABELS = {
    "none": "None",
    "luks-passphrase": "Encrypted with passphrase",
    "tpm2-luks": "Hardware-backed encryption",
    "tpm2-luks-passphrase": "Hardware-backed + passphrase fallback",
}

from gi.repository import Adw, GLib, GObject, Gtk


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/widget-choice.ui")
class BootcChoiceEntry(Adw.ActionRow):
    __gtype_name__ = "BootcChoiceEntry"

    img_choice = Gtk.Template.Child()

    def __init__(self, title, subtitle, icon_name, **kwargs):
        super().__init__(**kwargs)
        self.set_title(title)
        self.set_subtitle(subtitle)
        self.img_choice.set_from_icon_name(icon_name)


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/widget-choice-expander.ui")
class BootcChoiceExpanderEntry(Adw.ExpanderRow):
    __gtype_name__ = "BootcChoiceExpanderEntry"

    img_choice = Gtk.Template.Child()

    def __init__(self, title, subtitle, icon_name, **kwargs):
        super().__init__(**kwargs)
        self.set_title(title)
        self.set_subtitle(subtitle)
        self.img_choice.set_from_icon_name(icon_name)


_SENNA_QUOTES = [
    _('"If you have God on your side, everything becomes clear." — Ayrton Senna'),
    _('"I am not designed to come second or third. I am designed to win." — Ayrton Senna'),
    _('"Being second is to be the first of the ones who lose." — Ayrton Senna'),
    _('"On a given day, a given circumstance, you think you have a limit — and you go beyond it." — Ayrton Senna'),
]


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/confirm.ui")
class BootcConfirm(Adw.Bin):
    __gtype_name__ = "BootcConfirm"
    __gsignals__ = {
        "installation-confirmed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    group_changes = Gtk.Template.Child()
    btn_confirm = Gtk.Template.Child()
    page_header = Gtk.Template.Child()

    _SENNA_QUOTES = _SENNA_QUOTES

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.delta = False

    def update(self, finals):
        try:
            for widget in self.active_widgets:
                self.group_changes.remove(widget)
        except AttributeError:
            pass
        self.active_widgets = []

        pretty_name = None
        selected_language = None

        for final in finals:
            for key, value in final.items():
                if key == "language":
                    selected_language = value
                    self.active_widgets.append(
                        BootcChoiceEntry(
                            _("Language"), value, "preferences-desktop-locale-symbolic"
                        )
                    )
                elif key == "keyboard":
                    self.process_keyboards(value)
                elif key == "timezone":
                    self.active_widgets.append(
                        BootcChoiceEntry(
                            _("Timezone"),
                            f"{value['region']} {value['zone']}",
                            "preferences-system-time-symbolic",
                        )
                    )
                elif key == "users":
                    self.active_widgets.append(
                        BootcChoiceEntry(
                            _("Users"),
                            f"{value['username']} ({value['fullname']})",
                            "system-users-symbolic",
                        )
                    )
                elif key == "disk":
                    if "auto" in value:
                        self.active_widgets.append(
                            BootcChoiceEntry(
                                _("Disk"),
                                f"{value['auto']['disk']} ({value['auto']['pretty_size']})",
                                "drive-harddisk-system-symbolic",
                            )
                        )
                        # Destructive action warning
                        warning = Adw.ActionRow()
                        warning.set_title(_("⚠️ ALL DATA ON THIS DISK WILL BE ERASED"))
                        warning.set_subtitle(_("This action cannot be undone"))
                        warning.add_css_class("error")
                        self.active_widgets.append(warning)
                    else:
                        disks = {}
                        # block, device_block
                        for part, info in value.items():
                            part_disk = re.match(
                                "^/dev/[a-zA-Z]+([0-9]+[a-z][0-9]+)?",
                                part,
                                re.MULTILINE,
                            )[0]
                            if part_disk not in disks:
                                disks[part_disk] = BootcChoiceExpanderEntry(
                                    _("Disk"),
                                    part_disk,
                                    "drive-harddisk-system-symbolic",
                                )
                                self.active_widgets.append(disks[part_disk])

                            disks[part_disk].add_row(
                                BootcChoiceEntry(
                                    part,
                                    f"{info['fs']} {info['mp']} ({info['pretty_size']})",
                                    "drive-harddisk-system-symbolic",
                                )
                            )
                elif key == "encryption":
                    enc_type = value.get("type", "none") if isinstance(value, dict) else str(value)
                    label = _ENC_LABELS.get(enc_type, enc_type)
                    self.active_widgets.append(
                        BootcChoiceEntry(
                            _("Encryption"),
                            label,
                            "channel-secure-symbolic",
                        )
                    )
                elif key == "hostname":
                    self.active_widgets.append(
                        BootcChoiceEntry(
                            _("Hostname"),
                            value,
                            "network-server-symbolic",
                        )
                    )
                elif key == "selected_image":
                    pn = final.get("pretty_name") or value
                    pretty_name = pn
                    self.active_widgets.append(
                        BootcChoiceEntry(
                            _("Image"),
                            pn,
                            "application-x-appliance-symbolic",
                        )
                    )
                elif key == "custom_image":
                    pn = final.get("pretty_name") or value
                    pretty_name = pn
                    self.active_widgets.append(
                        BootcChoiceEntry(
                            _("Image"),
                            value,
                            "image-missing-symbolic"
                        )
                    )

        # Hardware-detected GPU badge (always shown if a GPU is found)
        from bootc_installer.core.system import Systeminfo
        gpu_label = Systeminfo.gpu_display_string()
        if gpu_label:
            gpu_icon = Systeminfo.gpu_icon_name()
            self.active_widgets.append(
                BootcChoiceEntry(
                    _("Graphics"),
                    gpu_label,
                    gpu_icon,
                )
            )

        # Locale-specific quote: Senna for pt_BR, Zavala otherwise
        import random
        if selected_language and selected_language.startswith("pt_BR"):
            self.page_header.subtitle = random.choice(self._SENNA_QUOTES)
        else:
            self.page_header.subtitle = _("\"Indeed.\" — Commander Zavala")

        self.btn_confirm.set_label(_("( Become Legend )"))

        for widget in self.active_widgets:
            self.group_changes.add(widget)

        self._btn_confirm_signal = self.btn_confirm.connect(
            "clicked", self.__on_confirm
        )

    def test_auto_advance(self):
        self.btn_confirm.emit("clicked")

    def __on_confirm(self, widget):
        self.emit("installation-confirmed")
        self.btn_confirm.disconnect(self._btn_confirm_signal)

    def process_keyboards(self, selected_keyboards):
        keyboard_index = ""
        if len(selected_keyboards) > 1:
           keyboard_index = 0 
        for i in selected_keyboards:
            value = i["layout"]
            if i["variant"] != "":
                value = f"{i['layout']}+{i['variant']}"
            if len(selected_keyboards) > 1:
                keyboard_index += 1
            self.active_widgets.append(
                BootcChoiceEntry(
                    _(f"Keyboard {keyboard_index}"), value,"input-keyboard-symbolic"
                )
            )
