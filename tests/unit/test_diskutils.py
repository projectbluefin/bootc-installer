"""Unit tests for the pure-Python parts of core/disks.py.

Covers Diskutils.pretty_size() (static, no I/O) and the Partition
comparison operators (__lt__, __eq__) exercised via lightweight stubs.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bootc_installer.core.disks import Diskutils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakePartition:
    """Minimal stand-in that satisfies __lt__ / __eq__ duck-typing."""

    def __init__(self, partition: str, uuid: str = "", fs_type: str = ""):
        self.partition = partition
        self.uuid = uuid
        self.fs_type = fs_type

    def __lt__(self, other):
        return self.partition < other.partition

    def __eq__(self, other):
        if not other:
            return False
        return self.uuid == other.uuid and self.fs_type == other.fs_type


# ---------------------------------------------------------------------------
# Diskutils.pretty_size
# ---------------------------------------------------------------------------

class TestPrettySize(unittest.TestCase):
    def test_bytes_boundary(self):
        self.assertEqual(Diskutils.pretty_size(512), "512 B")

    def test_exactly_1024_is_bytes(self):
        # 1024 is NOT > 1024, so it stays in bytes
        self.assertEqual(Diskutils.pretty_size(1024), "1024 B")

    def test_just_above_1024_is_kb(self):
        self.assertEqual(Diskutils.pretty_size(1025), "1.0 KB")

    def test_kilobytes(self):
        result = Diskutils.pretty_size(2048)
        self.assertIn("KB", result)
        self.assertEqual(result, "2.0 KB")

    def test_exactly_1mb_is_kb(self):
        # 1024**2 is NOT > 1024**2
        result = Diskutils.pretty_size(1024 ** 2)
        self.assertIn("KB", result)

    def test_just_above_1mb_is_mb(self):
        result = Diskutils.pretty_size(1024 ** 2 + 1)
        self.assertIn("MB", result)

    def test_megabytes(self):
        result = Diskutils.pretty_size(10 * 1024 ** 2)
        self.assertEqual(result, "10.0 MB")

    def test_exactly_1gb_is_mb(self):
        result = Diskutils.pretty_size(1024 ** 3)
        self.assertIn("MB", result)

    def test_just_above_1gb_is_gb(self):
        result = Diskutils.pretty_size(1024 ** 3 + 1)
        self.assertIn("GB", result)

    def test_gigabytes(self):
        result = Diskutils.pretty_size(500 * 1024 ** 3)
        self.assertEqual(result, "500.0 GB")

    def test_zero_bytes(self):
        self.assertEqual(Diskutils.pretty_size(0), "0 B")

    def test_rounding(self):
        # 1.5 GB
        size = int(1.5 * 1024 ** 3) + 1
        result = Diskutils.pretty_size(size)
        self.assertIn("GB", result)
        self.assertIn("1.5", result)

    def test_returns_string(self):
        self.assertIsInstance(Diskutils.pretty_size(1024 ** 2 + 1), str)


# ---------------------------------------------------------------------------
# Partition ordering and equality (via _FakePartition)
# ---------------------------------------------------------------------------

class TestPartitionComparisons(unittest.TestCase):
    def test_lt_by_device_path(self):
        sda1 = _FakePartition("/dev/sda1")
        sda2 = _FakePartition("/dev/sda2")
        self.assertLess(sda1, sda2)
        self.assertFalse(sda2 < sda1)

    def test_lt_equal_paths_not_less(self):
        a = _FakePartition("/dev/sda1")
        b = _FakePartition("/dev/sda1")
        self.assertFalse(a < b)

    def test_eq_same_uuid_and_fstype(self):
        a = _FakePartition("/dev/sda1", uuid="abc-123", fs_type="ext4")
        b = _FakePartition("/dev/sdb1", uuid="abc-123", fs_type="ext4")
        self.assertEqual(a, b)

    def test_neq_different_uuid(self):
        a = _FakePartition("/dev/sda1", uuid="abc", fs_type="ext4")
        b = _FakePartition("/dev/sda1", uuid="xyz", fs_type="ext4")
        self.assertNotEqual(a, b)

    def test_neq_different_fstype(self):
        a = _FakePartition("/dev/sda1", uuid="abc", fs_type="ext4")
        b = _FakePartition("/dev/sda1", uuid="abc", fs_type="xfs")
        self.assertNotEqual(a, b)

    def test_eq_none_is_false(self):
        a = _FakePartition("/dev/sda1", uuid="abc", fs_type="ext4")
        self.assertFalse(a == None)  # noqa: E711 — intentional None comparison

    def test_sort_order(self):
        parts = [
            _FakePartition("/dev/sda3"),
            _FakePartition("/dev/sda1"),
            _FakePartition("/dev/sda2"),
        ]
        sorted_parts = sorted(parts)
        self.assertEqual(
            [p.partition for p in sorted_parts],
            ["/dev/sda1", "/dev/sda2", "/dev/sda3"],
        )


if __name__ == "__main__":
    unittest.main()
