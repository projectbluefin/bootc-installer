import logging
from gettext import gettext as _

from gi.repository import Adw, Gdk, GLib, GObject, Gtk

logger = logging.getLogger("Installer::RecoveryKey")

_PLACEHOLDER_KEY = _("Recovery key will be displayed here once the installer reports it.")


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/recovery-key.ui")
class BootcRecoveryKey(Adw.Bin):
    __gtype_name__ = "BootcRecoveryKey"
    __gsignals__ = {
        "recovery-key-acknowledged": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    key_label = Gtk.Template.Child()
    copy_button = Gtk.Template.Child()
    ack_check = Gtk.Template.Child()
    btn_continue = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.delta = False
        self.btn_continue.set_sensitive(False)
        self.copy_button.connect("clicked", self.__on_copy)
        self.ack_check.connect("toggled", self.__on_ack_toggled)
        self.btn_continue.connect("clicked", self.__on_continue)
        self.set_recovery_key("")

    def set_recovery_key(self, key: str):
        key = (key or "").strip()
        has_key = bool(key)
        self.key_label.set_label(key or _PLACEHOLDER_KEY)
        self.copy_button.set_sensitive(has_key)
        self.copy_button.set_icon_name("edit-copy-symbolic")
        self.ack_check.set_active(False)
        self.btn_continue.set_sensitive(False)

    def __on_copy(self, *args):
        if not self.copy_button.get_sensitive():
            return
        display = Gdk.Display.get_default()
        if display is None:
            return

        clipboard = display.get_clipboard()
        clipboard.set(self.key_label.get_label())
        self.copy_button.set_icon_name("emblem-ok-symbolic")

        def _reset_icon():
            self.copy_button.set_icon_name("edit-copy-symbolic")
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(1500, _reset_icon)

    def __on_ack_toggled(self, check):
        self.btn_continue.set_sensitive(check.get_active())

    def __on_continue(self, *args):
        self.emit("recovery-key-acknowledged")
