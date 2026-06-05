import logging
import os
import subprocess
import threading
import time
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from bootc_installer.utils.pastry_compat import wrap_glass
from bootc_installer.widgets.page_header import BootcPageHeader  # noqa: F401
from bootc_installer.windows.dialog_output import BootcDialogOutput

logger = logging.getLogger("Installer::Done")
log = logger


def apply_icon(page_header, icon_spec):
    """Set the page header icon from a resource:// URI or an icon-theme name."""
    try:
        if icon_spec.startswith("resource://"):
            resource_path = icon_spec[len("resource://"):]
            page_header.set_from_resource(resource_path)
        else:
            page_header.icon_name = icon_spec
    except Exception as e:
        log.warning("Could not apply icon %r: %s", icon_spec, e)


def warmup_registry(image_ref: str):
    """Fire a skopeo inspect to warm DNS, TLS, and CDN routing for the registry.

    Called in a daemon thread 30 seconds after install success. Does not write
    to the target disk (which is finalized/frozen after install).
    """
    try:
        result = subprocess.run(
            ["skopeo", "inspect", f"docker://{image_ref}"],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0:
            log.info("Registry warmup succeeded for %s", image_ref)
        else:
            log.debug("Registry warmup exited %d for %s: %s",
                      result.returncode, image_ref,
                      result.stderr.decode(errors="replace").strip()[:200])
    except FileNotFoundError:
        log.debug("skopeo not available — registry warmup skipped")
    except subprocess.TimeoutExpired:
        log.debug("Registry warmup timed out for %s", image_ref)
    except Exception as e:
        log.debug("Registry warmup failed for %s: %s", image_ref, e)


def do_reboot(in_flatpak):
    """Attempt to reboot. Returns True if a reboot command succeeded."""
    # Preferred: logind D-Bus — works correctly from inside the Flatpak
    # sandbox and handles polkit transparently.
    try:
        conn = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        conn.call_sync(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            "Reboot",
            GLib.Variant("(b)", (False,)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return True
    except Exception as e:
        log.warning("logind D-Bus reboot failed: %s", e)

    # Fallback: spawn systemctl / reboot on the host.
    cmds = [["systemctl", "reboot"], ["reboot"]]
    for cmd in cmds:
        argv = (["flatpak-spawn", "--host"] + cmd) if in_flatpak else cmd
        try:
            result = subprocess.run(argv, capture_output=True)
            if result.returncode == 0:
                return True
            log.warning("%s exited %d: %s", argv, result.returncode, result.stderr.decode())
        except Exception as e:
            log.warning("%s failed: %s", argv, e)

    return False


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/done.ui")
class BootcDone(Adw.Bin):
    __gtype_name__ = "BootcDone"

    page_header = Gtk.Template.Child()
    btn_reboot = Gtk.Template.Child()
    btn_close = Gtk.Template.Child()
    btn_log = Gtk.Template.Child()
    btn_retry = Gtk.Template.Child()
    store_group = Gtk.Template.Child()
    store_qr = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__log = None
        self.__boot_id = ""
        self.delta = False

        self.btn_reboot.connect("clicked", self.__on_reboot_clicked)
        self.btn_close.connect("clicked", self.__on_close_clicked)
        self.btn_log.connect("clicked", self.__on_log_clicked)
        self.btn_retry.connect("clicked", self.__on_retry_clicked)
        self.__wrap_store_qr()

    def __wrap_store_qr(self):
        parent = self.store_qr.get_parent()
        if parent is None:
            return

        try:
            parent.remove(self.store_qr)
        except Exception:
            return

        parent.prepend(wrap_glass(self.store_qr))

    def set_result(self, result, terminal, boot_id="", elapsed_secs=0, image_ref=None):
        self.__terminal = terminal
        self.__boot_id = boot_id

        if result:
            self.page_header.icon_name = "object-select-symbolic"
            pretty_name = getattr(self.__window, "pretty_name", None) \
                or self.__window.recipe.get("distro_name", "the operating system")
            self.page_header.title = _("{} is installed").format(pretty_name)
            if elapsed_secs > 0:
                minutes, secs = divmod(elapsed_secs, 60)
                time_str = f"{minutes}:{secs:02d}"
                self.page_header.subtitle = _("Installed in %s. Restart to begin your new experience.") % time_str
            else:
                self.page_header.subtitle = _("Restart now to complete the installation.")
            icon_spec = getattr(self.__window, "selected_icon", None)
            if icon_spec:
                apply_icon(self.page_header, icon_spec)
            self.btn_reboot.set_visible(True)
            self.btn_close.set_visible(False)
            self.btn_retry.set_visible(False)
            self.btn_log.remove_css_class("suggested-action")
            # Show store widget for US users
            self.store_group.set_visible(False)
            self.__maybe_show_store()
            # Warm the registry connection in the background after 30 seconds.
            # The target disk is finalized (ro + frozen), so we cannot write to it.
            # This fires a skopeo inspect to warm DNS, TLS, and CDN routing so
            # the first `bootc upgrade` after reboot finds a hot connection.
            if image_ref:
                GLib.timeout_add_seconds(30, self.__schedule_registry_warmup, image_ref)
        else:
            self.page_header.icon_name = "dialog-error-symbolic"
            self.page_header.title = _("Installation failed")
            # Try to extract the last failed step from the log for a helpful message
            hint = self.__extract_failure_hint()
            self.page_header.subtitle = hint
            self.store_group.set_visible(False)
            self.btn_reboot.set_visible(False)
            self.btn_close.set_visible(True)
            self.btn_retry.set_visible(True)
            # Show the log button prominently on failure
            self.btn_log.add_css_class("suggested-action")

    def __schedule_registry_warmup(self, image_ref: str) -> bool:
        """Fire off a background thread to warm the registry connection.
        Runs 30 seconds after install success. Does not write to the target disk.
        """
        log.info("Scheduling registry warmup for %s", image_ref)
        t = threading.Thread(
            target=warmup_registry,
            args=(image_ref,),
            daemon=True,
        )
        t.start()
        return False  # don't repeat the GLib timer

    def __registry_warmup_worker(self, image_ref: str):
        """Alias kept for back-compat — delegates to module-level warmup_registry."""
        warmup_registry(image_ref)

    def __extract_failure_hint(self) -> str:
        """Read the fisherman log to determine what failed and suggest a fix."""
        from bootc_installer.views.progress import _FISHERMAN_LOG_PATH
        try:
            with open(_FISHERMAN_LOG_PATH) as f:
                lines = f.readlines()
        except OSError:
            return _("Check the log for details. Click 'Show Log' below.")

        # Find the last "fatal:" line from fisherman
        fatal_msg = ""
        for line in lines:
            if "fatal:" in line.lower():
                fatal_msg = line.strip()

        if not fatal_msg:
            return _("The installer exited unexpectedly. Check the log for details.")

        # Provide actionable hints based on common failure patterns
        lower = fatal_msg.lower()
        if "not found in path" in lower or "missing required host tool" in lower:
            return _("A required system tool is missing. Ensure you are running from the official live media.")
        if "network" in lower or "pull" in lower or "timeout" in lower or "registry" in lower:
            return _("Network error during image download. Check your internet connection and try again.")
        if "no space" in lower or "enospc" in lower:
            return _("Not enough disk space. Select a larger disk or free up space.")
        if "permission" in lower or "denied" in lower:
            return _("Permission denied. The installer needs administrator access to proceed.")
        if "luks" in lower or "cryptsetup" in lower:
            return _("Disk encryption setup failed. Try disabling encryption or check your passphrase.")
        if "partition" in lower or "sfdisk" in lower:
            return _("Disk partitioning failed. The disk may be in use or damaged.")
        if "mount" in lower:
            return _("Filesystem mount failed. The disk may be in use by another process.")

        # Generic fallback with the actual error
        short_msg = fatal_msg.split("fatal:")[-1].strip()[:120]
        return _("Error: {}").format(short_msg)

    def __on_reboot_clicked(self, button):
        in_flatpak = os.path.exists("/.flatpak-info")

        if self.__boot_id:
            # Set BootNext so the firmware boots the newly installed drive on
            # the next boot, even if the install media is still plugged in.
            try:
                if in_flatpak:
                    subprocess.run(
                        ["flatpak-spawn", "--host", "efibootmgr", "--bootnext", self.__boot_id],
                        check=True,
                    )
                else:
                    subprocess.run(["efibootmgr", "--bootnext", self.__boot_id], check=True)
            except Exception as e:
                # Non-fatal — the user can always pick the right entry in the
                # BIOS/UEFI boot menu if this fails.
                log.warning("Could not set BootNext to %s: %s", self.__boot_id, e)

        if not do_reboot(in_flatpak):
            self.__show_reboot_error()

    def __show_reboot_error(self):
        dialog = Adw.AlertDialog.new(
            _("Could not reboot"),
            _("Please reboot manually by running: systemctl reboot"),
        )
        dialog.add_response("ok", _("OK"))
        dialog.present(self)

    def __on_close_clicked(self, button):
        self.__window.close()

    def __on_retry_clicked(self, button):
        """Navigate back to confirm screen and re-trigger install."""
        self.__window.on_installation_confirmed()

    def __on_log_clicked(self, button):
        dialog = BootcDialogOutput(self.__window)
        dialog.present()

    def __maybe_show_store(self):
        """Show the merch store QR code for US-locale users only.

        Requires ``store_url`` in the recipe. The QR image is loaded from
        ``store_qr_resource`` (a GResource path) if provided, otherwise falls
        back to the built-in ``assets/store-qr.svg``.  If ``store_url`` is
        absent the widget stays hidden regardless of locale.
        """
        store_url = self.__window.recipe.get("store_url", "")
        if not store_url:
            return
        if not self.__is_us_locale():
            return
        qr_resource = self.__window.recipe.get(
            "store_qr_resource",
            "/org/bootcinstaller/Installer/assets/store-qr.svg",
        )
        try:
            self.store_qr.set_resource(qr_resource)
            self.store_group.set_visible(True)
        except Exception as e:
            log.debug("Could not load store QR: %s", e)

    @staticmethod
    def __is_us_locale() -> bool:
        """Detect US locale via language or timezone."""
        # Check LANG / LC_ALL for US English
        lang = os.environ.get("LANG", "") + os.environ.get("LC_ALL", "")
        if "en_US" in lang:
            return True
        # Check timezone — US zones
        try:
            tz = time.tzname[0] if time.tzname else ""
            us_zones = {"EST", "EDT", "CST", "CDT", "MST", "MDT", "PST", "PDT", "AKST", "AKDT", "HST"}
            if tz in us_zones:
                return True
        except Exception as e:
            log.debug("Could not read timezone name: %s", e)
        # Check /etc/timezone or timedatectl output
        try:
            with open("/etc/timezone") as f:
                tz_file = f.read().strip()
            if tz_file.startswith("America/") or tz_file.startswith("US/"):
                return True
        except OSError:
            pass
        return False
