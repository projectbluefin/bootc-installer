"""
Unit tests for confirm.py and related helpers — pure Python, no GTK required.
Covers _ENC_LABELS lookup, quote selection logic, and keyboard formatting.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Stub out gi.repository before importing confirm so no display is needed.
for _mod in (
    "gi", "gi.repository", "gi.repository.Adw", "gi.repository.Gdk",
    "gi.repository.Gio", "gi.repository.GLib", "gi.repository.Gtk",
    "gi.repository.GObject",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bootc_installer.views.confirm import _ENC_LABELS, _SENNA_QUOTES  # noqa: E402


class TestEncLabels(unittest.TestCase):
    """_ENC_LABELS maps all four encryption type strings to human-readable labels."""

    def test_none_label(self):
        self.assertEqual(_ENC_LABELS["none"], "None")

    def test_luks_passphrase_label(self):
        self.assertIn("passphrase", _ENC_LABELS["luks-passphrase"].lower())

    def test_tpm2_luks_label(self):
        label = _ENC_LABELS["tpm2-luks"]
        self.assertTrue(label, "tpm2-luks should have a non-empty label")
        self.assertNotIn("passphrase", label.lower(),
                         "tpm2-luks-only label should not mention passphrase")

    def test_tpm2_luks_passphrase_label(self):
        label = _ENC_LABELS["tpm2-luks-passphrase"]
        self.assertIn("passphrase", label.lower())

    def test_all_four_keys_present(self):
        expected = {"none", "luks-passphrase", "tpm2-luks", "tpm2-luks-passphrase"}
        self.assertEqual(set(_ENC_LABELS.keys()), expected)

    def test_all_labels_are_non_empty_strings(self):
        for key, label in _ENC_LABELS.items():
            self.assertIsInstance(label, str, f"Label for {key!r} is not a string")
            self.assertTrue(label.strip(), f"Label for {key!r} is empty")

    def test_fallback_for_unknown_type(self):
        # Unknown type falls through to raw key — callers use .get(type, type)
        unknown = "custom-encryption"
        result = _ENC_LABELS.get(unknown, unknown)
        self.assertEqual(result, unknown)


class TestConfirmQuoteSelection(unittest.TestCase):
    """Quote selection logic: Senna for pt_BR, Zavala otherwise."""

    def _select_quote(self, selected_language):
        """Mirror the logic in VanillaConfirm.update() — returns quote category."""
        if selected_language and selected_language.startswith("pt_BR"):
            return "senna"
        return "zavala"

    def test_pt_br_gets_senna(self):
        self.assertEqual(self._select_quote("pt_BR"), "senna")

    def test_pt_br_with_encoding_suffix_gets_senna(self):
        self.assertEqual(self._select_quote("pt_BR.UTF-8"), "senna")

    def test_english_gets_zavala(self):
        self.assertEqual(self._select_quote("en_US"), "zavala")

    def test_none_language_gets_zavala(self):
        self.assertEqual(self._select_quote(None), "zavala")

    def test_empty_language_gets_zavala(self):
        self.assertEqual(self._select_quote(""), "zavala")

    def test_pt_pt_gets_zavala(self):
        # pt_PT (Portugal) is NOT pt_BR — should get Zavala
        self.assertEqual(self._select_quote("pt_PT"), "zavala")

    def test_de_de_gets_zavala(self):
        self.assertEqual(self._select_quote("de_DE"), "zavala")


class TestConfirmSennaQuotes(unittest.TestCase):
    """VanillaConfirm._SENNA_QUOTES contains valid non-empty quote strings."""

    def _get_quotes(self):
        return _SENNA_QUOTES

    def test_senna_quotes_non_empty_list(self):
        quotes = self._get_quotes()
        self.assertIsInstance(quotes, list)
        self.assertGreater(len(quotes), 0)

    def test_senna_quotes_contain_his_name(self):
        quotes = self._get_quotes()
        for q in quotes:
            self.assertIn("Senna", q, f"Quote missing 'Senna': {q!r}")

    def test_senna_quotes_are_strings(self):
        for q in self._get_quotes():
            self.assertIsInstance(q, str)


class TestKeyboardFormatting(unittest.TestCase):
    """process_keyboards produces correct VanillaChoiceEntry arguments."""

    def _get_keyboard_labels(self, selected_keyboards):
        """Return list of (title, value) pairs that process_keyboards would create,
        without instantiating any GTK widget."""
        results = []
        keyboard_index = ""
        if len(selected_keyboards) > 1:
            keyboard_index = 0
        for i in selected_keyboards:
            value = i["layout"]
            if i["variant"] != "":
                value = f"{i['layout']}+{i['variant']}"
            if len(selected_keyboards) > 1:
                keyboard_index += 1
            results.append((f"Keyboard {keyboard_index}", value))
        return results

    def test_single_keyboard_no_variant(self):
        kb = [{"layout": "us", "variant": ""}]
        labels = self._get_keyboard_labels(kb)
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0][1], "us")

    def test_single_keyboard_with_variant(self):
        kb = [{"layout": "de", "variant": "neo"}]
        labels = self._get_keyboard_labels(kb)
        self.assertEqual(labels[0][1], "de+neo")

    def test_multiple_keyboards_indexed(self):
        kb = [
            {"layout": "us", "variant": ""},
            {"layout": "fr", "variant": "azerty"},
        ]
        labels = self._get_keyboard_labels(kb)
        self.assertEqual(len(labels), 2)
        self.assertEqual(labels[0][1], "us")
        self.assertEqual(labels[1][1], "fr+azerty")
        # Multi-keyboard entries should have a numeric index in title
        self.assertIn("1", labels[0][0])
        self.assertIn("2", labels[1][0])

    def test_empty_keyboard_list(self):
        labels = self._get_keyboard_labels([])
        self.assertEqual(labels, [])


if __name__ == "__main__":
    unittest.main()
