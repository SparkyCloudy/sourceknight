import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from sourceknight.context import Context
from sourceknight.dependencies import Dependency
from sourceknight.drivers.git import GitDriver
from sourceknight.drivers.release import ReleaseDriver
from sourceknight.errors import SkError
from sourceknight.utils import FileManager


def _make_dummy_manifest(tmpdir: str) -> None:
    yaml_content = """project:
  sourceknight: 0.5
  name: test-proj
"""
    with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
        f.write(yaml_content)


class TestGitDriver(unittest.TestCase):
    @patch("git.Repo.clone_from")
    def test_git_shallow_clone_success(self, mock_clone):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "mygit"
                dep.type = "git"
                dep.params = {"repo": "https://github.com/example/repo"}
                dep.version = "v1.0"

                driver = GitDriver(ctx, dep)
                self.assertTrue(driver.check_update(None))

                with FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    mock_clone.assert_called_once()
                    self.assertEqual(mock_clone.call_args[1].get("depth"), 1)
                    self.assertEqual(mock_clone.call_args[1].get("branch"), "v1.0")

    @patch("git.Repo.clone_from")
    def test_git_shallow_clone_no_version_success(self, mock_clone):
        mock_repo = MagicMock()
        mock_repo.head.commit.hexsha = "123456789abcdef"
        mock_clone.return_value = mock_repo

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "mygit_no_ver"
                dep.type = "git"
                dep.params = {"repo": "https://github.com/example/repo"}
                dep.version = None

                driver = GitDriver(ctx, dep)
                with FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    mock_clone.assert_called_once_with(
                        "https://github.com/example/repo",
                        os.path.join(tmpdir, ".sourceknight", "cache", "mygit_no_ver"),
                        depth=1,
                    )
                    self.assertEqual(dep.version, "123456789abcdef")
                    self.assertIn("mygit_no_ver", ctx.state.dependencies)

    @patch("git.Repo.clone_from")
    def test_git_shallow_clone_fallback_on_commit_sha(self, mock_clone):
        def _simulate_clone(*args, **kwargs):
            if mock_clone.call_count == 1:
                loc = args[1]
                os.makedirs(loc, exist_ok=True)
                with open(os.path.join(loc, "partial.tmp"), "w") as f:
                    f.write("partial")
                raise Exception("Shallow clone failed on commit SHA")
            mock_full_repo = MagicMock()
            mock_full_repo.head.commit.hexsha = "015d30c884674720914"
            return mock_full_repo

        mock_clone.side_effect = _simulate_clone

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "mygit_sha"
                dep.type = "git"
                dep.params = {"repo": "https://github.com/example/repo"}
                dep.version = "015d30c884674720914"

                driver = GitDriver(ctx, dep)
                with FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    self.assertEqual(mock_clone.call_count, 2)
                    self.assertIn("mygit_sha", ctx.state.dependencies)

    @patch("sourceknight.drivers.git.Repo")
    def test_git_pull_existing_repo(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.head.commit.hexsha = "abcdef1234567890"
        mock_repo_cls.return_value = mock_repo

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            repo_cache = os.path.join(tmpdir, ".sourceknight", "cache", "mygit_existing")
            os.makedirs(repo_cache)

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "mygit_existing"
                dep.type = "git"
                dep.params = {"repo": "https://github.com/example/repo"}
                dep.version = "master"

                driver = GitDriver(ctx, dep)
                with FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    mock_repo.remote().fetch.assert_called_once()
                    mock_repo.head.reset.assert_called_once_with("master", working_tree=True)

    @patch("sourceknight.drivers.git.Repo")
    def test_git_pull_existing_repo_no_version(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.head.commit.hexsha = "fedcba0987654321"
        mock_repo_cls.return_value = mock_repo

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            repo_cache = os.path.join(tmpdir, ".sourceknight", "cache", "mygit_pull_no_ver")
            os.makedirs(repo_cache)

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "mygit_pull_no_ver"
                dep.type = "git"
                dep.params = {"repo": "https://github.com/example/repo"}
                dep.version = None

                driver = GitDriver(ctx, dep)
                with FileManager(ctx, "cache") as fmgr:
                    driver.update(fmgr)
                    mock_repo.remote().pull.assert_called_once()
                    self.assertEqual(dep.version, "fedcba0987654321")

    def test_git_unpack_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            repo_cache = os.path.join(tmpdir, ".sourceknight", "cache", "mygit")
            os.makedirs(os.path.join(repo_cache, "addons", "sourcemod", "scripting", "include"))
            with open(os.path.join(repo_cache, "addons", "sourcemod", "scripting", "include", "mygit.inc"), "w") as f:
                f.write("// mygit")

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "mygit"
                dep.type = "git"
                dep.version = "v1.0"

                ctx.state.update(
                    dependencies={
                        "mygit": {
                            "name": "mygit",
                            "driver": "git",
                            "version": "v1.0",
                            "location": ".sourceknight/cache/mygit",
                        }
                    }
                )

                driver = GitDriver(ctx, dep)
                with FileManager(ctx, "build") as bmgr:
                    driver.unpack(bmgr, [])
                    dest_inc = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "include", "mygit.inc")
                    self.assertTrue(os.path.exists(dest_inc))

                driver.cleanup()


class TestReleaseDriverDeep(unittest.TestCase):
    def test_release_platform_patterns(self):
        mock_ctx = MagicMock()
        dep = Dependency()
        driver = ReleaseDriver(mock_ctx, dep)

        with patch("platform.system", return_value="Windows"):
            self.assertIn("*windows*.zip", driver._get_platform_pattern())

        with patch("platform.system", return_value="Linux"):
            self.assertIn("*linux*.tar.gz", driver._get_platform_pattern())

        with patch("platform.system", return_value="Darwin"):
            self.assertIn("*darwin*", driver._get_platform_pattern())

    def test_release_check_update_logic(self):
        mock_ctx = MagicMock()
        dep = Dependency()
        dep.version = "v1.0.0"
        driver = ReleaseDriver(mock_ctx, dep)

        # None current -> True
        self.assertTrue(driver.check_update(None))

        # Version is latest -> True
        dep_latest = Dependency()
        dep_latest.version = "latest"
        driver_latest = ReleaseDriver(mock_ctx, dep_latest)
        self.assertTrue(driver_latest.check_update(dep))

        # Different version -> True
        curr = Dependency()
        curr.version = "v0.9.0"
        self.assertTrue(driver.check_update(curr))

        # Same version -> False
        curr_same = Dependency()
        curr_same.version = "v1.0.0"
        self.assertFalse(driver.check_update(curr_same))

    @patch("requests.get")
    def test_github_release_tag_fallback_on_404(self, mock_get):
        mock_404 = MagicMock()
        mock_404.status_code = 404

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "tag_name": "1.2.0",
            "assets": [
                {
                    "name": "plugin-1.2.0-windows.zip",
                    "browser_download_url": "https://github.com/example/releases/download/1.2.0/plugin-windows.zip",
                }
            ],
        }

        mock_get.side_effect = [mock_404, mock_200]

        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "ext_lib"
        dep.type = "release"
        dep.params = {"repo": "example/repo", "asset_pattern": "*windows*.zip"}
        dep.version = "1.2.0"

        driver = ReleaseDriver(mock_ctx, dep)
        url, tag = driver._resolve_asset_url()
        self.assertEqual(url, "https://github.com/example/releases/download/1.2.0/plugin-windows.zip")
        self.assertEqual(tag, "1.2.0")

    @patch("requests.get")
    def test_github_release_empty_assets_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"tag_name": "1.0", "assets": []}
        mock_get.return_value = mock_resp

        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "no_assets"
        dep.type = "release"
        dep.params = {"repo": "example/empty"}
        dep.version = "1.0"

        driver = ReleaseDriver(mock_ctx, dep)
        with self.assertRaises(SkError) as cm:
            driver._resolve_asset_url()
        self.assertIn("No release assets found", str(cm.exception))

    @patch("requests.get")
    def test_gitlab_release_resolution(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v3.0.0",
            "assets": {
                "links": [
                    {
                        "name": "gitlab-lib-linux.tar.gz",
                        "url": "https://gitlab.com/group/project/releases/gitlab-lib-linux.tar.gz",
                    }
                ]
            },
        }
        mock_get.return_value = mock_resp

        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "gitlab_lib"
        dep.type = "release"
        dep.params = {
            "repo": "https://gitlab.com/group/project",
            "asset_pattern": "*linux*.tar.gz",
        }
        dep.version = "v3.0.0"

        driver = ReleaseDriver(mock_ctx, dep)
        url, tag = driver._resolve_asset_url()
        self.assertEqual(url, "https://gitlab.com/group/project/releases/gitlab-lib-linux.tar.gz")
        self.assertEqual(tag, "v3.0.0")

    def test_direct_archive_url_resolution(self):
        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "direct_lib"
        dep.type = "release"
        dep.params = {"repo": "https://example.com/downloads/v1.0.0.zip"}
        dep.version = "v1.0.0"

        driver = ReleaseDriver(mock_ctx, dep)
        url, tag = driver._resolve_asset_url()
        self.assertEqual(url, "https://example.com/downloads/v1.0.0.zip")
        self.assertEqual(tag, "v1.0.0")

    def test_release_driver_unpack_zip_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            cache_dir = os.path.join(tmpdir, ".sourceknight", "cache")
            os.makedirs(cache_dir, exist_ok=True)
            zip_filename = "release_mock.zip"
            zip_path = os.path.join(cache_dir, zip_filename)

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("addons/sourcemod/scripting/include/rel_zip.inc", "// release zip header")

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "release_zip_dep"
                dep.type = "release"
                dep.version = "1.0.0"

                ctx.state.update(
                    dependencies={
                        "release_zip_dep": {
                            "name": "release_zip_dep",
                            "driver": "release",
                            "file": zip_filename,
                            "resolved_version": "1.0.0",
                        }
                    }
                )

                driver = ReleaseDriver(ctx, dep)
                with FileManager(ctx, "build") as bmgr:
                    driver.unpack(bmgr, [])
                    dest_inc = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "include", "rel_zip.inc")
                    self.assertTrue(os.path.exists(dest_inc))

                driver.cleanup()

    def test_release_driver_unpack_tar_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            cache_dir = os.path.join(tmpdir, ".sourceknight", "cache")
            os.makedirs(cache_dir, exist_ok=True)
            tar_filename = "release_mock.tar.gz"
            tar_path = os.path.join(cache_dir, tar_filename)

            with tarfile.open(tar_path, "w:gz") as tf:
                content = b"// release tar header"
                ti = tarfile.TarInfo("addons/sourcemod/scripting/include/rel_tar.inc")
                ti.size = len(content)
                tf.addfile(ti, io.BytesIO(content))

            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "release_tar_dep"
                dep.type = "release"
                dep.version = "1.0.0"

                ctx.state.update(
                    dependencies={
                        "release_tar_dep": {
                            "name": "release_tar_dep",
                            "driver": "release",
                            "file": tar_filename,
                            "resolved_version": "1.0.0",
                        }
                    }
                )

                driver = ReleaseDriver(ctx, dep)
                with FileManager(ctx, "build") as bmgr:
                    driver.unpack(bmgr, [])
                    dest_inc = os.path.join(bmgr.path, "addons", "sourcemod", "scripting", "include", "rel_tar.inc")
                    self.assertTrue(os.path.exists(dest_inc))

                driver.cleanup()

    def test_release_driver_update(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                dep = Dependency()
                dep.name = "release_update_dep"
                dep.type = "release"
                dep.params = {"repo": "https://example.com/downloads/rel_archive.zip"}
                dep.version = "1.0.0"

                driver = ReleaseDriver(ctx, dep)
                with FileManager(ctx, "cache") as fmgr, patch.object(fmgr, "acquire", return_value=os.path.join(fmgr.path, "rel_archive.zip")):
                    driver.update(fmgr)
                    self.assertIn("release_update_dep", ctx.state.dependencies)
                    self.assertEqual(
                        ctx.state.dependencies["release_update_dep"]["resolved_version"],
                        "1.0.0",
                    )


if __name__ == "__main__":
    unittest.main()
