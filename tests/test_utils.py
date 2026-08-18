import io
import os
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sourceknight.context import Context
from sourceknight.dependencies import Dependency
from sourceknight.utils import (
    FileManager,
    LocalFileAdapter,
    SkVersion,
    adjust_sourcemod_platform,
    cd,
    ensure_path_exists,
    extract_and_copy,
    once,
    resolve_heuristic_locations,
    tar_is_within_directory,
    tar_safe_extract,
)


def _make_dummy_manifest(tmpdir: str) -> None:
    yaml_content = """project:
  sourceknight: 0.5
  name: test-proj
"""
    with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
        f.write(yaml_content)


class TestFileManager(unittest.TestCase):
    def test_file_manager_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                with FileManager(ctx, "temp_cache") as fmgr:
                    self.assertTrue(os.path.isdir(fmgr.path))
                    tmp_file = os.path.join(fmgr.path, "temp.txt")
                    with open(tmp_file, "w") as f:
                        f.write("content")
                    fmgr._tmpfiles.append(tmp_file)

                # After context exit, tracked temp file should be unlinked
                self.assertFalse(os.path.exists(tmp_file))

    def test_file_manager_release(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                with FileManager(ctx, "temp_cache") as fmgr:
                    tmp_file = os.path.join(fmgr.path, "keep.txt")
                    with open(tmp_file, "w") as f:
                        f.write("keep me")
                    fmgr._tmpfiles.append(tmp_file)
                    fmgr.release(tmp_file)

                # Released file should still exist
                self.assertTrue(os.path.exists(tmp_file))


class TestLocalFileAdapter(unittest.TestCase):
    def test_local_file_adapter_chkpath(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_file = os.path.join(tmpdir, "sample.txt")
            with open(sample_file, "w") as f:
                f.write("sample text")

            # 200 OK
            status, _ = LocalFileAdapter._chkpath("GET", sample_file)
            self.assertEqual(status, 200)

            # 400 Path Is Directory
            status, _ = LocalFileAdapter._chkpath("GET", tmpdir)
            self.assertEqual(status, 400)

            # 404 File Not Found
            status, _ = LocalFileAdapter._chkpath("GET", os.path.join(tmpdir, "missing.txt"))
            self.assertEqual(status, 404)

            # 405 Method Not Allowed
            status, _ = LocalFileAdapter._chkpath("POST", sample_file)
            self.assertEqual(status, 405)

            # 501 Not Implemented
            status, _ = LocalFileAdapter._chkpath("DELETE", sample_file)
            self.assertEqual(status, 501)


class TestUtilsFunctions(unittest.TestCase):
    def test_once_decorator(self):
        call_count = 0

        @once
        def calculate(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        self.assertEqual(calculate(5), 10)
        self.assertEqual(calculate(10), 10)  # Cached
        self.assertEqual(call_count, 1)

    def test_cd_context_manager(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir, cd(tmpdir):
            self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(tmpdir))
        self.assertEqual(os.getcwd(), original_cwd)

    def test_ensure_path_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "nested", "sub", "dir")
            ensure_path_exists(target)
            self.assertTrue(os.path.isdir(target))

    def test_adjust_sourcemod_platform(self):
        dep = Dependency()
        dep.name = "sourcemod"
        dep.type = "tar"
        dep.params = {"location": "http://example.com/sourcemod-windows.zip"}

        with patch("platform.system", return_value="Linux"):
            adjusted = adjust_sourcemod_platform(dep)
            self.assertIn("linux.tar.gz", adjusted.params["location"])
            self.assertEqual(adjusted.type, "tar")

        dep2 = Dependency()
        dep2.name = "sourcemod"
        dep2.type = "tar"
        dep2.params = {"location": "http://example.com/sourcemod-linux.tar.gz"}

        with patch("platform.system", return_value="Windows"):
            adjusted2 = adjust_sourcemod_platform(dep2)
            self.assertIn("windows.zip", adjusted2.params["location"])
            self.assertEqual(adjusted2.type, "zip")

    def test_sk_version_compatibility(self):
        v_current = SkVersion("0.5")
        v_compat = SkVersion("0.5.0")
        self.assertFalse(v_current.compatibility(v_compat).major)
        self.assertFalse(v_current.compatibility(v_compat).newer)

        v_major_diff = SkVersion("1.0")
        self.assertTrue(v_current.compatibility(v_major_diff).major)

        v_newer_req = SkVersion("0.9")
        self.assertTrue(v_current.compatibility(v_newer_req).newer)
        self.assertEqual(str(v_current), "0.5")

    def test_resolve_heuristic_locations_all_variants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Non existent path
            self.assertEqual(resolve_heuristic_locations(os.path.join(tmpdir, "none")), [])

            # 2. Root addons/
            dir_addons = os.path.join(tmpdir, "with_addons")
            os.makedirs(os.path.join(dir_addons, "addons"))
            self.assertEqual(
                resolve_heuristic_locations(dir_addons),
                [{"source": "/addons", "dest": "/addons"}],
            )

            # 3. Nested game/addons/
            dir_nested = os.path.join(tmpdir, "with_nested")
            os.makedirs(os.path.join(dir_nested, "game", "addons"))
            self.assertEqual(
                resolve_heuristic_locations(dir_nested),
                [{"source": "/game/addons", "dest": "/addons"}],
            )

            # 4. Standard directories (scripting, plugins, gamedata)
            dir_std = os.path.join(tmpdir, "with_std")
            os.makedirs(os.path.join(dir_std, "scripting"))
            os.makedirs(os.path.join(dir_std, "gamedata"))
            locs = resolve_heuristic_locations(dir_std)
            dest_list = [rule["dest"] for rule in locs]
            self.assertIn("/addons/sourcemod/scripting", dest_list)
            self.assertIn("/addons/sourcemod/gamedata", dest_list)

            # 5. Loose .inc files
            dir_loose = os.path.join(tmpdir, "with_loose")
            os.makedirs(dir_loose)
            with open(os.path.join(dir_loose, "sample.inc"), "w") as f:
                f.write("// sample")
            locs_loose = resolve_heuristic_locations(dir_loose)
            self.assertEqual(len(locs_loose), 1)
            self.assertEqual(locs_loose[0]["dest"], "/addons/sourcemod/scripting/include/sample.inc")

    def test_tar_safe_extract_and_traversal_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tar_path = os.path.join(tmpdir, "safe.tar.gz")
            with tarfile.open(tar_path, "w:gz") as tf:
                content = b"// safe header"
                ti = tarfile.TarInfo("safe.inc")
                ti.size = len(content)
                tf.addfile(ti, io.BytesIO(content))

            extract_target = os.path.join(tmpdir, "extracted")
            os.makedirs(extract_target)
            with tarfile.open(tar_path, "r:gz") as tf:
                tar_safe_extract(tf, extract_target)
            self.assertTrue(os.path.exists(os.path.join(extract_target, "safe.inc")))

        # Test path traversal prevention
        self.assertFalse(tar_is_within_directory("/safe/dir", "/safe/dir/../../etc/passwd"))

    def test_extract_and_copy_with_heuristic_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(os.path.join(src_dir, "addons", "sourcemod", "scripting", "include"))

            with open(os.path.join(src_dir, "addons", "sourcemod", "scripting", "include", "test.inc"), "w") as f:
                f.write("// inc")

            mock_drv = MagicMock()
            mock_drv.model.name = "test_dep"

            with Context(tmpdir) as ctx, FileManager(ctx, "build") as bmgr:
                mock_tmp = MagicMock()
                mock_tmp.path = src_dir
                extract_and_copy(mock_drv, [], bmgr, mock_tmp)

                target_inc = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "include", "test.inc")
                self.assertTrue(os.path.exists(target_inc))


if __name__ == "__main__":
    unittest.main()
