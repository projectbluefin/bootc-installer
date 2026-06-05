# progress.py
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

import io
import json
import logging
import os
import pathlib
import shutil
import stat
import subprocess
import threading
import time
from gettext import gettext as _

logger = logging.getLogger("Installer::Progress")

_IN_FLATPAK = os.path.exists("/.flatpak-info")
_LIVE_ISO = not _IN_FLATPAK and os.path.exists("/run/ostree-booted")
_RESOURCE_PREFIX = "/org/bootcinstaller/Installer"
_ASSET_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets"
_TRACK_QR_DIR = _ASSET_DIR / "qr"
_TRACK_COVER_DIR = _ASSET_DIR / "covers"

# Where to stage fisherman so the host can see it (shared via --filesystem=host)
_FISHERMAN_CACHE_DIR = os.path.join(os.environ.get("HOME", "/tmp"), ".cache", "bootc-installer")
_FISHERMAN_HOST_PATH = os.path.join(_FISHERMAN_CACHE_DIR, "fisherman")
_FISHERMAN_LOG_PATH = os.path.join(_FISHERMAN_CACHE_DIR, "fisherman-output.log")

from bootc_installer.utils.progress_parser import apply_progress_event, new_progress_state  # noqa: E402
from bootc_installer.utils.pastry_compat import new_grid_spinner  # noqa: E402
from bootc_installer.utils.codec_check import check_codecs_present  # noqa: E402


def _track_qr_resource_path(track: dict) -> str | None:
    qr_asset = track.get("qr_asset")
    if not qr_asset:
        return None
    return f"{_RESOURCE_PREFIX}/assets/qr/{qr_asset}"


def _track_qr_dev_path(track: dict) -> pathlib.Path | None:
    qr_asset = track.get("qr_asset")
    if not qr_asset:
        return None
    return _TRACK_QR_DIR / qr_asset


def _track_cover_dev_path(track: dict) -> pathlib.Path | None:
    cover_asset = track.get("cover_art")
    if not cover_asset:
        return None
    return _TRACK_COVER_DIR / cover_asset


def _media_stream_is_prepared(media_stream) -> bool:
    return media_stream is not None and media_stream.is_prepared()


def _fisherman_argv_direct(recipe: str) -> list:
    """Build an argv that captures fisherman stdout+stderr into the log file.

    For Flatpak: run bash on the HOST via flatpak-spawn so the shell redirect
    happens where fisherman actually runs. If we redirect inside the sandbox,
    flatpak-spawn's D-Bus proxy doesn't forward the host process stdout back
    through the redirect — the log file stays empty even though fisherman runs.
    """
    log = _FISHERMAN_LOG_PATH
    if _IN_FLATPAK:
        if os.environ.get("BOOTC_TEST"):
            bin_ = os.environ.get("BOOTC_FISHERMAN_PATH", _FISHERMAN_HOST_PATH)
            cmd = f'sudo "{bin_}" "$1" >"{log}" 2>&1; exit $?'
        else:
            cmd = f'pkexec "{_FISHERMAN_HOST_PATH}" "$1" >"{log}" 2>&1; exit $?'
        return ["flatpak-spawn", "--host", "bash", "-c", cmd, "--", recipe]
    elif _LIVE_ISO:
        return ["bash", "-c", f'sudo /usr/local/bin/fisherman "$1" >"{log}" 2>&1; exit $?', "--", recipe]
    else:
        return ["bash", "-c", f'pkexec /usr/local/bin/fisherman "$1" >"{log}" 2>&1; exit $?', "--", recipe]


def _stage_fisherman_on_host() -> bool:
    """Copy fisherman binary to a host-visible cache dir so pkexec can find it."""
    if not _IN_FLATPAK:
        return True

    os.makedirs(_FISHERMAN_CACHE_DIR, exist_ok=True)
    fisherman_src = os.environ.get("BOOTC_FISHERMAN_PATH", "/app/bin/fisherman")
    try:
        shutil.copy2(fisherman_src, _FISHERMAN_HOST_PATH)
        os.chmod(_FISHERMAN_HOST_PATH, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        logger.info(f"Staged fisherman binary to {_FISHERMAN_HOST_PATH}")
        return True
    except Exception as e:
        logger.error(f"Failed to stage fisherman binary: {e}")
        return False

from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/progress.ui")
class BootcProgress(Gtk.Box):
    __gtype_name__ = "BootcProgress"

    media_box = Gtk.Template.Child()
    soundtrack_box = Gtk.Template.Child()
    track_carousel = Gtk.Template.Child()
    install_video = Gtk.Template.Child()
    video_fallback_box = Gtk.Template.Child()
    btn_video_mode = Gtk.Template.Child()
    btn_soundtrack_mode = Gtk.Template.Child()
    progressbar = Gtk.Template.Child()
    progressbar_text = Gtk.Template.Child()
    progress_percentage = Gtk.Template.Child()
    progress_elapsed = Gtk.Template.Child()
    progress_eta = Gtk.Template.Child()
    progress_substep = Gtk.Template.Child()
    console_button = Gtk.Template.Child()
    media_button = Gtk.Template.Child()
    console_box = Gtk.Template.Child()
    log_view = Gtk.Template.Child()
    copy_log_button = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__proc = None       # subprocess handle for fisherman
        self.__log_out = None    # open file handle for fisherman stdout/stderr
        self.__log_buf = None    # GtkTextBuffer — set after super().__init__
        self.__pulse_active = True  # whether the progress bar is in pulse mode
        self.__log_file = None      # open handle to fisherman-output.log for tailing
        self.__log_linebuf = ""     # incomplete line buffer for the log watcher
        self.__progress_state = new_progress_state()
        self.__boot_id = ""  # EFI boot entry ID from fisherman complete event
        self.__recovery_key = ""
        self.__recipe_path = None   # path to recipe JSON (for cleanup)
        self.__start_time = None
        self.__elapsed_timer_id = None
        self.__last_fraction = 0.0  # for ETA computation
        self.__current_media_mode = "video"
        self.__syncing_mode_buttons = False
        self._carousel_timer = None
        self._tracks_loaded = False
        self._video_configured = False
        self._video_fallback_timeout_id = None

        self._video_tmp_path = None
        self._video_spinner = None
        self._media_overlay = None

        self.__build_ui()
        self.__log_buf = self.log_view.get_buffer()

        self.console_button.connect("clicked", self.__on_console_button)
        self.media_button.connect("clicked", self.__on_media_button)
        self.copy_log_button.connect("clicked", self.__on_copy_log)
        self.btn_video_mode.connect("toggled", self.__on_video_mode_toggled)
        self.btn_soundtrack_mode.connect("toggled", self.__on_soundtrack_mode_toggled)


    def __configure_install_video(self):
        """Set up video playback."""
        self._video_file = None
        self.install_video.connect("notify::media-stream", self.__on_media_stream_changed)
        self.__hide_video_fallback()

        # Check if GStreamer VP9/AV1 decoders are available
        codecs = check_codecs_present()
        if not (codecs["vp9"] or codecs["av1"]):
            logger.warning("GStreamer VP9 or AV1 decoders not available. Automatically falling back to soundtrack mode.")
            self.btn_video_mode.set_sensitive(False)
            GLib.idle_add(self.__show_video_fallback)
            GLib.idle_add(lambda: self.__set_media_mode("soundtrack"))
            return

        self.__arm_video_fallback_timeout()
        threading.Thread(target=self.__extract_and_play_video, daemon=True).start()

    def __on_video_widget_realized(self, *_):
        pass  # unused — kept for safety if connected externally

    def __extract_and_play_video(self):
        """Extract installer-video.webm from GResource to a temp file, then play."""
        import tempfile
        try:
            data = Gio.resources_lookup_data(
                f"{_RESOURCE_PREFIX}/assets/installer-video.webm",
                Gio.ResourceLookupFlags.NONE,
            )
            tmp = tempfile.NamedTemporaryFile(
                suffix=".webm", prefix="bootc-installer-video-", delete=False
            )
            tmp.write(data.get_data())
            tmp.flush()
            tmp.close()
            self._video_tmp_path = tmp.name
            video_file = Gio.File.new_for_path(tmp.name)

            def _done():
                self._video_file = video_file
                # GTK4 gtk_video_set_file() handles both cases:
                #   realized   → starts GStreamer immediately
                #   unrealized → stores file; gtk_video_realize() starts it later
                self.install_video.set_file(video_file)
                return False

            GLib.idle_add(_done)
        except Exception as e:
            logger.warning("Failed to extract installer video: %s", e)
            GLib.idle_add(self.__show_video_fallback)

    def __configure_soundtrack(self):
        self._carousel_timer = None
        self._tracks_loaded = False
        self.btn_soundtrack_mode.set_sensitive(False)
        threading.Thread(target=self.__load_tracks, daemon=True).start()

    def __load_tracks(self):
        """Load soundtrack track list.

        Resolution order:
        1. ``recipe["soundtrack_data"]`` — a GResource path or filesystem path
           supplied by the branding layer.
        2. Built-in GResource ``/org/bootcinstaller/Installer/data/tracks.json``.
        3. Filesystem fallback next to this module (dev mode).
        """
        tracks = []

        # 1. Recipe-supplied override
        recipe = getattr(self.__window, "recipe", {}) or {}
        soundtrack_override = recipe.get("soundtrack_data", "")
        if soundtrack_override:
            if soundtrack_override.startswith("/org/"):
                try:
                    tracks_bytes = Gio.resources_lookup_data(
                        soundtrack_override, Gio.ResourceLookupFlags.NONE
                    )
                    tracks = json.loads(tracks_bytes.get_data())
                except Exception as e:
                    logger.warning("Failed to load soundtrack from recipe GResource %s: %s", soundtrack_override, e)
            else:
                try:
                    import pathlib
                    tracks = json.loads(pathlib.Path(soundtrack_override).read_text())
                except Exception as e:
                    logger.warning("Failed to load soundtrack from recipe path %s: %s", soundtrack_override, e)

        # 2. Built-in GResource
        if not tracks:
            try:
                tracks_bytes = Gio.resources_lookup_data(
                    "/org/bootcinstaller/Installer/data/tracks.json",
                    Gio.ResourceLookupFlags.NONE,
                )
                tracks = json.loads(tracks_bytes.get_data())
            except Exception as e:
                logger.warning("Failed to load soundtrack from GResource: %s", e)
                # 3. Filesystem fallback (dev mode)
                import pathlib
                dev_path = pathlib.Path(__file__).resolve().parent.parent / "data" / "tracks.json"
                try:
                    tracks = json.loads(dev_path.read_text())
                except Exception as e2:
                    logger.warning("Failed to load soundtrack from dev path: %s", e2)

        GLib.idle_add(self.__populate_carousel, tracks)

    def __populate_carousel(self, tracks):
        for track in tracks:
            self.track_carousel.append(self._build_track_card(track))
        self._tracks_loaded = bool(tracks)
        self.btn_soundtrack_mode.set_sensitive(bool(tracks))
        if tracks:
            self._start_carousel_timer()
        self.__show_selected_media_view()
        return False

    def _build_track_card(self, track):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        card.set_margin_start(24)
        card.set_margin_end(24)
        card.set_margin_top(16)
        card.set_margin_bottom(16)
        card.set_hexpand(True)
        card.set_halign(Gtk.Align.FILL)
        card.add_css_class("card")

        # Album cover art (left)
        cover = self.__build_cover_art(track)
        cover.set_size_request(120, 120)
        card.append(cover)

        # Track metadata (center, expands)
        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        meta.set_valign(Gtk.Align.CENTER)
        meta.set_hexpand(True)

        title_lbl = Gtk.Label(label=track["title"])
        title_lbl.add_css_class("title-2")
        title_lbl.set_wrap(True)
        title_lbl.set_xalign(0)

        artist_lbl = Gtk.Label(label=track["artist"])
        artist_lbl.add_css_class("dim-label")
        artist_lbl.set_wrap(True)
        artist_lbl.set_xalign(0)

        album_lbl = Gtk.Label(label=track.get("album", ""))
        album_lbl.add_css_class("caption")
        album_lbl.add_css_class("dim-label")
        album_lbl.set_wrap(True)
        album_lbl.set_xalign(0)

        caption = Gtk.Label(label=_("Scan to listen on your phone"))
        caption.add_css_class("caption")
        caption.add_css_class("dim-label")
        caption.set_xalign(0)

        meta.append(title_lbl)
        meta.append(artist_lbl)
        if track.get("album"):
            meta.append(album_lbl)
        meta.append(caption)
        card.append(meta)

        # QR code (right, smaller)
        qr_widget = self.__build_bundled_track_qr(track)
        if qr_widget is None:
            qr_widget = self.__build_runtime_track_qr(track)
        if qr_widget is None:
            qr_widget = self.__build_track_qr_fallback(track)

        qr_widget.set_size_request(100, 100)
        card.append(qr_widget)

        return card

    def __build_cover_art(self, track):
        """Build a 120×120 album cover picture widget."""
        cover_asset = track.get("cover_art")
        if cover_asset:
            resource_path = f"{_RESOURCE_PREFIX}/assets/covers/{cover_asset}"
            try:
                Gio.resources_lookup_data(resource_path, Gio.ResourceLookupFlags.NONE)
                picture = Gtk.Picture.new_for_resource(resource_path)
                picture.set_can_shrink(True)
                picture.set_content_fit(Gtk.ContentFit.COVER)
                picture.add_css_class("card")
                return picture
            except Exception:
                pass
            # Dev-mode filesystem fallback
            dev_path = _TRACK_COVER_DIR / cover_asset
            if dev_path.exists():
                picture = Gtk.Picture.new_for_file(Gio.File.new_for_path(str(dev_path)))
                picture.set_can_shrink(True)
                picture.set_content_fit(Gtk.ContentFit.COVER)
                picture.add_css_class("card")
                return picture

        # Generic music note placeholder
        icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        box = Gtk.Box()
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        box.append(icon)
        return box

    def __build_bundled_track_qr(self, track):
        resource_path = _track_qr_resource_path(track)
        if resource_path:
            try:
                Gio.resources_lookup_data(resource_path, Gio.ResourceLookupFlags.NONE)
                picture = Gtk.Picture.new_for_resource(resource_path)
                picture.set_can_shrink(True)
                picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                return picture
            except Exception as e:
                logger.debug("Bundled QR unavailable in GResource for %s: %s", track.get("title", "track"), e)

        dev_path = _track_qr_dev_path(track)
        if dev_path and dev_path.exists():
            try:
                picture = Gtk.Picture.new_for_file(Gio.File.new_for_path(str(dev_path)))
                picture.set_can_shrink(True)
                picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                return picture
            except Exception as e:
                logger.debug("Bundled QR unavailable in dev path for %s: %s", track.get("title", "track"), e)

        return None

    def __build_runtime_track_qr(self, track):
        try:
            import segno

            qr = segno.make(track["url"], error="M")
            buf = io.BytesIO()
            qr.save(buf, kind="png", scale=6, dark="#ffffff", light="#1e1e2e")
            buf.seek(0)
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(buf.read()))
            picture = Gtk.Picture.new_for_paintable(texture)
            picture.set_can_shrink(True)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            return picture
        except Exception as e:
            logger.debug("Runtime QR generation unavailable for %s: %s", track.get("title", "track"), e)
            return None

    def __build_track_qr_fallback(self, track):
        fallback_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fallback_box.set_valign(Gtk.Align.CENTER)
        fallback_box.set_halign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        fallback_box.append(icon)
        url_label = Gtk.Label(label=track.get("url", ""))
        url_label.set_wrap(True)
        url_label.set_max_width_chars(20)
        url_label.add_css_class("caption")
        url_label.add_css_class("dim-label")
        url_label.set_selectable(True)
        fallback_box.append(url_label)
        return fallback_box

    def _start_carousel_timer(self):
        self.__stop_carousel_timer()
        self._carousel_timer = GLib.timeout_add_seconds(50, self.__advance_carousel)

    def __stop_carousel_timer(self):
        if self._carousel_timer:
            GLib.source_remove(self._carousel_timer)
            self._carousel_timer = None

    def __advance_carousel(self):
        n_pages = self.track_carousel.get_n_pages()
        if n_pages == 0:
            return True
        next_pos = (int(self.track_carousel.get_position()) + 1) % n_pages
        page = self.track_carousel.get_nth_page(next_pos)
        if page is not None:
            self.track_carousel.scroll_to(page, True)
        return True

    def __on_media_stream_changed(self, *_args):
        """Called when the Gtk.Video gets its MediaStream. Hook into prepared
        notification to defer mute until GstPlayer is actually ready."""
        media_stream = self.install_video.get_media_stream()
        if media_stream is None:
            return
        if _media_stream_is_prepared(media_stream):
            self.__cancel_video_fallback_timeout()
            self.__hide_video_fallback()
            GLib.idle_add(self.__mute_install_video)
        else:
            media_stream.connect("notify::prepared", self.__on_media_prepared)
            media_stream.connect("notify::error", self.__on_media_error)
            self.__arm_video_fallback_timeout()

    def __on_media_prepared(self, media_stream, *_args):
        if _media_stream_is_prepared(media_stream):
            self.__cancel_video_fallback_timeout()
            self.__hide_video_fallback()
            GLib.idle_add(self.__mute_install_video)

    def __on_media_error(self, media_stream, *_args):
        err = media_stream.get_error()
        logger.warning("Media stream error: %s", err)
        self.__cancel_video_fallback_timeout()
        self.__show_video_fallback()

    def __mute_install_video(self):
        media_stream = self.install_video.get_media_stream()
        if _media_stream_is_prepared(media_stream):
            media_stream.set_muted(True)

    def __play_install_video(self):
        media_stream = self.install_video.get_media_stream()
        if _media_stream_is_prepared(media_stream):
            media_stream.play()
            media_stream.set_muted(True)

    def __pause_install_video(self):
        media_stream = self.install_video.get_media_stream()
        if _media_stream_is_prepared(media_stream):
            media_stream.pause()

    def __arm_video_fallback_timeout(self):
        self.__cancel_video_fallback_timeout()
        self.__show_video_spinner()
        self._video_fallback_timeout_id = GLib.timeout_add_seconds(15, self.__on_video_prepare_timeout)

    def __cancel_video_fallback_timeout(self):
        self.__hide_video_spinner()
        if self._video_fallback_timeout_id is not None:
            context = GLib.MainContext.default()
            if context is not None and context.find_source_by_id(self._video_fallback_timeout_id):
                GLib.source_remove(self._video_fallback_timeout_id)
            self._video_fallback_timeout_id = None

    def __on_video_prepare_timeout(self):
        if not _media_stream_is_prepared(self.install_video.get_media_stream()):
            logger.warning("Install video was not prepared in time; showing fallback")
            self.__show_video_fallback()
        self._video_fallback_timeout_id = None
        return False

    def __show_video_fallback(self):
        self.__hide_video_spinner()
        self.video_fallback_box.set_visible(True)
        self.__pause_install_video()

    def __hide_video_fallback(self):
        self.video_fallback_box.set_visible(False)

    def __set_media_mode(self, mode: str, sync_buttons: bool = True):
        self.__current_media_mode = mode
        if sync_buttons:
            self.__syncing_mode_buttons = True
            self.btn_video_mode.set_active(mode == "video")
            self.btn_soundtrack_mode.set_active(mode == "soundtrack")
            self.__syncing_mode_buttons = False
        self.__show_selected_media_view()

    def __show_selected_media_view(self):
        self.console_box.set_visible(False)
        self.media_button.set_visible(False)
        self.console_button.set_visible(True)

        show_soundtrack = self.__current_media_mode == "soundtrack" and self._tracks_loaded
        self.media_box.set_visible(not show_soundtrack)
        self.soundtrack_box.set_visible(show_soundtrack)

        if show_soundtrack:
            self.__pause_install_video()
        else:
            self.__play_install_video()

    def __show_media_view(self):
        self.__show_selected_media_view()

    def __show_console_view(self):
        self.media_box.set_visible(False)
        self.soundtrack_box.set_visible(False)
        self.console_box.set_visible(True)
        self.media_button.set_visible(True)
        self.console_button.set_visible(False)
        self.__pause_install_video()

    def __on_console_button(self, *args):
        self.__show_console_view()

    def __on_media_button(self, *args):
        self.__show_selected_media_view()

    def __on_video_mode_toggled(self, btn):
        if self.__syncing_mode_buttons:
            return
        if btn.get_active():
            self.__syncing_mode_buttons = True
            self.btn_soundtrack_mode.set_active(False)
            self.__syncing_mode_buttons = False
            self.__set_media_mode("video", sync_buttons=False)
        elif not self.btn_soundtrack_mode.get_active():
            self.__syncing_mode_buttons = True
            btn.set_active(True)
            self.__syncing_mode_buttons = False

    def __on_soundtrack_mode_toggled(self, btn):
        if self.__syncing_mode_buttons:
            return
        if btn.get_active():
            self.__syncing_mode_buttons = True
            self.btn_video_mode.set_active(False)
            self.__syncing_mode_buttons = False
            self.__set_media_mode("soundtrack", sync_buttons=False)
        elif not self.btn_video_mode.get_active():
            self.__syncing_mode_buttons = True
            btn.set_active(True)
            self.__syncing_mode_buttons = False

    def __on_copy_log(self, *args):
        """Copy the fisherman log to the clipboard."""
        try:
            with open(_FISHERMAN_LOG_PATH) as f:
                text = f.read()
        except OSError:
            text = self.__log_buf.get_text(
                self.__log_buf.get_start_iter(),
                self.__log_buf.get_end_iter(),
                False,
            )
        if not text:
            return
        try:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
        except Exception as e:
            logger.error("Failed to copy log: %s", e)
            return
        self.copy_log_button.set_icon_name("emblem-ok-symbolic")
        GLib.timeout_add(1500, lambda: self.copy_log_button.set_icon_name("edit-copy-symbolic"))

    def __build_ui(self):
        self.__install_progress_css()
        self.__build_pastry_spinner()
        self.__configure_soundtrack()
        self.__set_media_mode("video")

    def __build_pastry_spinner(self):
        self._media_overlay = self.media_box.get_first_child()
        self._video_spinner = new_grid_spinner()
        if self._video_spinner is not None and self._media_overlay is not None:
            self._media_overlay.add_overlay(self._video_spinner)

    def __show_video_spinner(self):
        if self._video_spinner is not None:
            self._video_spinner.set_visible(True)

    def __hide_video_spinner(self):
        if self._video_spinner is not None:
            self._video_spinner.set_visible(False)

    def __install_progress_css(self):
        display = Gdk.Display.get_default()
        if display is None:
            return
        css = Gtk.CssProvider()
        css.load_from_string(
            ".thick-progress trough, .thick-progress progress { min-height: 8px; }"
            " .thick-progress progress { transition: all 300ms ease-in-out; }"
        )
        Gtk.StyleContext.add_provider_for_display(
            display,
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def __set_progress_fraction(self, fraction: float):
        fraction = max(0.0, min(fraction, 1.0))
        self.progressbar.set_fraction(fraction)
        self.progress_percentage.set_label(f"{int(fraction * 100)}%")
        self.__last_fraction = fraction
        self.__update_eta(fraction)

    def __format_elapsed(self, elapsed_seconds: float) -> str:
        total_seconds = max(0, int(elapsed_seconds))
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    def __update_eta(self, fraction: float):
        """Compute and display estimated time remaining."""
        if self.__start_time is None or fraction < 0.05:
            # Not enough data to estimate yet
            self.progress_eta.set_label("")
            return
        elapsed = time.monotonic() - self.__start_time
        if elapsed < 5:
            return  # wait at least 5s before showing ETA
        remaining = (elapsed / fraction) * (1.0 - fraction)
        remaining = max(0, int(remaining))
        if remaining < 60:
            eta_text = _("~%d sec remaining") % remaining
        else:
            minutes = remaining // 60
            eta_text = _("~%d min remaining") % minutes
        self.progress_eta.set_label(eta_text)

    def __update_elapsed_label(self):
        if self.__start_time is None:
            return False
        elapsed = self.__format_elapsed(time.monotonic() - self.__start_time)
        self.progress_elapsed.set_label(_("%s elapsed") % elapsed)
        # Also refresh ETA on the timer tick
        self.__update_eta(self.__last_fraction)
        return True

    def __start_elapsed_timer(self):
        self.__stop_elapsed_timer(clear_start_time=False)
        self.__start_time = time.monotonic()
        self.__update_elapsed_label()
        self.__elapsed_timer_id = GLib.timeout_add(1000, self.__update_elapsed_label)

    def __stop_elapsed_timer(self, clear_start_time: bool = True):
        if self.__elapsed_timer_id is not None:
            GLib.source_remove(self.__elapsed_timer_id)
            self.__elapsed_timer_id = None
        if clear_start_time:
            self.__start_time = None

    def __pulse_progress(self):
        if self.__pulse_active:
            self.progressbar.pulse()
        return self.__pulse_active

    def _start_log_watcher(self):
        """Begin tailing fisherman-output.log for JSON progress events.

        Polls until the file exists, then reads new data every 100ms.
        GLib.io_add_watch does not work on regular files (only pipes/sockets),
        so we use a timer-based poll instead.
        """
        self.__watcher_lines = 0
        logger.info("_start_log_watcher: scheduling try_open for %s", _FISHERMAN_LOG_PATH)
        GLib.timeout_add(200, self.__try_open_log_for_watching)

    def __try_open_log_for_watching(self) -> bool:
        exists = os.path.exists(_FISHERMAN_LOG_PATH)
        if not exists:
            return True  # retry
        try:
            self.__log_file = open(_FISHERMAN_LOG_PATH, "r")
            GLib.timeout_add(100, self.__poll_log_file)
            logger.info("Log watcher OPENED %s (pos=%d)", _FISHERMAN_LOG_PATH, self.__log_file.tell())
            return False  # stop retrying
        except OSError as e:
            logger.error("Log watcher open FAILED: %s", e)
            return True  # retry

    def __poll_log_file(self) -> bool:
        """Read any new data from the log file into the TextView. Runs every 100ms."""
        if self.__log_file is None:
            return False
        new_text = self.__log_file.read()
        if new_text:
            self.__log_linebuf += new_text
            lines = self.__log_linebuf.split("\n")
            self.__log_linebuf = lines[-1]
            for line in lines[:-1]:
                self.__watcher_lines += 1
                self.__parse_progress_line(line.strip())
                self.__append_log_line(line)
            if self.__watcher_lines <= 5 or self.__watcher_lines % 50 == 0:
                logger.info("Log watcher: %d lines appended to buffer (buf chars=%d)",
                            self.__watcher_lines, self.__log_buf.get_char_count())
        return True  # keep polling until __finish_install sets __log_file = None

    def __append_log_line(self, line: str):
        """Append a line to the TextView buffer and auto-scroll."""
        end = self.__log_buf.get_end_iter()
        self.__log_buf.insert(end, line + "\n")
        if self.console_box.get_visible():
            GLib.idle_add(self.__scroll_log_to_bottom)

    def __scroll_log_to_bottom(self):
        end = self.__log_buf.get_end_iter()
        self.log_view.scroll_to_iter(end, 0.0, False, 0.0, 1.0)
        return False

    def __poll_proc(self) -> bool:
        """Poll fisherman subprocess exit status every 500ms."""
        if self.__proc is None:
            return False
        ret = self.__proc.poll()
        if ret is None:
            return True  # still running
        # Give the log poller 300ms to drain any last bytes before finishing.
        GLib.timeout_add(300, self.__finish_install, ret)
        return False

    def __finish_install(self, ret: int) -> bool:
        """Final log drain then hand off to the done screen."""
        if self.__log_file:
            remaining = self.__log_file.read()
            if remaining:
                self.__log_linebuf += remaining
            lines = (self.__log_linebuf + "\n").split("\n")
            self.__log_linebuf = ""
            for line in lines:
                if line.strip():
                    self.__parse_progress_line(line.strip())
                    self.__append_log_line(line)
            self.__log_file.close()
            self.__log_file = None
        # Compute elapsed before stopping the timer
        elapsed_secs = 0
        if self.__start_time is not None:
            elapsed_secs = int(time.monotonic() - self.__start_time)
        self.__stop_elapsed_timer()
        self.__stop_carousel_timer()
        self.__cancel_video_fallback_timeout()
        self.__pause_install_video()
        # Securely delete the recipe file — it contains plaintext passphrases
        # and passwords that must not persist on disk after install.
        self.__cleanup_recipe_file()
        self.__cleanup_video_tmp()
        self.__window.set_installation_result(
            ret == 0, None, self.__boot_id, self.__recovery_key, elapsed_secs
        )
        return False

    def __cleanup_recipe_file(self):
        """Remove the temporary recipe JSON file containing sensitive credentials."""
        recipe_path = getattr(self, "_BootcProgress__recipe_path", None)
        if not recipe_path:
            return
        try:
            os.unlink(recipe_path)
            logger.info("Deleted recipe file: %s", recipe_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("Could not delete recipe file %s: %s", recipe_path, e)

    def __cleanup_video_tmp(self):
        """Remove the temp video file extracted from GResource."""
        if self._video_tmp_path:
            try:
                os.unlink(self._video_tmp_path)
            except OSError:
                pass
            self._video_tmp_path = None

    def __parse_progress_line(self, line: str):
        """Parse a single fisherman log line and apply any resulting UI update."""
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            event = {}

        update = apply_progress_event(line, self.__progress_state)
        if event.get("type") == "recovery_key":
            self.__recovery_key = self.__progress_state.get("recovery_key", "")
            logger.info("Fisherman reported recovery key")
        if update is None:
            return

        if update["fraction"] is not None:
            self.__set_progress_fraction(update["fraction"])
        if update["label"] is not None:
            self.progressbar_text.set_label(_(update["label"]))
        if event.get("type") == "step":
            self.progress_substep.set_label("")
        elif event.get("type") == "substep":
            self.progress_substep.set_label(event.get("message", ""))
        if not update["pulse"]:
            self.__pulse_active = False

        if update["complete"]:
            self.__stop_elapsed_timer()
            self.__stop_carousel_timer()
            self.__cancel_video_fallback_timeout()
            self.__pause_install_video()
            self.progress_substep.set_label("")
            self.__boot_id = self.__progress_state["boot_id"]
            self.__recovery_key = self.__progress_state.get("recovery_key", "")
            logger.info("Fisherman reported completion")
        elif update.get("label"):
            logger.info("UI update: %s (fraction=%.2f)", update["label"],
                        update["fraction"] if update["fraction"] is not None else -1)

    def configure_video_preview(self):
        """Configure video playback for the preview/demo mode (BOOTC_PREVIEW_SCREEN=progress).
        Called by main_window when the progress page is shown without a real install."""
        if not self._video_configured:
            self._video_configured = True
            self.__configure_install_video()

    def start_demo(self):
        """Fake install sequence for UI design / demo mode (BOOTC_DEMO=1).

        Walks through 9 steps over ~5 seconds, then calls set_installation_result.
        No fisherman is launched. No disk is touched.
        """
        logger.info("start_demo() called")
        _STEPS = [
            (0.4,  0.11, "Step 1/9: Partitioning disk"),
            (0.8,  0.22, "Step 2/9: Formatting EFI partition"),
            (1.2,  0.33, "Step 3/9: Setting up encryption"),
            (1.6,  0.44, "Step 4/9: Formatting root filesystem"),
            (2.0,  0.55, "Step 5/9: Mounting filesystems"),
            (2.8,  0.66, "Step 6/9: Installing system image"),
            (3.6,  0.77, "Step 7/9: Copying flatpaks"),
            (4.2,  0.88, "Step 8/9: Writing configuration"),
            (4.8,  0.99, "Step 9/9: Finalizing"),
        ]
        self.__pulse_active = False
        self.__set_progress_fraction(0.0)
        self.progress_substep.set_label("")
        self.progress_elapsed.set_label(_("0:00 elapsed"))
        self.__hide_video_fallback()
        self.__show_media_view()
        if not self._video_configured:
            self._video_configured = True
            self.__configure_install_video()

        def _fire_step(index):
            if index >= len(_STEPS):
                self.__set_progress_fraction(1.0)
                self.__pause_install_video()
                self.progress_substep.set_label("")
                self.progressbar_text.set_label(_("Installation complete!"))
                GLib.timeout_add(600, lambda: self.__window.set_installation_result(True, None, "") or False)
                return False
            _delay, fraction, label = _STEPS[index]
            self.__set_progress_fraction(fraction)
            self.progress_substep.set_label("")
            self.progressbar_text.set_label(_(label))
            return False

        for i, (delay, _frac, _label) in enumerate(_STEPS):
            GLib.timeout_add(int(delay * 1000), _fire_step, i)
        GLib.timeout_add(int((_STEPS[-1][0] + 0.6) * 1000), _fire_step, len(_STEPS))

    def start(self, recipe):
        # If VANILLA_FAKE was passed as argument
        if not recipe:
            self.__window.set_installation_result(False, None)
            return

        if not _stage_fisherman_on_host():
            self.__window.set_installation_result(False, None)
            return

        # Track the recipe path so we can securely delete it after install.
        # The recipe contains plaintext passphrases and passwords.
        self.__recipe_path = recipe

        argv = _fisherman_argv_direct(recipe)
        os.makedirs(_FISHERMAN_CACHE_DIR, exist_ok=True)
        # Remove any stale log file before launching so the watcher always opens
        # a fresh file at position 0. If the old file exists, bash's '>' redirect
        # truncates it but Python's file handle would still sit at the old EOF,
        # causing read() to return empty even though new content is present.
        try:
            os.unlink(_FISHERMAN_LOG_PATH)
            logger.info("Deleted stale log file: %s", _FISHERMAN_LOG_PATH)
        except FileNotFoundError:
            logger.info("No stale log file to delete")
        except Exception as e:
            logger.error("Failed to delete stale log: %s", e)
        self.__progress_state = new_progress_state()
        self.__boot_id = ""
        self.__recovery_key = ""
        self.__pulse_active = True
        self.__set_progress_fraction(0.0)
        self.progressbar_text.set_label(_("Installing"))
        self.progress_substep.set_label("")
        self.__hide_video_fallback()
        self.__show_media_view()
        if not self._video_configured:
            self._video_configured = True
            self.__configure_install_video()
        GLib.timeout_add(200, self.__pulse_progress)
        logger.info("Launching fisherman: %s", argv)
        self.__start_elapsed_timer()
        # bash handles writing stdout+stderr to the log file via shell redirection.
        # Do NOT pass stdout= here — flatpak-spawn uses D-Bus, not a real pipe fd.
        self.__proc = subprocess.Popen(argv)
        logger.info("Fisherman PID: %s", self.__proc.pid)
        GLib.timeout_add(500, self.__poll_proc)
        self._start_log_watcher()

    def terminate(self):
        """Terminate fisherman if it is still running (e.g. window closed).

        This sends SIGTERM to the bash wrapper process group. fisherman's cleanup
        handler will attempt to unmount filesystems and close LUKS devices.
        """
        self.__stop_carousel_timer()
        self.__cancel_video_fallback_timeout()
        if self.__proc is None:
            return
        if self.__proc.poll() is not None:
            return
        logger.warning("Terminating fisherman (PID %s) due to window close", self.__proc.pid)
        try:
            import signal
            os.killpg(os.getpgid(self.__proc.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                self.__proc.terminate()
            except OSError as e:
                logger.debug("Could not terminate fisherman process: %s", e)
        self.__cleanup_recipe_file()
