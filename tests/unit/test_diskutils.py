"""Unit tests for the pure-Python parts of core/disks.py.

Covers Diskutils.pretty_size() (static, no I/O) and the Partition
comparison operators (__lt__, __eq__) exercised via lightweight stubs.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bootc_installer.core.disks import Disk as _Disk
from bootc_installer.core.disks import Diskutils
from bootc_installer.core.disks import Partition as _Partition


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


# ---------------------------------------------------------------------------
# Diskutils — subprocess-dependent methods
# ---------------------------------------------------------------------------

class TestSeparateDeviceAndPartn(unittest.TestCase):
    """Tests for Diskutils.separate_device_and_partn()."""

    def _mock_output(self, name, pkname, partn):
        payload = json.dumps({
            "blockdevices": [{"name": name, "pkname": pkname, "partn": partn}]
        })
        return payload.encode()

    def test_partition_returns_disk_and_number(self):
        with patch("subprocess.check_output",
                   return_value=self._mock_output("nvme0n1p2", "nvme0n1", 2)):
            disk, num = Diskutils.separate_device_and_partn("/dev/nvme0n1p2")
        self.assertEqual(disk, "/dev/nvme0n1")
        self.assertEqual(num, "2")

    def test_bare_device_returns_none_for_partn(self):
        with patch("subprocess.check_output",
                   return_value=self._mock_output("sda", None, None)):
            disk, num = Diskutils.separate_device_and_partn("/dev/sda")
        self.assertEqual(disk, "/dev/sda")
        self.assertIsNone(num)

    def test_multiple_devices_raises_value_error(self):
        payload = json.dumps({
            "blockdevices": [
                {"name": "sda1", "pkname": "sda", "partn": 1},
                {"name": "sdb1", "pkname": "sdb", "partn": 1},
            ]
        }).encode()
        with patch("subprocess.check_output", return_value=payload):
            with self.assertRaises(ValueError):
                Diskutils.separate_device_and_partn("/dev/sda1")


class TestFetchLvmPvs(unittest.TestCase):
    """Tests for Diskutils.fetch_lvm_pvs()."""

    def test_returns_pv_vg_pairs(self):
        payload = json.dumps({
            "report": [{"pv": [
                {"pv_name": "/dev/sda2", "vg_name": "vg_data"},
                {"pv_name": "/dev/sdb1", "vg_name": ""},
            ]}]
        }).encode()
        with patch("subprocess.check_output", return_value=payload):
            result = Diskutils.fetch_lvm_pvs()
        self.assertEqual(result, [["/dev/sda2", "vg_data"], ["/dev/sdb1", None]])

    def test_empty_vg_name_becomes_none(self):
        payload = json.dumps({
            "report": [{"pv": [{"pv_name": "/dev/sdc1", "vg_name": ""}]}]
        }).encode()
        with patch("subprocess.check_output", return_value=payload):
            result = Diskutils.fetch_lvm_pvs()
        self.assertEqual(result, [["/dev/sdc1", None]])

    def test_returns_empty_list_on_exception(self):
        with patch("subprocess.check_output", side_effect=Exception("pvs not found")):
            result = Diskutils.fetch_lvm_pvs()
        self.assertEqual(result, [])


class TestGetBootDisk(unittest.TestCase):
    """Tests for Diskutils.get_boot_disk()."""

    def _make_check_output(self, findmnt_output, lsblk_output, pkname_output=""):
        call_count = [0]

        def fake_check_output(cmd, **kwargs):
            call_count[0] += 1
            if "findmnt" in cmd and "pkname" not in cmd:
                return findmnt_output.encode()
            elif "lsblk -sno" in cmd:
                return lsblk_output.encode()
            elif "pkname" in cmd:
                return pkname_output.encode()
            return b""

        return fake_check_output

    def test_detects_disk_from_lsblk_tree(self):
        fake = self._make_check_output(
            findmnt_output="/dev/nvme0n1p3",
            lsblk_output="nvme0n1p3 part\nnvme0n1  disk\n",
        )
        with patch("subprocess.check_output", side_effect=fake):
            result = Diskutils.get_boot_disk()
        self.assertEqual(result, "/dev/nvme0n1")

    def test_falls_back_to_pkname(self):
        def fake(cmd, **kwargs):
            if "findmnt" in cmd:
                return b"/dev/sda2"
            if "lsblk -sno" in cmd:
                return b"sda2 part\n"  # no "disk" type in output
            if "pkname" in cmd:
                return b"sda"
            return b""

        with patch("subprocess.check_output", side_effect=fake):
            result = Diskutils.get_boot_disk()
        self.assertEqual(result, "/dev/sda")

    def test_returns_none_on_exception(self):
        with patch("subprocess.check_output", side_effect=Exception("no findmnt")):
            result = Diskutils.get_boot_disk()
        self.assertIsNone(result)

    def test_returns_none_when_no_source_found(self):
        import subprocess as _sp

        def fake(cmd, **kwargs):
            raise _sp.CalledProcessError(1, cmd)

        with patch("subprocess.check_output", side_effect=fake):
            result = Diskutils.get_boot_disk()
        self.assertIsNone(result)

    def test_returns_source_when_pkname_empty(self):
        """When pkname lookup returns empty, returns the raw source device."""
        def fake(cmd, **kwargs):
            if "findmnt" in cmd and "pkname" not in cmd:
                return b"/dev/sda"
            if "lsblk -sno" in cmd:
                return b"sda part\n"  # no "disk" type
            if "pkname" in cmd:
                return b""  # empty pkname
            return b""

        with patch("subprocess.check_output", side_effect=fake):
            result = Diskutils.get_boot_disk()
        self.assertEqual(result, "/dev/sda")


# ---------------------------------------------------------------------------
# Disk class — using __new__ + attribute injection (avoids sysfs reads)
# ---------------------------------------------------------------------------

def _make_stub_disk(name="nvme0n1", size=500 * 1024 ** 3):
    """Create a Disk without calling __init__ (no sysfs I/O)."""
    d = _Disk.__new__(_Disk)
    d._Disk__disk = name
    d._Disk__partitions = []
    d._Disk__size = size
    return d


class TestDiskClass(unittest.TestCase):
    """Tests for the Disk class properties using lightweight stubs."""

    def test_disk_property(self):
        d = _make_stub_disk(name="nvme0n1")
        self.assertEqual(d.disk, "/dev/nvme0n1")

    def test_name_property(self):
        d = _make_stub_disk(name="sda")
        self.assertEqual(d.name, "sda")

    def test_block_property(self):
        d = _make_stub_disk(name="nvme0n1")
        self.assertEqual(d.block, "/sys/block/nvme0n1")

    def test_size_property(self):
        d = _make_stub_disk(size=1000 * 512)
        self.assertEqual(d.size, 1000 * 512)

    def test_pretty_size_gb(self):
        d = _make_stub_disk(size=500 * 1024 ** 3 + 1)
        self.assertIn("GB", d.pretty_size)

    def test_pretty_size_mb(self):
        d = _make_stub_disk(size=5 * 1024 ** 2 + 1)
        self.assertIn("MB", d.pretty_size)

    def test_pretty_size_kb(self):
        d = _make_stub_disk(size=2 * 1024 + 1)
        self.assertIn("KB", d.pretty_size)

    def test_pretty_size_bytes(self):
        d = _make_stub_disk(size=512)
        self.assertIn("B", d.pretty_size)
        self.assertNotIn("K", d.pretty_size)

    def test_model_reads_from_sysfs(self):
        d = _make_stub_disk(name="nvme0n1")
        import io
        with patch("builtins.open",
                   return_value=io.StringIO("Samsung 980 Pro\n")):
            result = d.model
        self.assertEqual(result, "Samsung 980 Pro")

    def test_model_falls_back_on_oserror(self):
        d = _make_stub_disk(name="nvme0n1")
        with patch("builtins.open", side_effect=OSError("not found")):
            result = d.model
        self.assertEqual(result, "")

    def test_vendor_reads_from_sysfs(self):
        d = _make_stub_disk(name="sda")
        import io
        with patch("builtins.open", return_value=io.StringIO("WDC\n")):
            result = d.vendor
        self.assertEqual(result, "WDC")

    def test_vendor_falls_back_on_oserror(self):
        d = _make_stub_disk(name="sda")
        with patch("builtins.open", side_effect=OSError):
            result = d.vendor
        self.assertEqual(result, "")

    def test_display_name_combines_vendor_and_model(self):
        d = _make_stub_disk(name="nvme0n1")
        import io
        # display_name accesses self.vendor first, then self.model
        open_calls = iter([io.StringIO("Samsung\n"), io.StringIO("980 Pro\n")])
        with patch("builtins.open", side_effect=lambda *a, **kw: next(open_calls)):
            name = d.display_name
        self.assertEqual(name, "Samsung 980 Pro")

    def test_display_name_falls_back_to_disk_name(self):
        d = _make_stub_disk(name="nvme0n1")
        with patch("builtins.open", side_effect=OSError):
            name = d.display_name
        self.assertEqual(name, "nvme0n1")

    def test_is_removable_true(self):
        d = _make_stub_disk(name="sdb")
        import io
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", return_value=io.StringIO("1\n")):
            self.assertTrue(d.is_removable)


    def test_is_removable_false_when_value_is_zero(self):
        d = _make_stub_disk(name="nvme0n1")
        import io
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", return_value=io.StringIO("0\n")):
            self.assertFalse(d.is_removable)

    def test_is_removable_false_when_no_sysfs_file(self):
        d = _make_stub_disk(name="nvme0n1")
        with patch("os.path.isfile", return_value=False):
            self.assertFalse(d.is_removable)

    def test_get_partition_returns_matching_mountpoint(self):
        """get_partition finds the partition with the given mountpoint."""
        d = _make_stub_disk()

        class _FakePart:
            def __init__(self, mp):
                self.mountpoint = mp

        d._Disk__partitions = [_FakePart("/boot"), _FakePart("/"), _FakePart(None)]
        result = d.get_partition("/")
        self.assertIsNotNone(result)
        self.assertEqual(result.mountpoint, "/")

    def test_get_partition_returns_none_when_not_found(self):
        d = _make_stub_disk()
        d._Disk__partitions = []
        self.assertIsNone(d.get_partition("/nonexistent"))

    def test_partitions_property(self):
        d = _make_stub_disk()
        d._Disk__partitions = ["fake"]
        self.assertEqual(d.partitions, ["fake"])

    def test_update_partitions_repopulates(self):
        """update_partitions calls __get_partitions which reads /sys/block/<disk>."""
        d = _make_stub_disk(name="nvme0n1")
        d._Disk__partitions = []
        with patch("os.listdir", return_value=[]), \
             patch("builtins.open", return_value=__import__("io").StringIO("0")):
            d.update_partitions()
        self.assertEqual(d._Disk__partitions, [])


class TestDiskInit(unittest.TestCase):
    """Tests for Disk.__init__ via mocked I/O to cover construction paths."""

    def test_disk_constructor_with_no_partitions(self):
        """Disk() with an empty /sys/block/<disk> directory sets empty partition list."""
        import io

        with patch("os.listdir", return_value=[]), \
             patch("builtins.open", return_value=io.StringIO("1953525168\n")):
            from bootc_installer.core.disks import Disk
            d = Disk("nvme0n1")

        self.assertEqual(d.disk, "/dev/nvme0n1")
        self.assertEqual(d.partitions, [])
        self.assertEqual(d.size, 1953525168 * 512)

    def test_disk_constructor_with_partition_listed(self):
        """Disk() adds Partition objects for each child entry that starts with disk name."""
        import io

        # open_calls: disk size, then one size per matching partition
        # nvme0n1p1 and nvme0n1p2 start with "nvme0n1"; "queue" does not
        open_calls = [
            io.StringIO("1953525168\n"),   # Disk size
            io.StringIO("0\n"),             # nvme0n1p1 partition size
            io.StringIO("0\n"),             # nvme0n1p2 partition size
        ]
        open_idx = [0]

        def fake_open(path, *a, **kw):
            idx = open_idx[0]
            open_idx[0] += 1
            return open_calls[idx]

        def fake_check_output(cmd, **kw):
            # All subprocess calls return empty for mountpoint, fstype, uuid, label
            return b""

        with patch("os.listdir", return_value=["nvme0n1p1", "queue", "nvme0n1p2"]), \
             patch("builtins.open", side_effect=fake_open), \
             patch("subprocess.check_output", side_effect=fake_check_output):
            from bootc_installer.core.disks import Disk
            d = Disk("nvme0n1")

        # Only nvme0n1p1 and nvme0n1p2 start with "nvme0n1"; "queue" does not
        self.assertEqual(len(d.partitions), 2)


# ---------------------------------------------------------------------------
# Partition construction via real __init__ with mocked subprocess
# ---------------------------------------------------------------------------

class TestPartitionInit(unittest.TestCase):
    """Tests for Partition.__init__ via mocked I/O."""

    def _make_partition(self, mountpoint=b"", fs_type=b"xfs", uuid=b"abc-123", label=b""):
        import io

        outputs = [mountpoint, fs_type, uuid, label]
        call_idx = [0]

        def fake_check_output(cmd, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx < len(outputs):
                return outputs[idx]
            return b""

        with patch("subprocess.check_output", side_effect=fake_check_output), \
             patch("builtins.open", return_value=io.StringIO("2097152\n")):
            from bootc_installer.core.disks import Partition
            return Partition("nvme0n1", "nvme0n1p2")

    def test_partition_init_sets_properties(self):
        p = self._make_partition(mountpoint=b"/", fs_type=b"xfs", uuid=b"abc-123", label=b"root")
        self.assertEqual(p.mountpoint, "/")
        self.assertEqual(p.fs_type, "xfs")
        self.assertEqual(p.uuid, "abc-123")
        self.assertEqual(p.label, "root")
        self.assertEqual(p.size, 2097152 * 512)

    def test_partition_init_handles_subprocess_errors(self):
        """CalledProcessError from any subprocess returns None gracefully."""
        import subprocess as _sp

        def raise_cpe(cmd, **kw):
            raise _sp.CalledProcessError(1, cmd)

        import io
        with patch("subprocess.check_output", side_effect=raise_cpe), \
             patch("builtins.open", return_value=io.StringIO("0\n")):
            from bootc_installer.core.disks import Partition
            p = Partition("sda", "sda1")

        self.assertIsNone(p.mountpoint)
        self.assertIsNone(p.fs_type)
        self.assertIsNone(p.uuid)
        self.assertIsNone(p.label)



# ---------------------------------------------------------------------------
# Partition class — using __new__ + attribute injection
# ---------------------------------------------------------------------------


def _make_stub_partition(disk="nvme0n1", partition="nvme0n1p2",
                          mountpoint="/", size=512 * 1024 ** 3,
                          fs_type="xfs", uuid="abc-123", label="root"):
    """Create a Partition without calling __init__ (no subprocess/sysfs I/O)."""
    p = _Partition.__new__(_Partition)
    p._Partition__disk = disk
    p._Partition__partition = partition
    p._Partition__mountpoint = mountpoint
    p._Partition__size = size
    p._Partition__fs_type = fs_type
    p._Partition__uuid = uuid
    p._Partition__label = label
    return p


class TestPartitionClass(unittest.TestCase):
    """Tests for the Partition class properties via lightweight stubs."""

    def test_partition_property(self):
        p = _make_stub_partition(partition="nvme0n1p2")
        self.assertEqual(p.partition, "/dev/nvme0n1p2")

    def test_block_property(self):
        p = _make_stub_partition(disk="nvme0n1", partition="nvme0n1p2")
        self.assertEqual(p.block, "/sys/block/nvme0n1/nvme0n1p2")

    def test_mountpoint_property(self):
        p = _make_stub_partition(mountpoint="/boot")
        self.assertEqual(p.mountpoint, "/boot")

    def test_size_property(self):
        p = _make_stub_partition(size=1000)
        self.assertEqual(p.size, 1000)

    def test_pretty_size_gb(self):
        p = _make_stub_partition(size=500 * 1024 ** 3 + 1)
        self.assertIn("GB", p.pretty_size)

    def test_pretty_size_mb(self):
        p = _make_stub_partition(size=10 * 1024 ** 2 + 1)
        self.assertIn("MB", p.pretty_size)

    def test_pretty_size_kb(self):
        p = _make_stub_partition(size=2 * 1024 + 1)
        self.assertIn("KB", p.pretty_size)

    def test_pretty_size_bytes(self):
        p = _make_stub_partition(size=512)
        self.assertIn("B", p.pretty_size)
        self.assertNotIn("K", p.pretty_size)

    def test_fs_type_property(self):
        p = _make_stub_partition(fs_type="ext4")
        self.assertEqual(p.fs_type, "ext4")

    def test_uuid_property(self):
        p = _make_stub_partition(uuid="deadbeef")
        self.assertEqual(p.uuid, "deadbeef")

    def test_label_property(self):
        p = _make_stub_partition(label="EFI")
        self.assertEqual(p.label, "EFI")

    def test_lt_by_device_path(self):
        p1 = _make_stub_partition(partition="nvme0n1p1")
        p2 = _make_stub_partition(partition="nvme0n1p2")
        self.assertLess(p1, p2)

    def test_eq_same_uuid_and_fstype(self):
        p1 = _make_stub_partition(partition="nvme0n1p2", uuid="abc", fs_type="xfs")
        p2 = _make_stub_partition(partition="sda1", uuid="abc", fs_type="xfs")
        self.assertEqual(p1, p2)

    def test_neq_different_uuid(self):
        p1 = _make_stub_partition(uuid="abc", fs_type="xfs")
        p2 = _make_stub_partition(uuid="xyz", fs_type="xfs")
        self.assertNotEqual(p1, p2)

    def test_eq_none_is_false(self):
        p = _make_stub_partition()
        self.assertFalse(p == None)  # noqa: E711


if __name__ == "__main__":
    unittest.main()
