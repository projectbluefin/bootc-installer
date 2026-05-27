from types import SimpleNamespace

from bootc_installer.defaults.disk import VanillaDefaultDisk
from bootc_installer.defaults.image import VanillaDefaultImage
from bootc_installer.defaults.user import VanillaDefaultUsers


class TestImageStepShouldShow:
    def test_hidden_when_single_leaf(self):
        assert not VanillaDefaultImage.should_show(object(), {"leaf_count": 1})

    def test_visible_when_multiple_leaves(self):
        assert VanillaDefaultImage.should_show(object(), {"leaf_count": 2})


class TestDiskStepShouldShow:
    def test_hidden_when_single_disk(self):
        assert not VanillaDefaultDisk.should_show(object(), {"disk_count": 1})

    def test_visible_when_multiple_disks(self):
        assert VanillaDefaultDisk.should_show(object(), {"disk_count": 2})

    def test_auto_select_single_disk_populates_partition_recipe(self):
        class FakeDisk:
            disk = "/dev/sda"
            pretty_size = "100 GB"
            size = 100 * 1024**3

        class FakeDisksManager:
            def __init__(self, disk):
                self._disk = disk

            def all_disks(self, include_removable=True):
                return [self._disk]

        class FakeCheckButton:
            def __init__(self, callback):
                self._active = False
                self._callback = callback

            def set_active(self, value):
                if self._active == value:
                    return
                self._active = value
                self._callback(self)

            def get_active(self):
                return self._active

        disk = FakeDisk()
        step = SimpleNamespace()

        def on_toggle(widget):
            if widget.get_active():
                step._VanillaDefaultDisk__selected_disks.append(disk)
                step._VanillaDefaultDisk__selected_disks_sum += disk.size

        step._VanillaDefaultDisk__disks = FakeDisksManager(disk)
        step._VanillaDefaultDisk__registry_disks = [
            SimpleNamespace(disk=disk, chk_button=FakeCheckButton(on_toggle))
        ]
        step._VanillaDefaultDisk__selected_disks = []
        step._VanillaDefaultDisk__selected_disks_sum = 0
        step._VanillaDefaultDisk__use_virtual_disk = False
        step._VanillaDefaultDisk__partition_recipe = None
        step._VanillaDefaultDisk__update_action_buttons = lambda: None
        step._set_auto_partition_recipe = lambda selected_disk: setattr(
            step,
            "_VanillaDefaultDisk__partition_recipe",
            {
                "auto": {
                    "disk": selected_disk.disk,
                    "pretty_size": selected_disk.pretty_size,
                    "size": selected_disk.size,
                    "vgs_to_remove": [],
                    "pvs_to_remove": [],
                }
            },
        )

        assert VanillaDefaultDisk.auto_select_single_disk(step)
        assert step._VanillaDefaultDisk__selected_disks == [disk]
        assert step._VanillaDefaultDisk__selected_disks_sum == disk.size
        assert step._VanillaDefaultDisk__partition_recipe == {
            "auto": {
                "disk": "/dev/sda",
                "pretty_size": "100 GB",
                "size": disk.size,
                "vgs_to_remove": [],
                "pvs_to_remove": [],
            }
        }


class TestUserStepShouldShow:
    def test_uses_selected_image_for_multi_image_catalogs(self):
        window = SimpleNamespace(
            image_step=SimpleNamespace(selected_needs_user_creation=False),
            recipe={},
        )
        step = SimpleNamespace(_VanillaDefaultUsers__window=window)

        assert not VanillaDefaultUsers.should_show(step, {"leaf_count": 2, "sys_recipe": {}})

        window.image_step.selected_needs_user_creation = True
        assert VanillaDefaultUsers.should_show(step, {"leaf_count": 2, "sys_recipe": {}})

    def test_falls_back_to_recipe_images_for_single_image_catalogs(self):
        window = SimpleNamespace(
            image_step=SimpleNamespace(selected_needs_user_creation=False),
            recipe={"images": [{"needs_user_creation": True}]},
        )
        step = SimpleNamespace(_VanillaDefaultUsers__window=window)
        context = {
            "leaf_count": 1,
            "sys_recipe": {"images": [{"needs_user_creation": True}]},
        }

        assert VanillaDefaultUsers.should_show(step, context)
