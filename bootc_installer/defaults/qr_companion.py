import logging
import os
import pathlib
import tempfile
from gettext import gettext as _
from gi.repository import Adw, GLib, Gtk, Gio

from bootc_installer.utils.run_async import RunAsync
from bootc_installer.utils.phone_companion import (
    CompanionServer,
    get_local_ip,
    CONFIG_RECEIVED_EVENT,
    GLOBAL_CONFIG
)

try:
    import segno
except ImportError:
    segno = None

logger = logging.getLogger("BootcInstaller::QrCompanion")

class BootcDefaultQrCompanion(Adw.Bin):
    def __init__(self, window, distro_info, key, step, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__key = key
        self.__step = step
        self.__step_num = step["num"]
        self.delta = False
        self.__server = None
        self.__timeout_id = None
        
        # Add companion_config placeholder on window
        if not hasattr(self.__window, "companion_config"):
            self.__window.companion_config = None

        # Build UI Programmatically to avoid needing new .blp/.ui templates
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.main_box.set_valign(Gtk.Align.CENTER)
        self.main_box.set_halign(Gtk.Align.CENTER)
        self.main_box.set_margin_top(48)
        self.main_box.set_margin_bottom(48)
        self.main_box.set_margin_start(24)
        self.main_box.set_margin_end(24)
        
        # Header Status Page
        self.status_page = Adw.StatusPage()
        self.status_page.set_title(_("Phone Companion Setup"))
        self.status_page.set_icon_name("phone-symbolic")
        self.status_page.set_description(_(
            "Scan the QR code below with your phone to configure the installer settings.\n"
            "Both devices must be on the same local network."
        ))
        self.main_box.append(self.status_page)
        
        # QR Code Image Container
        self.qr_image = Gtk.Image()
        self.qr_image.set_pixel_size(200)
        self.main_box.append(self.qr_image)
        
        # Link Label
        self.link_label = Gtk.Label()
        self.link_label.set_use_markup(True)
        self.link_label.add_css_class("title-3")
        self.main_box.append(self.link_label)
        
        # Waiting status & Skip Button Horizontal Box
        self.actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.actions_box.set_halign(Gtk.Align.CENTER)
        
        self.waiting_label = Gtk.Label(label=_("Waiting for phone configuration..."))
        self.waiting_label.add_css_class("dim-label")
        self.actions_box.append(self.waiting_label)
        
        self.btn_next = Gtk.Button(label=_("Skip Companion Setup"))
        self.btn_next.add_css_class("suggested-action")
        self.btn_next.connect("clicked", self.__on_skip_clicked)
        self.actions_box.append(self.btn_next)
        
        self.main_box.append(self.actions_box)
        self.set_child(self.main_box)
        
        # Listen for page change events to start/stop the server
        self.__window.carousel.connect("page-changed", self.__on_page_changed)

    @property
    def step_id(self):
        return self.__key

    def should_show(self, context: dict) -> bool:
        # Show this setup page if it is configured in the recipe
        return True

    def get_finals(self):
        # Feed Hostname and SSH Key to the recipe processor if provided
        companion_config = getattr(self.__window, "companion_config", None)
        if companion_config:
            finals = {}
            if "hostname" in companion_config:
                finals["hostname"] = companion_config["hostname"]
            return finals
        return {}

    def __on_page_changed(self, carousel, idx):
        # Check if we transitioned into this step page
        if int(idx) == self.__step_num - 1:
            self.__start_companion()
        else:
            self.__stop_companion()

    def test_auto_advance(self):
        """Simulate programmatic advance for UI integration tests."""
        self.__stop_companion()
        self.__window.next()

    def __start_companion(self):
        if self.__server is not None:
            return
            
        logger.info("Initializing Phone Companion server...")
        self.__server = CompanionServer(port=8443)
        self.__server.start()
        
        ip = get_local_ip()
        protocol = "https" if self.__server.is_https else "http"
        url = f"{protocol}://{ip}:8443"
        self.link_label.set_markup(f'<a href="{url}">{url}</a>')
        
        # Generate QR code SVG on the fly
        if segno is not None:
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".svg", delete=False)
                qr = segno.make_qr(url)
                qr.save(tmp.name, scale=6, dark="white", light="#1e1e2e")
                tmp.close()
                self.qr_image.set_from_file(tmp.name)
                logger.info("Generated QR Code for companion URL.")
            except Exception as e:
                logger.error("Failed to generate QR Code SVG: %s", e)
                self.qr_image.set_from_icon_name("dialog-question-symbolic")
        else:
            logger.warning("segno is not available. Displaying URL link text only.")
            self.qr_image.set_from_icon_name("network-wired-symbolic")
            
        # Start GLib polling loop to check for received config
        self.__timeout_id = GLib.timeout_add(500, self.__check_config_event)

    def __stop_companion(self):
        if self.__timeout_id:
            GLib.source_remove(self.__timeout_id)
            self.__timeout_id = None
            
        if self.__server:
            self.__server.stop()
            self.__server = None
            logger.info("Shut down Phone Companion server.")

    def __check_config_event(self):
        if CONFIG_RECEIVED_EVENT.is_set():
            logger.info("Received configuration from Phone Companion!")
            from bootc_installer.utils.phone_companion import GLOBAL_CONFIG
            
            # Save config to window state
            self.__window.companion_config = GLOBAL_CONFIG
            
            # Auto-advance to the next page
            GLib.idle_add(self.__window.next)
            
            self.__stop_companion()
            return False # Stop the polling loop
            
        return True # Continue polling

    def __on_skip_clicked(self, btn):
        logger.info("Companion setup skipped by the user.")
        self.__stop_companion()
        self.__window.next()
