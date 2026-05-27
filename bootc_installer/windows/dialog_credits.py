"""Credits window with animated hero cards for Bluefin contributors."""

import json
import os

from gi.repository import Adw, Gio, GLib, Gtk

_CREDITS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "credits.json")

# CSS for the glass-effect hero cards and animations
_CREDITS_CSS = """
.credits-window {
  background: @window_bg_color;
}

.credits-header-title {
  font-weight: 900;
  letter-spacing: 2px;
}

.credits-quote {
  font-style: italic;
  opacity: 0.7;
}

.credits-closing {
  font-weight: 700;
  letter-spacing: 1px;
  margin-top: 12px;
}

.credits-section-title {
  font-weight: 800;
  letter-spacing: 1px;
}

.hero-card {
  background: alpha(@card_bg_color, 0.85);
  border-radius: 12px;
  padding: 16px;
  border: 1px solid alpha(@borders, 0.3);
  box-shadow: 0 2px 8px alpha(black, 0.08);
  transition: all 300ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.hero-card:hover {
  background: alpha(@card_bg_color, 1.0);
  box-shadow: 0 4px 20px alpha(@accent_color, 0.2), 0 8px 32px alpha(black, 0.12);
  border: 1px solid alpha(@accent_color, 0.6);
  transform: scale(1.02);
}

.hero-card-name {
  font-weight: 700;
  font-size: 1.05em;
}

.hero-card-title {
  color: @accent_color;
  font-size: 0.85em;
  font-weight: 600;
}

.hero-card-nickname {
  font-style: italic;
  opacity: 0.6;
  font-size: 0.85em;
}

.hero-card-avatar {
  border-radius: 50%;
  background: alpha(@accent_bg_color, 0.15);
  border: 2px solid alpha(@accent_color, 0.3);
  min-width: 48px;
  min-height: 48px;
  transition: all 400ms ease;
}

.hero-card:hover .hero-card-avatar {
  background: alpha(@accent_bg_color, 0.3);
  border-color: @accent_color;
  box-shadow: 0 0 12px alpha(@accent_color, 0.4);
}

.card-revealed {
  animation: card-materialize 500ms cubic-bezier(0.22, 1, 0.36, 1);
}

@keyframes card-materialize {
  0% {
    opacity: 0;
    transform: translateY(20px) scale(0.95);
  }
  60% {
    opacity: 1;
    transform: translateY(-2px) scale(1.01);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.section-revealed {
  animation: section-sweep 600ms cubic-bezier(0.22, 1, 0.36, 1);
}

@keyframes section-sweep {
  from {
    opacity: 0;
    transform: translateX(-16px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
"""


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/dialog-credits.ui")
class TunaCreditsWindow(Adw.Window):
    __gtype_name__ = "TunaCreditsWindow"

    header_title = Gtk.Template.Child()
    header_subtitle = Gtk.Template.Child()
    header_quote = Gtk.Template.Child()
    sections_box = Gtk.Template.Child()
    footer_quote = Gtk.Template.Child()
    footer_closing = Gtk.Template.Child()
    credits_scroll = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.set_transient_for(window)
        self._reveal_queue = []
        self._reveal_index = 0
        self._section_revealers = []
        self._current_section = 0

        # Apply CSS
        provider = Gtk.CssProvider()
        provider.load_from_string(_CREDITS_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._load_credits()

    def _load_credits(self):
        """Load credits data and populate the window."""
        data = None

        # Try loading from GResource (Flatpak bundle)
        try:
            resource_path = "/org/bootcinstaller/Installer/data/credits.json"
            gfile = Gio.File.new_for_uri(f"resource://{resource_path}")
            content = gfile.load_contents(None)[1].decode("utf-8")
            data = json.loads(content)
        except Exception:
            pass

        # Fall back to file on disk
        if data is None:
            credits_path = _CREDITS_PATH
            if not os.path.exists(credits_path):
                credits_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "credits.json"
                )
            try:
                with open(credits_path) as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self.header_title.set_label("Credits")
                self.header_subtitle.set_label("Data not available")
                return

        # Populate header
        header = data.get("header", {})
        self.header_title.set_label(header.get("title", "Credits"))
        self.header_subtitle.set_label(header.get("subtitle", ""))
        quote_text = header.get("quote", "")
        if header.get("quote_author"):
            quote_text += f"\n— {header['quote_author']}"
        self.header_quote.set_label(quote_text)

        # Populate footer
        footer = data.get("footer", {})
        footer_text = footer.get("quote", "")
        if footer.get("quote_author"):
            footer_text += f"\n— {footer['quote_author']}"
        self.footer_quote.set_label(footer_text)
        self.footer_closing.set_label(footer.get("closing", ""))

        # Build sections with hero cards
        for section in data.get("sections", []):
            self._build_section(section)

        # Start staggered reveal animation — sections first, then cards
        GLib.timeout_add(200, self._reveal_next_section)

    def _reveal_next_section(self):
        """Reveal sections one at a time, then start card animation."""
        if self._current_section >= len(self._section_revealers):
            # All sections revealed, start card cascade
            GLib.timeout_add(60, self._reveal_next_card)
            return GLib.SOURCE_REMOVE

        revealer, box = self._section_revealers[self._current_section]
        revealer.set_reveal_child(True)
        box.add_css_class("section-revealed")
        self._current_section += 1
        return GLib.SOURCE_CONTINUE

    def _build_section(self, section):
        """Build a section with title and hero cards."""
        # Section wrapper with reveal animation
        section_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            transition_duration=400,
            reveal_child=False,
        )

        section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # Section header
        title_label = Gtk.Label(
            label=section.get("title", ""),
            halign=Gtk.Align.START,
            css_classes=["credits-section-title", "title-4"],
        )
        section_box.append(title_label)

        subtitle = section.get("subtitle", "")
        if subtitle:
            sub_label = Gtk.Label(
                label=subtitle,
                halign=Gtk.Align.START,
                css_classes=["dim-label", "caption"],
            )
            section_box.append(sub_label)

        # Flow box for hero cards (responsive grid)
        flow = Gtk.FlowBox(
            homogeneous=False,
            max_children_per_line=2,
            min_children_per_line=1,
            selection_mode=Gtk.SelectionMode.NONE,
            row_spacing=12,
            column_spacing=12,
            margin_top=8,
        )

        for member in section.get("members", []):
            card = self._build_hero_card(member)
            flow.insert(card, -1)

        section_box.append(flow)
        section_revealer.set_child(section_box)

        # Queue section revealer before its cards
        self._section_revealers.append((section_revealer, section_box))

        self.sections_box.append(section_revealer)

    def _build_hero_card(self, member):
        """Build a single hero card widget with reveal animation."""
        # Wrap in a Revealer for staggered animation
        revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
            transition_duration=350,
            reveal_child=False,
        )

        card = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            css_classes=["hero-card"],
        )

        # Avatar placeholder (initials circle)
        handle = member.get("handle", "?")
        initials = handle[0].upper() if handle else "?"
        avatar_label = Gtk.Label(
            label=initials,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            width_request=48,
            height_request=48,
            css_classes=["hero-card-avatar", "title-2"],
        )
        card.append(avatar_label)

        # Info column
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        # Handle / display name
        name_label = Gtk.Label(
            label=handle,
            halign=Gtk.Align.START,
            css_classes=["hero-card-name"],
        )
        info_box.append(name_label)

        # Title (only if present)
        title = member.get("title")
        if title:
            title_label = Gtk.Label(
                label=title,
                halign=Gtk.Align.START,
                css_classes=["hero-card-title"],
            )
            info_box.append(title_label)

        # Nickname (only if present)
        nickname = member.get("nickname")
        if nickname:
            nick_label = Gtk.Label(
                label=f'"{nickname}"',
                halign=Gtk.Align.START,
                css_classes=["hero-card-nickname"],
            )
            info_box.append(nick_label)

        card.append(info_box)
        revealer.set_child(card)

        # Queue for staggered reveal
        self._reveal_queue.append(revealer)

        return revealer

    def _reveal_next_card(self):
        """Reveal one card at a time for cinematic staggered effect."""
        if self._reveal_index >= len(self._reveal_queue):
            return GLib.SOURCE_REMOVE

        revealer = self._reveal_queue[self._reveal_index]
        revealer.set_reveal_child(True)
        # Add CSS animation class after reveal
        child = revealer.get_child()
        if child:
            child.add_css_class("card-revealed")
        self._reveal_index += 1
        return GLib.SOURCE_CONTINUE
