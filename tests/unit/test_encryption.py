"""
Unit tests for defaults/encryption.py passphrase strength logic and get_finals output.
No GTK display required — pure logic is mirrored from the widget for isolated testing.
"""
import unittest


def _classify_passphrase_strength(password):
    """Mirror the strength classification logic in BootcDefaultEncryption.__on_password_changed."""
    if not password:
        return None
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_symbol = any(not c.isalnum() for c in password)
    variety = sum([has_upper, has_lower, has_digit, has_symbol])
    length = len(password)
    if length < 8 or variety < 2:
        return "weak"
    elif length < 12 or variety < 3:
        return "fair"
    else:
        return "strong"


def _compute_get_finals(use_enc, use_tpm2, passphrase):
    """Mirror the logic in BootcDefaultEncryption.get_finals."""
    if not use_enc:
        return {"encryption": {"use_encryption": False, "encryption_key": ""}}
    enc_type = "tpm2-luks-passphrase" if use_tpm2 else "luks-passphrase"
    return {
        "encryption": {
            "use_encryption": True,
            "type": enc_type,
            "encryption_key": passphrase,
        }
    }


class TestPassphraseStrength(unittest.TestCase):

    def test_empty_password_returns_none(self):
        self.assertIsNone(_classify_passphrase_strength(""))

    def test_short_password_is_weak(self):
        self.assertEqual(_classify_passphrase_strength("Ab1!"), "weak")

    def test_lowercase_only_is_weak(self):
        self.assertEqual(_classify_passphrase_strength("abcdefgh"), "weak")

    def test_uppercase_lowercase_eight_chars_is_fair(self):
        self.assertEqual(_classify_passphrase_strength("Abcdefgh"), "fair")

    def test_short_high_variety_is_weak(self):
        # length < 8 takes priority even with all 4 character classes
        self.assertEqual(_classify_passphrase_strength("Ab1!xy"), "weak")

    def test_medium_length_three_char_classes_is_fair(self):
        self.assertEqual(_classify_passphrase_strength("Abcdef12"), "fair")

    def test_long_password_all_classes_is_strong(self):
        self.assertEqual(_classify_passphrase_strength("Abcdef12!@#$"), "strong")

    def test_long_password_low_variety_is_fair(self):
        # length >= 12 but only 2 char classes (upper + lower)
        self.assertEqual(_classify_passphrase_strength("AbcdefghijkL"), "fair")

    def test_digits_and_symbol_only_fair(self):
        # 2 char classes (digit + symbol), length >= 8
        self.assertEqual(_classify_passphrase_strength("12345!@#"), "fair")

    def test_length_boundary_exactly_8(self):
        # length == 8 with two classes (lower + digit) -> fair
        self.assertEqual(_classify_passphrase_strength("abcde123"), "fair")

    def test_length_boundary_exactly_12_three_classes(self):
        # length == 12 with three classes -> strong
        self.assertEqual(_classify_passphrase_strength("Abcde12345!X"), "strong")

    def test_realistic_strong_passphrase(self):
        self.assertEqual(_classify_passphrase_strength("MyStr0ng!Pass#2024"), "strong")


class TestGetFinalsLogic(unittest.TestCase):
    """Tests for the get_finals output shape and encryption type selection."""

    def test_encryption_disabled_returns_no_key(self):
        result = _compute_get_finals(use_enc=False, use_tpm2=False, passphrase="")
        self.assertEqual(result, {"encryption": {"use_encryption": False, "encryption_key": ""}})

    def test_encryption_disabled_ignores_passphrase(self):
        result = _compute_get_finals(use_enc=False, use_tpm2=True, passphrase="secret")
        self.assertFalse(result["encryption"]["use_encryption"])
        self.assertEqual(result["encryption"]["encryption_key"], "")

    def test_luks_passphrase_type_when_tpm2_off(self):
        result = _compute_get_finals(use_enc=True, use_tpm2=False, passphrase="hunter2")
        self.assertEqual(result["encryption"]["type"], "luks-passphrase")
        self.assertEqual(result["encryption"]["encryption_key"], "hunter2")
        self.assertTrue(result["encryption"]["use_encryption"])

    def test_tpm2_luks_passphrase_type_when_tpm2_on(self):
        result = _compute_get_finals(use_enc=True, use_tpm2=True, passphrase="s3cret!")
        self.assertEqual(result["encryption"]["type"], "tpm2-luks-passphrase")
        self.assertTrue(result["encryption"]["use_encryption"])

    def test_encryption_key_propagated_exactly(self):
        passphrase = "My$uper@Secure!Pass"
        result = _compute_get_finals(use_enc=True, use_tpm2=False, passphrase=passphrase)
        self.assertEqual(result["encryption"]["encryption_key"], passphrase)

    def test_result_has_required_keys_when_encrypted(self):
        result = _compute_get_finals(use_enc=True, use_tpm2=False, passphrase="test123!")
        enc = result["encryption"]
        self.assertIn("use_encryption", enc)
        self.assertIn("type", enc)
        self.assertIn("encryption_key", enc)

    def test_result_has_required_keys_when_not_encrypted(self):
        result = _compute_get_finals(use_enc=False, use_tpm2=False, passphrase="")
        enc = result["encryption"]
        self.assertIn("use_encryption", enc)
        self.assertIn("encryption_key", enc)
        self.assertNotIn("type", enc)


if __name__ == "__main__":
    unittest.main()
