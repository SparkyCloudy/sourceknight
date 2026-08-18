import io
import os
import pathlib
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from sourceknight.context import Context
from sourceknight.dependencies import Dependency
from sourceknight.drivers.base import basedriver
from sourceknight.drivers.file import FileDriver
from sourceknight.drivers.smdrop import SmdropDriver
from sourceknight.drivers.tar import TarDriver
from sourceknight.drivers.zip import ZipDriver
from sourceknight.errors import SkError
from sourceknight.utils import FileManager


def _make_dummy_manifest(tmpdir: str) -> None:
    yaml_content = """project:
  sourceknight: 0.5
  name: test-proj
"""
    with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
        f.write(yaml_content)


class TestBaseDriver(unittest.TestCase):
    def test_basedriver_defaults(self):
        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "base_dep"
        dep.type = "base"
        dep.version = "1.0"

        driver = basedriver(mock_ctx, dep)
        # Default check_update returns True
        self.assertTrue(driver.check_update(None))
        # Default cleanup is a no-op
        driver.cleanup()


class TestFileDriver(unittest.TestCase):
    def test_file_driver_lifecycle_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            src_dir = os.path.join(tmpdir, "local_sdk")
            os.makedirs(os.path.join(src_dir, "addons", "sourcemod", "scripting", "include"))
            with open(os.path.join(src_dir, "addons", "sourcemod", "scripting", "include", "sdk.inc"), "w") as f:
                f.write("// sdk")

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "local_sdk"
                dep.type = "file"
                dep.params = {"location": "local_sdk"}

                driver = FileDriver(ctx, dep)
                self.assertTrue(driver.check_update(None))

                with FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    self.assertIn("local_sdk", ctx.state.dependencies)

                with FileManager(ctx, "build") as bmgr:
                    driver.unpack(bmgr, [])
                    self.assertIn("local_sdk", ctx.state.build)
                    dest_inc = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "include", "sdk.inc")
                    self.assertTrue(os.path.exists(dest_inc))

                driver.cleanup()


class TestTarAndZipDrivers(unittest.TestCase):
    def test_zip_driver_lifecycle_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            zip_path = os.path.join(tmpdir, "test.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("addons/sourcemod/scripting/include/lib.inc", "// lib header")

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "ziplib"
                dep.type = "zip"
                dep.params = {"location": pathlib.Path(zip_path).as_uri()}
                dep.version = "1.0"

                driver = ZipDriver(ctx, dep)
                self.assertTrue(driver.check_update(None))

                with FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    self.assertIn("ziplib", ctx.state.dependencies)

                with FileManager(ctx, "build") as bmgr:
                    driver.unpack(bmgr, [])
                    self.assertIn("ziplib", ctx.state.build)
                    dest_inc = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "include", "lib.inc")
                    self.assertTrue(os.path.exists(dest_inc))

                driver.cleanup()

    def test_tar_driver_lifecycle_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            tar_path = os.path.join(tmpdir, "test.tar.gz")
            with tarfile.open(tar_path, "w:gz") as tf:
                content = b"// tarlib header"
                ti = tarfile.TarInfo("addons/sourcemod/scripting/include/tarlib.inc")
                ti.size = len(content)
                tf.addfile(ti, io.BytesIO(content))

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "tarlib"
                dep.type = "tar"
                dep.params = {"location": pathlib.Path(tar_path).as_uri()}
                dep.version = "1.0"

                driver = TarDriver(ctx, dep)
                self.assertTrue(driver.check_update(None))

                with FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    self.assertIn("tarlib", ctx.state.dependencies)

                with FileManager(ctx, "build") as bmgr:
                    driver.unpack(bmgr, [])
                    self.assertIn("tarlib", ctx.state.build)
                    dest_inc = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "include", "tarlib.inc")
                    self.assertTrue(os.path.exists(dest_inc))

                driver.cleanup()


class TestSmdropDriverDeep(unittest.TestCase):
    def test_smdrop_platform_info(self):
        mock_ctx = MagicMock()
        dep = Dependency()
        driver = SmdropDriver(mock_ctx, dep)

        with patch("platform.system", return_value="Linux"):
            self.assertEqual(driver._get_platform_info(), ("linux", ".tar.gz"))

        with patch("platform.system", return_value="Windows"):
            self.assertEqual(driver._get_platform_info(), ("windows", ".zip"))

    @patch("requests.get")
    def test_smdrop_resolution_branch(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "sourcemod-1.12.0-git7249-windows.zip\n"
        mock_get.return_value = mock_resp

        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "sourcemod"
        dep.type = "smdrop"
        dep.version = "1.12.x"

        driver = SmdropDriver(mock_ctx, dep)
        with patch.object(driver, "_get_platform_info", return_value=("windows", ".zip")):
            url = driver._resolve_url()
            self.assertIn("sourcemod-latest-windows", mock_get.call_args[0][0])
            self.assertEqual(url, "https://sm.alliedmods.net/smdrop/1.12/sourcemod-1.12.0-git7249-windows.zip")

    def test_smdrop_resolution_explicit_archive(self):
        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "sourcemod"
        dep.type = "smdrop"
        dep.version = "1.11.0-git6930-linux.tar.gz"

        driver = SmdropDriver(mock_ctx, dep)
        with patch.object(driver, "_get_platform_info", return_value=("linux", ".tar.gz")):
            url = driver._resolve_url()
            self.assertEqual(url, "https://sm.alliedmods.net/smdrop/1.11/1.11.0-git6930-linux.tar.gz")

    def test_smdrop_resolution_invalid_format(self):
        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "sourcemod"
        dep.type = "smdrop"
        dep.version = "invalid_format_xyz"

        driver = SmdropDriver(mock_ctx, dep)
        with self.assertRaises(SkError) as cm:
            driver._resolve_url()
        self.assertIn("Invalid smdrop version format", str(cm.exception))

    def test_smdrop_check_update_logic(self):
        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "sourcemod"
        dep.version = "1.12.x"
        driver = SmdropDriver(mock_ctx, dep)

        # None current -> True
        self.assertTrue(driver.check_update(None))

        # Different version -> True
        curr_diff = Dependency()
        curr_diff.version = "1.11.x"
        self.assertTrue(driver.check_update(curr_diff))

        # Same version with missing location -> True
        curr_same = Dependency()
        curr_same.version = "1.12.x"
        curr_same.params = {"location": "missing/path/sm.zip"}
        self.assertTrue(driver.check_update(curr_same))

    def test_smdrop_update_unpack_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            zip_path = os.path.join(tmpdir, "sm_mock.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("addons/sourcemod/scripting/spcomp.exe", "compiler binary")

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "sourcemod"
                dep.type = "smdrop"
                dep.version = "1.12.x"
                dep.params = {"location": pathlib.Path(zip_path).as_uri()}

                driver = SmdropDriver(ctx, dep)
                with patch.object(driver, "_resolve_url", return_value=pathlib.Path(zip_path).as_uri()), FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    self.assertIn("sourcemod", ctx.state.dependencies)

                dep.params["location"] = ctx.state.dependencies["sourcemod"]["location"]
                with FileManager(ctx, "build") as bmgr:
                    driver.unpack(bmgr, [])
                    dest_bin = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "spcomp.exe")
                    self.assertTrue(os.path.exists(dest_bin))

                driver.cleanup()

    def test_smdrop_tar_unpack(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            tar_path = os.path.join(tmpdir, "sm_mock.tar.gz")
            with tarfile.open(tar_path, "w:gz") as tf:
                content = b"compiler binary linux"
                ti = tarfile.TarInfo("addons/sourcemod/scripting/spcomp")
                ti.size = len(content)
                tf.addfile(ti, io.BytesIO(content))

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "sourcemod_tar"
                dep.type = "smdrop"
                dep.version = "1.12.x"
                dep.params = {"location": os.path.relpath(tar_path, tmpdir)}

                driver = SmdropDriver(ctx, dep)
                with FileManager(ctx, "build") as bmgr:
                    driver.unpack(bmgr, [])
                    dest_bin = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "spcomp")
                    self.assertTrue(os.path.exists(dest_bin))


if __name__ == "__main__":
    unittest.main()
