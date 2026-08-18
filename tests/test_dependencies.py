import os
import tempfile
import unittest
from unittest.mock import patch

from sourceknight.context import Context
from sourceknight.dependencies import Dependency, DependencyManager
from sourceknight.errors import SkError
from sourceknight.utils import FileManager


def _make_dummy_manifest(tmpdir: str) -> None:
    yaml_content = """project:
  sourceknight: 0.5
  name: test-proj
"""
    with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
        f.write(yaml_content)


class TestDependencies(unittest.TestCase):
    def test_dependency_model(self):
        data = {
            "name": "ptah",
            "type": "release",
            "version": "v1.2.0",
            "repo": "komashchenko/PTaH",
        }
        dep = Dependency.from_yaml(data)
        self.assertEqual(dep.name, "ptah")
        self.assertEqual(dep.type, "release")
        self.assertEqual(dep.version, "v1.2.0")
        self.assertEqual(dep.params["repo"], "komashchenko/PTaH")

        state = dep.state(driver="release", file="ptah.zip")
        self.assertEqual(state["name"], "ptah")
        self.assertEqual(state["version"], "v1.2.0")
        self.assertEqual(state["driver"], "release")
        self.assertEqual(state["file"], "ptah.zip")

    @patch("sourceknight.drivers.git.GitDriver.update")
    @patch("sourceknight.drivers.git.GitDriver.check_update", return_value=True)
    def test_dependency_manager_update_flow(self, mock_check, mock_update):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-dep
  dependencies:
    - name: colors
      type: git
      repo: https://github.com/example/colors
      version: master
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            with Context(tmpdir) as ctx:
                dmgr = DependencyManager(ctx)
                with FileManager(ctx, "cache") as fmgr:
                    dmgr.update(ctx.defs["dependencies"][0], fmgr, force=False)
                    mock_update.assert_called_once()

    @patch("sourceknight.drivers.git.GitDriver.check_update", return_value=False)
    @patch("sourceknight.drivers.git.GitDriver.update")
    def test_dependency_manager_skip_up_to_date(self, mock_update, mock_check):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-dep
  dependencies:
    - name: colors
      type: git
      repo: https://github.com/example/colors
      version: master
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            with Context(tmpdir) as ctx:
                ctx.state.dependencies["colors"] = {"name": "colors", "version": "master"}
                dmgr = DependencyManager(ctx)
                with FileManager(ctx, "cache") as fmgr:
                    dmgr.update(ctx.defs["dependencies"][0], fmgr, force=False)
                    mock_update.assert_not_called()

    def test_dependency_manager_unsupported_driver(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                dmgr = DependencyManager(ctx)
                with FileManager(ctx, "cache") as fmgr:
                    invalid_dep = {"name": "bad", "type": "invalid_driver_type"}
                    with self.assertRaises(SkError) as cm:
                        dmgr.update(invalid_dep, fmgr)
                    self.assertIn("Unsupported dependency type", str(cm.exception))

    @patch("sourceknight.drivers.git.GitDriver.unpack")
    def test_dependency_manager_unpack_flow(self, mock_unpack):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                ctx.state.dependencies["colors"] = {
                    "name": "colors",
                    "driver": "git",
                    "version": "v2.0",
                }
                dmgr = DependencyManager(ctx)
                with FileManager(ctx, "build") as fmgr:
                    dmgr.unpack(
                        ctx.state.dependencies["colors"],
                        [],
                        fmgr,
                        force=False,
                    )
                    mock_unpack.assert_called_once()

    @patch("sourceknight.drivers.git.GitDriver.unpack")
    def test_dependency_manager_unpack_skip_when_synced(self, mock_unpack):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                ctx.state.dependencies["colors"] = {
                    "name": "colors",
                    "driver": "git",
                    "version": "v1.0",
                }
                ctx.state.build["colors"] = {
                    "name": "colors",
                    "version": "v1.0",
                }
                dmgr = DependencyManager(ctx)
                with FileManager(ctx, "build") as fmgr:
                    dmgr.unpack(
                        ctx.state.dependencies["colors"],
                        [],
                        fmgr,
                        force=False,
                    )
                    mock_unpack.assert_not_called()

    def test_dependency_manager_unpack_unknown_driver(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                ctx.state.dependencies["colors"] = {
                    "name": "colors",
                    "driver": "non_existent_driver_xyz",
                    "version": "v1.0",
                }
                dmgr = DependencyManager(ctx)
                with FileManager(ctx, "build") as fmgr:
                    with self.assertRaises(SkError) as cm:
                        dmgr.unpack(
                            ctx.state.dependencies["colors"],
                            [],
                            fmgr,
                            force=False,
                        )
                    self.assertIn("Unknown driver", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
