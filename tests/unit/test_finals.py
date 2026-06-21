"""Unit tests for bootc_installer.utils.finals."""

import unittest

from bootc_installer.utils.finals import _extract_icon_and_name


class TestExtractIconAndName(unittest.TestCase):
    def test_empty_finals_returns_none_pair(self):
        self.assertEqual(_extract_icon_and_name([]), (None, None))

    def test_only_pretty_name_returns_name_and_none_icon(self):
        self.assertEqual(_extract_icon_and_name([{"pretty_name": "Bluefin"}]), ("Bluefin", None))

    def test_only_icon_returns_none_name_and_icon(self):
        self.assertEqual(_extract_icon_and_name([{"icon": "bluefin-symbolic"}]), (None, "bluefin-symbolic"))

    def test_skips_non_dict_entries(self):
        finals = [None, "ignored", ["nested"], {"pretty_name": "Aurora", "icon": "aurora-symbolic"}]
        self.assertEqual(_extract_icon_and_name(finals), ("Aurora", "aurora-symbolic"))

    def test_combines_fields_split_across_dicts(self):
        finals = [{"hostname": "testbox"}, {"pretty_name": "Bazzite"}, {"icon": "bazzite-symbolic"}]
        self.assertEqual(_extract_icon_and_name(finals), ("Bazzite", "bazzite-symbolic"))

    def test_first_occurrence_wins_for_name_and_icon(self):
        finals = [
            {"pretty_name": "Bluefin", "icon": "bluefin-symbolic"},
            {"pretty_name": "Aurora"},
            {"icon": "aurora-symbolic"},
        ]
        self.assertEqual(_extract_icon_and_name(finals), ("Bluefin", "bluefin-symbolic"))

    def test_stops_iterating_once_both_values_found(self):
        class FinalsSequence:
            def __iter__(self):
                yield {"pretty_name": "Bluefin"}
                yield {"icon": "bluefin-symbolic"}
                raise AssertionError("iteration continued after both values were found")

        self.assertEqual(
            _extract_icon_and_name(FinalsSequence()),
            ("Bluefin", "bluefin-symbolic"),
        )
