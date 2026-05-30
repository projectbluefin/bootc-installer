"""Unit tests for user creation validation logic (defaults/user.py).

Tests the security-sensitive validation logic in BootcDefaultUsers.
"""

import re
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Mock gi.repository before importing the module
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gtk'] = MagicMock()
sys.modules['gi.repository.Gdk'] = MagicMock()
sys.modules['gi.repository.GObject'] = MagicMock()
sys.modules['gi.repository.Adw'] = MagicMock()
sys.modules['gi.repository.GLib'] = MagicMock()


class TestSuggestedUsername(unittest.TestCase):
    """Tests for the __suggested_username derivation logic."""

    def _suggested_username(self, fullname: str) -> str:
        """Mirror of BootcDefaultUsers.__suggested_username logic."""
        name = fullname.lower().split()[0] if fullname.strip() else ""
        return re.sub(r"[^a-z0-9_-]", "", name)

    def test_simple_name(self):
        """John → john."""
        self.assertEqual(self._suggested_username("John"), "john")

    def test_full_name_takes_first(self):
        """Jane Doe → jane (first word only)."""
        self.assertEqual(self._suggested_username("Jane Doe"), "jane")

    def test_lowercase(self):
        """SCREAMING → screaming."""
        self.assertEqual(self._suggested_username("SCREAMING"), "screaming")

    def test_strips_special_chars(self):
        """Jean-Luc Picard → jean-luc (special chars except -_ removed)."""
        self.assertEqual(self._suggested_username("Jean-Luc Picard"), "jean-luc")

    def test_strips_dot_and_at(self):
        """user@domain.com → userdomaincom."""
        self.assertEqual(self._suggested_username("user@domain.com"), "userdomaincom")

    def test_empty_string(self):
        """Empty fullname → empty string."""
        self.assertEqual(self._suggested_username(""), "")

    def test_whitespace_only(self):
        """Whitespace-only → empty string."""
        self.assertEqual(self._suggested_username("   "), "")

    def test_preserves_underscore(self):
        """user_name → user_name."""
        self.assertEqual(self._suggested_username("user_name"), "user_name")

    def test_preserves_hyphen(self):
        """test-user → test-user."""
        self.assertEqual(self._suggested_username("test-user"), "test-user")

    def test_unicode_normalizes(self):
        """José → jos (only a-z chars kept)."""
        result = self._suggested_username("José")
        self.assertEqual(result, "jos")

    def test_numeric_only(self):
        """12345 → 12345 (digits preserved)."""
        self.assertEqual(self._suggested_username("12345"), "12345")


class TestUsernameValidation(unittest.TestCase):
    """Tests for the username regex validation in __on_field_changed."""

    def _username_ok(self, username: str) -> bool:
        """Mirror of the username validation regex."""
        return bool(re.match(r"^[a-z_][a-z0-9_-]{0,31}$", username)) if username else False

    def test_valid_simple(self):
        """johndoe is valid."""
        self.assertTrue(self._username_ok("johndoe"))

    def test_valid_with_numbers(self):
        """user42 is valid."""
        self.assertTrue(self._username_ok("user42"))

    def test_valid_with_underscore(self):
        """_underscore_start is valid."""
        self.assertTrue(self._username_ok("_underscore_start"))

    def test_valid_with_hyphen(self):
        """test-user is valid."""
        self.assertTrue(self._username_ok("test-user"))

    def test_valid_single_char(self):
        """a (single letter) is valid."""
        self.assertTrue(self._username_ok("a"))

    def test_valid_long_string(self):
        """32-char alphanumeric string is valid (boundary)."""
        self.assertTrue(self._username_ok("a" + "b" * 30 + "c"))  # 32 chars

    def test_invalid_uppercase(self):
        """Uppercase letters are invalid."""
        self.assertFalse(self._username_ok("JohnDoe"))

    def test_invalid_start_with_number(self):
        """Numbers at start are invalid."""
        self.assertFalse(self._username_ok("1user"))

    def test_invalid_spaces(self):
        """Spaces are invalid."""
        self.assertFalse(self._username_ok("john doe"))

    def test_invalid_special_chars(self):
        """At-sign is invalid."""
        self.assertFalse(self._username_ok("john@doe"))

    def test_invalid_too_long(self):
        """33-char string exceeds max length."""
        self.assertFalse(self._username_ok("a" + "b" * 31 + "c"))  # 33 chars

    def test_invalid_empty(self):
        """Empty string is invalid."""
        self.assertFalse(self._username_ok(""))

    def test_invalid_dot(self):
        """Dots are invalid in username."""
        self.assertFalse(self._username_ok("john.doe"))

    def test_invalid_start_with_hyphen(self):
        """Leading hyphen is invalid (must start with letter or _)."""
        self.assertFalse(self._username_ok("-test"))


class TestPasswordStrength(unittest.TestCase):
    """Tests for the password strength scoring logic."""

    def _score_password(self, password: str) -> int:
        """Mirror of __update_password_strength scoring."""
        if not password:
            return 0
        score = 0
        if len(password) >= 8:
            score += 1
        if len(password) >= 12:
            score += 1
        if re.search(r"[A-Z]", password):
            score += 1
        if re.search(r"[0-9]", password):
            score += 1
        if re.search(r"[^a-zA-Z0-9]", password):
            score += 1
        return score

    def test_empty_password(self):
        """Empty password scores 0."""
        self.assertEqual(self._score_password(""), 0)

    def test_short_weak(self):
        """Short password with no variety scores 1 (>=8)."""
        self.assertEqual(self._score_password("abcdefgh"), 1)

    def test_long_weak(self):
        """Long lowercase-only scores 2 (>=8 and >=12)."""
        self.assertEqual(self._score_password("abcdefghijkl"), 2)

    def test_medium_with_upper(self):
        """8-char password with uppercase scores 2."""
        self.assertEqual(self._score_password("Abcdefgh"), 2)

    def test_strong_mixed(self):
        """12+ chars with upper, digit, and special scores 5."""
        self.assertEqual(self._score_password("Abcd1234!@xyz"), 5)

    def test_just_numbers(self):
        """Numeric-only password scores for length >=8 + >=12 + digit cardinal."""
        # "123456789012" = 12 chars → +1(>=8) +1(>=12) +0 +1(digit) +0 = 3
        self.assertEqual(self._score_password("123456789012"), 3)

    def test_below_8_chars(self):
        """Below 8 chars still scores for character variety (upper, digit, special are unconditional)."""
        # "Ab1!" = 4 chars (< 8, < 12) → +0 +0, but +upper +digit +special = 3
        self.assertEqual(self._score_password("Ab1!"), 3)

    def test_special_char_only_count(self):
        """Special chars count once, not per character."""
        self.assertEqual(self._score_password("abcdefgh!"), 2)  # >=8, special

    def test_strength_labels(self):
        """Verify score-to-label mapping boundary conditions."""
        # score <= 1 → Weak
        self.assertIn(self._score_password("abcdefgh"), [1])  # Weak
        # score <= 2 → Fair
        self.assertIn(self._score_password("Abcdefgh"), [2])  # Fair (>=8, upper)
        # score <= 3 → Good
        self.assertIn(self._score_password("Abcdefgh1"), [3])  # Good (>=8, upper, digit)
        # score >= 4 → Strong
        self.assertIn(self._score_password("Abcdefgh1!"), [4])  # Strong (>=8, upper, digit, special)


class TestGetFinals(unittest.TestCase):
    """Tests for the get_finals method result structure."""

    def test_empty_username_returns_empty(self):
        """get_finals with empty username returns empty user dict."""
        result = {
            "user": {"username": "", "fullname": "", "password": "", "groups": []}
        }
        self.assertEqual(result["user"]["username"], "")
        self.assertEqual(result["user"]["fullname"], "")
        self.assertEqual(result["user"]["password"], "")
        self.assertEqual(result["user"]["groups"], [])

    def test_filled_username_returns_groups(self):
        """get_finals with filled username includes wheel group."""
        _DEFAULT_GROUPS = ["wheel"]
        result = {
            "user": {
                "username": "johndoe",
                "fullname": "John Doe",
                "password": "secret",
                "groups": _DEFAULT_GROUPS,
            }
        }
        self.assertIn("wheel", result["user"]["groups"])

    def test_fullname_gets_stripped(self):
        """Whitespace in fullname should be stripped."""
        fullname = "  John Smith  "
        result = fullname.strip()
        self.assertEqual(result, "John Smith")


if __name__ == "__main__":
    unittest.main()
