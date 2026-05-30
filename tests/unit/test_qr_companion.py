import sys
import types
import threading
import json
import urllib.request
from unittest.mock import MagicMock, patch
import pytest

from bootc_installer.utils.phone_companion import (
    get_local_ip,
    CompanionServer,
    CONFIG_RECEIVED_EVENT
)

def _build_gi_stubs():
    """Build headless stubs for Adw and Gtk to run tests without a display."""
    class _StubBin:
        def __init__(self, *args, **kwargs):
            pass
        def append(self, widget):
            pass
        def set_child(self, widget):
            pass
        def set_valign(self, val):
            pass
        def set_halign(self, val):
            pass
        def set_margin_top(self, val):
            pass
        def set_margin_bottom(self, val):
            pass
        def set_margin_start(self, val):
            pass
        def set_margin_end(self, val):
            pass
        def set_title(self, val):
            pass
        def set_icon_name(self, val):
            pass
        def set_description(self, val):
            pass
        def set_pixel_size(self, val):
            pass
        def set_use_markup(self, val):
            pass
        def add_css_class(self, val):
            pass
        def set_markup(self, val):
            pass
        def set_from_file(self, val):
            pass
        def set_from_icon_name(self, val):
            pass
        def connect(self, signal, callback, *args):
            pass

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    class _Align:
        CENTER = "center"
    class _Orientation:
        VERTICAL = "vertical"
        HORIZONTAL = "horizontal"
    gtk_mod.Align = _Align
    gtk_mod.Orientation = _Orientation
    gtk_mod.Box = _StubBin
    gtk_mod.Image = _StubBin
    gtk_mod.Label = _StubBin
    gtk_mod.Button = _StubBin

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = _StubBin
    adw_mod.StatusPage = _StubBin

    sys.modules["gi.repository.Gtk"] = gtk_mod
    sys.modules["gi.repository.Adw"] = adw_mod
    
    # Mock GLib
    glib_mock = MagicMock()
    sys.modules["gi.repository.GLib"] = glib_mock
    
    # Mock Gio
    gio_mock = MagicMock()
    sys.modules["gi.repository.Gio"] = gio_mock

    # Setup gi parent modules
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")
    repo_mod.Gtk = gtk_mod
    repo_mod.Adw = adw_mod
    repo_mod.GLib = glib_mock
    repo_mod.Gio = gio_mock
    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod

def test_get_local_ip():
    """Verify that get_local_ip returns a valid, non-empty string IP address."""
    ip = get_local_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0

def test_companion_server_lifecycle_and_api():
    """Verify that the background companion server can serve requests and handle configuration posting."""
    # Force HTTP mode by patching generate_self_signed_cert to return False
    with patch("bootc_installer.utils.phone_companion.generate_self_signed_cert", return_value=False):
        server = CompanionServer(port=18443)
        server.start()
        
        try:
            # 1. Test GET / to retrieve captive portal HTML
            url = "http://127.0.0.1:18443/"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as response:
                html = response.read().decode('utf-8')
                assert "Dakota Setup" in html
                assert response.status == 200
                
            # 2. Test POST /api/config with JSON configuration payload
            config_data = {
                "fullname": "John Doe",
                "username": "johndoe",
                "password": "mypassword",
                "hostname": "test-host",
                "sshkey": "ssh-rsa ABC"
            }
            
            post_url = "http://127.0.0.1:18443/api/config"
            post_req = urllib.request.Request(
                post_url, 
                data=json.dumps(config_data).encode('utf-8'),
                headers={"Content-Type": "application/json"}
            )
            
            with urllib.request.urlopen(post_req, timeout=2) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                assert res_data["status"] == "success"
                assert response.status == 200
                
            # 3. Verify global state and events were successfully updated
            assert CONFIG_RECEIVED_EVENT.is_set()
            from bootc_installer.utils.phone_companion import GLOBAL_CONFIG
            assert GLOBAL_CONFIG["fullname"] == "John Doe"
            assert GLOBAL_CONFIG["username"] == "johndoe"
            assert GLOBAL_CONFIG["password"] == "mypassword"
            assert GLOBAL_CONFIG["hostname"] == "test-host"
            assert GLOBAL_CONFIG["sshkey"] == "ssh-rsa ABC"
            
        finally:
            server.stop()

def test_qr_companion_step_lifecycle():
    """Verify the GUI companion step parses contexts, skips, and resolves finals cleanly."""
    _build_gi_stubs()
    
    window_mock = MagicMock()
    carousel_mock = MagicMock()
    window_mock.carousel = carousel_mock
    
    distro_info = {}
    step = {"num": 2}
    
    # Reload step module cleanly
    sys.modules.pop("bootc_installer.defaults.qr_companion", None)
    from bootc_installer.defaults.qr_companion import BootcDefaultQrCompanion
    
    step_widget = BootcDefaultQrCompanion(window_mock, distro_info, "qr_companion", step)
    
    assert step_widget.step_id == "qr_companion"
    assert step_widget.should_show({}) is True
    
    # Test get_finals when no configuration has been received yet
    window_mock.companion_config = None
    assert step_widget.get_finals() == {}
    
    # Test get_finals when configuration has been populated from phone
    window_mock.companion_config = {
        "fullname": "John Doe",
        "username": "johndoe",
        "password": "mypassword",
        "hostname": "test-host",
        "sshkey": "ssh-rsa ABC"
    }
    assert step_widget.get_finals() == {
        "hostname": "test-host"
    }
