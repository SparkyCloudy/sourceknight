import argparse
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sourceknight.context import Context
from sourceknight.dependencies import Dependency, drivers_by_name
from sourceknight.drivers.smdrop import SmdropDriver
from sourceknight.utils import resolve_heuristic_locations


class TestHeuristicUnpack(unittest.TestCase):
    def test_addons_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "addons", "sourcemod"))
            locations = resolve_heuristic_locations(tmpdir)
            self.assertEqual(locations, [{'source': '/addons', 'dest': '/addons'}])

    def test_subdirectories_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "scripting"))
            os.makedirs(os.path.join(tmpdir, "include"))
            os.makedirs(os.path.join(tmpdir, "plugins"))
            locations = resolve_heuristic_locations(tmpdir)
            expected = [
                {'source': '/scripting', 'dest': '/addons/sourcemod/scripting'},
                {'source': '/include', 'dest': '/addons/sourcemod/scripting/include'},
                {'source': '/plugins', 'dest': '/addons/sourcemod/plugins'},
            ]
            self.assertEqual(locations, expected)

    def test_loose_inc_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "my_include.inc"), "w") as f:
                f.write("// include header")
            locations = resolve_heuristic_locations(tmpdir)
            self.assertEqual(locations, [{'source': '/my_include.inc', 'dest': '/addons/sourcemod/scripting/include/my_include.inc'}])


class TestSmdropDriver(unittest.TestCase):
    def test_smdrop_registration(self):
        self.assertIn('smdrop', drivers_by_name)
        self.assertEqual(drivers_by_name['smdrop'], SmdropDriver)

    @patch('requests.get')
    def test_url_resolution(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "sourcemod-1.12.0-git7249-linux.tar.gz\n"
        mock_get.return_value = mock_resp

        mock_ctx = MagicMock()
        mock_ctx.path = "/tmp/fake_project"

        dep = Dependency()
        dep.name = "sourcemod"
        dep.type = "smdrop"
        dep.version = "1.12.x"

        driver = SmdropDriver(mock_ctx, dep)
        # Mock platform to linux
        with patch.object(driver, '_get_platform_info', return_value=('linux', '.tar.gz')):
            resolved = driver._resolve_url()
            self.assertEqual(resolved, "https://sm.alliedmods.net/smdrop/1.12/sourcemod-1.12.0-git7249-linux.tar.gz")


class TestOverrides(unittest.TestCase):
    def test_cli_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-proj
  dependencies:
    - name: sourcemod
      type: smdrop
      version: 1.10.x
    - name: colors
      type: git
      version: master
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            args = argparse.Namespace(
                override_dep=["sourcemod=1.12.x", "colors=v1.2"]
            )

            with Context(tmpdir, args=args) as ctx:
                deps = {d['name']: d['version'] for d in ctx.defs['dependencies']}
                self.assertEqual(deps['sourcemod'], "1.12.x")
                self.assertEqual(deps['colors'], "v1.2")

    def test_env_var_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-proj
  dependencies:
    - name: sourcemod
      type: smdrop
      version: 1.10.x
    - name: extend-map
      type: git
      version: master
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            os.environ["SK_OVERRIDE_SOURCEMOD"] = "1.11.x"
            os.environ["SK_OVERRIDE_EXTEND_MAP"] = "dev-branch"

            try:
                with Context(tmpdir) as ctx:
                    deps = {d['name']: d['version'] for d in ctx.defs['dependencies']}
                    self.assertEqual(deps['sourcemod'], "1.11.x")
                    self.assertEqual(deps['extend-map'], "dev-branch")
            finally:
                del os.environ["SK_OVERRIDE_SOURCEMOD"]
                del os.environ["SK_OVERRIDE_EXTEND_MAP"]


if __name__ == "__main__":
    unittest.main()
