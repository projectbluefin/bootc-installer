import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

from bootc_installer.views.done import BootcDone  # noqa: E402
from bootc_installer.windows.dialog_credits import BootcCreditsWindow  # noqa: E402

_CREDITS_JSON = (
    Path(__file__).resolve().parents[2] / "bootc_installer" / "data" / "credits.json"
)


def _pump():
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


def _children(widget):
    child = widget.get_first_child()
    children = []
    while child is not None:
        children.append(child)
        child = child.get_next_sibling()
    return children


@pytest.fixture()
def host_window():
    window = Gtk.Window()
    window.present()
    _pump()
    yield window
    window.destroy()
    _pump()


def _make_done(window):
    controller = SimpleNamespace(
        recipe={"distro_name": "Bluefin", "store_url": "https://example.com"},
        close=MagicMock(),
        on_installation_confirmed=MagicMock(),
    )
    widget = BootcDone(controller)
    window.set_child(widget)
    _pump()
    return widget, controller


class TestDoneScreen:
    def test_success_result_updates_header_and_store_visibility(self, host_window):
        done, controller = _make_done(host_window)
        controller.pretty_name = "Bluefin DX"

        with patch.object(
            BootcDone, "_BootcDone__is_us_locale", return_value=True
        ):
            done.set_result(True, terminal=object(), elapsed_secs=125)

        assert done.page_header.title == "Bluefin DX is installed"
        assert (
            done.page_header.subtitle
            == "Installed in 2:05. Restart to begin your new experience."
        )
        assert done.btn_reboot.get_visible()
        assert not done.btn_close.get_visible()
        assert not done.btn_retry.get_visible()
        assert done.store_group.get_visible()

    def test_failure_result_shows_retry_controls_and_hint(self, host_window):
        done, _controller = _make_done(host_window)

        with patch.object(
            done,
            "_BootcDone__extract_failure_hint",
            return_value="Check your network and try again.",
        ):
            done.set_result(False, terminal=object())

        assert done.page_header.icon_name == "dialog-error-symbolic"
        assert done.page_header.title == "Installation failed"
        assert done.page_header.subtitle == "Check your network and try again."
        assert not done.btn_reboot.get_visible()
        assert done.btn_close.get_visible()
        assert done.btn_retry.get_visible()
        assert done.btn_log.has_css_class("suggested-action")

    def test_failure_result_uses_log_fallback_copy_when_hint_is_unavailable(
        self, host_window
    ):
        done, _controller = _make_done(host_window)

        with patch(
            "bootc_installer.views.progress._FISHERMAN_LOG_PATH",
            "/path/that/does/not/exist.log",
        ):
            done.set_result(False, terminal=object())

        assert (
            done.page_header.subtitle
            == "Check the log for details. Click 'Show Log' below."
        )
        assert done.btn_log.get_visible()
        assert done.btn_log.has_css_class("suggested-action")

    def test_retry_failure_then_success_resets_failure_only_controls(
        self, host_window
    ):
        done, controller = _make_done(host_window)
        controller.pretty_name = "Bluefin DX"

        with patch.object(
            done,
            "_BootcDone__extract_failure_hint",
            return_value="Pull failed.",
        ):
            done.set_result(False, terminal=object())

        with patch.object(
            BootcDone, "_BootcDone__is_us_locale", return_value=False
        ):
            done.set_result(True, terminal=object(), elapsed_secs=9)

        assert done.page_header.icon_name == "object-select-symbolic"
        assert done.page_header.title == "Bluefin DX is installed"
        assert (
            done.page_header.subtitle
            == "Installed in 0:09. Restart to begin your new experience."
        )
        assert done.btn_reboot.get_visible()
        assert not done.btn_close.get_visible()
        assert not done.btn_retry.get_visible()
        assert not done.btn_log.has_css_class("suggested-action")
        assert not done.store_group.get_visible()

    def test_buttons_call_window_actions_and_show_log_dialog(self, host_window):
        done, controller = _make_done(host_window)

        with patch("bootc_installer.views.done.BootcDialogOutput") as dialog_cls:
            dialog = dialog_cls.return_value

            done.btn_retry.emit("clicked")
            done.btn_close.emit("clicked")
            done.btn_log.emit("clicked")
            _pump()

        controller.on_installation_confirmed.assert_called_once_with()
        controller.close.assert_called_once_with()
        dialog_cls.assert_called_once_with(controller)
        dialog.present.assert_called_once_with()


class TestCreditsWindow:
    def test_populates_header_sections_and_cards(self, host_window):
        data = json.loads(_CREDITS_JSON.read_text())
        credits = BootcCreditsWindow(host_window)

        assert credits.header_title.get_label() == data["header"]["title"]
        assert credits.header_subtitle.get_label() == data["header"]["subtitle"]
        assert credits.header_quote.get_label() == (
            f'{data["header"]["quote"]}\n— {data["header"]["quote_author"]}'
        )
        assert len(_children(credits.sections_box)) == len(data["sections"])

        first_section = _children(credits.sections_box)[0]
        section_box = first_section.get_child()
        section_children = _children(section_box)
        first_member = data["sections"][0]["members"][0]

        assert section_children[0].get_label() == data["sections"][0]["title"]
        assert section_children[1].get_label() == data["sections"][0]["subtitle"]

        flow_children = _children(section_children[2])
        assert len(flow_children) == len(data["sections"][0]["members"])

        first_card = flow_children[0].get_child().get_child()
        card_children = _children(first_card)
        info_labels = [
            child.get_label() for child in _children(card_children[1])
        ]

        assert card_children[0].get_label() == first_member["handle"][0].upper()
        assert info_labels == [
            first_member["handle"],
            first_member["title"],
            f'"{first_member["nickname"]}"',
        ]

        credits.destroy()
        _pump()

    def test_falls_back_when_credits_data_is_missing(self, host_window):
        class BrokenResourceFile:
            def load_contents(self, _cancellable):
                raise FileNotFoundError("missing resource")

        with patch(
            "bootc_installer.windows.dialog_credits.Gio.File.new_for_uri",
            return_value=BrokenResourceFile(),
        ), patch(
            "bootc_installer.windows.dialog_credits.os.path.exists",
            return_value=False,
        ), patch(
            "builtins.open",
            side_effect=FileNotFoundError("missing file"),
        ):
            credits = BootcCreditsWindow(host_window)

        assert credits.header_title.get_label() == "Credits"
        assert credits.header_subtitle.get_label() == "Data not available"
        assert len(_children(credits.sections_box)) == 0

        credits.destroy()
        _pump()
