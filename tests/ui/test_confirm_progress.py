"""GTK integration tests for confirm.py and progress.py."""

import json
from unittest.mock import patch

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib  # noqa: E402

from bootc_installer.widgets.page_header import BootcPageHeader  # noqa: F401, E402
from bootc_installer.views.confirm import BootcConfirm  # noqa: E402
from bootc_installer.views.progress import BootcProgress  # noqa: E402


def _pump():
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


class _DummyWindow:
    def __init__(self):
        self.results = []

    def set_installation_result(self, *args):
        self.results.append(args)


class _ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, **_kwargs):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class TestConfirmScreen:
    def test_update_renders_summary_rows_and_pt_br_quote(self):
        confirm = BootcConfirm(object())
        finals = [
            {"language": "pt_BR.UTF-8"},
            {"keyboard": [{"layout": "us", "variant": ""}, {"layout": "br", "variant": "abnt2"}]},
            {"timezone": {"region": "America", "zone": "Sao_Paulo"}},
            {"users": {"username": "jorge", "fullname": "Jorge Castro"}},
            {"disk": {"auto": {"disk": "/dev/nvme0n1", "pretty_size": "1 TB"}}},
            {"encryption": {"type": "tpm2-luks-passphrase"}},
            {"hostname": "legendary-box"},
            {"selected_image": "ghcr.io/projectbluefin/bluefin:latest", "pretty_name": "Bluefin GTS"},
        ]

        with (
            patch("bootc_installer.core.system.Systeminfo.gpu_display_string", return_value="AMD Radeon"),
            patch("bootc_installer.core.system.Systeminfo.gpu_icon_name", return_value="video-display-symbolic"),
            patch("random.choice", return_value='"Go beyond it." — Ayrton Senna'),
        ):
            confirm.update(finals)

        rows = {(widget.get_title(), widget.get_subtitle()) for widget in confirm.active_widgets}
        assert confirm.page_header.subtitle == '"Go beyond it." — Ayrton Senna'
        assert confirm.btn_confirm.get_label() == "( Become Legend )"
        assert ("Language", "pt_BR.UTF-8") in rows
        assert ("Keyboard 1", "us") in rows
        assert ("Keyboard 2", "br+abnt2") in rows
        assert ("Timezone", "America Sao_Paulo") in rows
        assert ("Users", "jorge (Jorge Castro)") in rows
        assert ("Disk", "/dev/nvme0n1 (1 TB)") in rows
        assert ("Encryption", "Hardware-backed + passphrase fallback") in rows
        assert ("Hostname", "legendary-box") in rows
        assert ("Image", "Bluefin GTS") in rows
        assert ("Graphics", "AMD Radeon") in rows
        assert (
            "⚠️ ALL DATA ON THIS DISK WILL BE ERASED",
            "This action cannot be undone",
        ) in rows

    def test_confirm_button_emits_signal_once_and_defaults_to_zavala(self):
        confirm = BootcConfirm(object())
        seen = []

        with patch("bootc_installer.core.system.Systeminfo.gpu_display_string", return_value=""):
            confirm.update([{"language": "en_US"}])

        confirm.connect("installation-confirmed", lambda *_args: seen.append("confirmed"))
        confirm.test_auto_advance()
        _pump()
        confirm.test_auto_advance()
        _pump()

        assert confirm.page_header.subtitle == '"Indeed." — Commander Zavala'
        assert seen == ["confirmed"]


class TestProgressScreen:
    def _make_progress(self):
        window = _DummyWindow()
        with (
            patch("bootc_installer.views.progress.threading.Thread", _ImmediateThread),
            patch("bootc_installer.views.progress.GLib.timeout_add_seconds", return_value=1),
        ):
            progress = BootcProgress(window)
            _pump()
        return progress, window

    def test_media_and_console_toggles_preserve_selected_media_mode(self):
        progress, _window = self._make_progress()

        assert not progress.console_box.get_visible()
        assert progress.media_box.get_visible()

        progress.console_button.emit("clicked")
        _pump()
        assert progress.console_box.get_visible()
        assert progress.media_button.get_visible()
        assert not progress.console_button.get_visible()
        assert not progress.media_box.get_visible()

        progress.media_button.emit("clicked")
        _pump()
        assert not progress.console_box.get_visible()
        assert not progress.media_button.get_visible()
        assert progress.console_button.get_visible()
        assert progress.media_box.get_visible()

    def test_progress_events_update_labels_percentage_eta_and_completion(self):
        progress, _window = self._make_progress()
        progress._BootcProgress__start_time = 100.0

        with patch("bootc_installer.views.progress.time.monotonic", return_value=220.0):
            progress._BootcProgress__update_elapsed_label()
            progress._BootcProgress__parse_progress_line(
                json.dumps(
                    {
                        "type": "step",
                        "step": 6,
                        "total_steps": 9,
                        "step_name": "Installing system image",
                        "cumulative_pct": 55,
                        "weight_pct": 22,
                    }
                )
            )
            progress._BootcProgress__parse_progress_line(
                json.dumps({"type": "substep", "message": "Pulling image: layer 5/10"})
            )

        assert progress.progressbar_text.get_label() == (
            "Step 6/9: Installing system image — Pulling image: layer 5/10"
        )
        assert progress.progress_percentage.get_label() == "66%"
        assert progress.progress_elapsed.get_label() == "2:00 elapsed"
        assert progress.progress_eta.get_label().startswith("~")
        assert "remaining" in progress.progress_eta.get_label()
        assert progress.progress_substep.get_label() == "Pulling image: layer 5/10"

        progress._BootcProgress__parse_progress_line(
            json.dumps({"type": "complete", "boot_id": "boot-123", "recovery_key": "rk-1"})
        )

        assert progress.progressbar_text.get_label() == "Installation complete!"
        assert progress.progress_percentage.get_label() == "100%"
        assert progress.progress_substep.get_label() == ""
        assert progress._BootcProgress__boot_id == "boot-123"
        assert progress._BootcProgress__recovery_key == "rk-1"

    def test_demo_mode_completes_and_reports_success(self):
        progress, window = self._make_progress()

        def _run_now(_delay, callback, *args):
            callback(*args)
            return 1

        with patch("bootc_installer.views.progress.GLib.timeout_add", side_effect=_run_now):
            progress.start_demo()

        assert progress.progressbar_text.get_label() == "Installation complete!"
        assert progress.progress_percentage.get_label() == "100%"
        assert window.results == [(True, None, "")]
