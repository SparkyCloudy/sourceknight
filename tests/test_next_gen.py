import argparse
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sourceknight.commands.actions import do_update
from sourceknight.commands.compile import Compile, _compile_single_target
from sourceknight.context import Context
from sourceknight.dependencies import Dependency, drivers_by_name
from sourceknight.diagnostics import (
    format_compiler_output,
    is_color_enabled,
    parse_diagnostics,
)
from sourceknight.drivers.release import ReleaseDriver
from sourceknight.drivers.smdrop import SmdropDriver
from sourceknight.errors import SkError
from sourceknight.utils import resolve_heuristic_locations


class TestHeuristicUnpack(unittest.TestCase):
    def test_addons_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "addons", "sourcemod"))
            locations = resolve_heuristic_locations(tmpdir)
            self.assertEqual(locations, [{"source": "/addons", "dest": "/addons"}])

    def test_nested_game_addons_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "game", "addons", "sourcemod"))
            locations = resolve_heuristic_locations(tmpdir)
            self.assertEqual(locations, [{"source": "/game/addons", "dest": "/addons"}])

    def test_subdirectories_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "scripting"))
            os.makedirs(os.path.join(tmpdir, "include"))
            os.makedirs(os.path.join(tmpdir, "plugins"))
            locations = resolve_heuristic_locations(tmpdir)
            expected = [
                {"source": "/scripting", "dest": "/addons/sourcemod/scripting"},
                {"source": "/include", "dest": "/addons/sourcemod/scripting/include"},
                {"source": "/plugins", "dest": "/addons/sourcemod/plugins"},
            ]
            self.assertEqual(locations, expected)

    def test_loose_inc_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "my_include.inc"), "w") as f:
                f.write("// include header")
            locations = resolve_heuristic_locations(tmpdir)
            self.assertEqual(
                locations,
                [
                    {
                        "source": "/my_include.inc",
                        "dest": "/addons/sourcemod/scripting/include/my_include.inc",
                    }
                ],
            )


class TestSmdropDriver(unittest.TestCase):
    def test_smdrop_registration(self):
        self.assertIn("smdrop", drivers_by_name)
        self.assertEqual(drivers_by_name["smdrop"], SmdropDriver)

    @patch("requests.get")
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
        with patch.object(driver, "_get_platform_info", return_value=("linux", ".tar.gz")):
            resolved = driver._resolve_url()
            self.assertEqual(
                resolved,
                "https://sm.alliedmods.net/smdrop/1.12/sourcemod-1.12.0-git7249-linux.tar.gz",
            )


class TestReleaseDriver(unittest.TestCase):
    def test_release_driver_registration(self):
        self.assertIn("release", drivers_by_name)
        self.assertEqual(drivers_by_name["release"], ReleaseDriver)

    @patch("requests.get")
    def test_github_release_resolution(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v1.2.0",
            "assets": [
                {
                    "name": "ptah-v1.2.0-linux.zip",
                    "browser_download_url": "https://github.com/komashchenko/PTaH/releases/download/v1.2.0/ptah-v1.2.0-linux.zip",
                },
                {
                    "name": "ptah-v1.2.0-windows.zip",
                    "browser_download_url": "https://github.com/komashchenko/PTaH/releases/download/v1.2.0/ptah-v1.2.0-windows.zip",
                },
            ],
        }
        mock_get.return_value = mock_resp

        mock_ctx = MagicMock()
        dep = Dependency()
        dep.name = "ptah"
        dep.type = "release"
        dep.params = {"repo": "komashchenko/PTaH", "asset_pattern": "*linux*.zip"}
        dep.version = "v1.2.0"

        driver = ReleaseDriver(mock_ctx, dep)
        url, tag = driver._resolve_asset_url()
        self.assertEqual(
            url,
            "https://github.com/komashchenko/PTaH/releases/download/v1.2.0/ptah-v1.2.0-linux.zip",
        )
        self.assertEqual(tag, "v1.2.0")


class TestDiagnostics(unittest.TestCase):
    def test_parse_diagnostics(self):
        raw = """mapchooser.sp(145) : error 017: undefined symbol "g_hTimer"
nominations.sp(20) : warning 213: tag mismatch
fatal.sp(1) : fatal error 100: cannot read from file: "missing.inc"
"""
        items = parse_diagnostics(raw)
        self.assertEqual(len(items), 3)

        self.assertEqual(items[0]["file"], "mapchooser.sp")
        self.assertEqual(items[0]["line"], 145)
        self.assertEqual(items[0]["kind"], "error")
        self.assertEqual(items[0]["code"], "017")
        self.assertEqual(items[0]["message"], 'undefined symbol "g_hTimer"')

        self.assertEqual(items[1]["file"], "nominations.sp")
        self.assertEqual(items[1]["line"], 20)
        self.assertEqual(items[1]["kind"], "warning")

        self.assertEqual(items[2]["kind"], "fatal error")

    def test_color_formatting(self):
        raw = 'mapchooser.sp(145) : error 017: undefined symbol "g_hTimer"'
        formatted = format_compiler_output(raw, color=True, emit_github_annotations=False)
        self.assertIn("\033[1;31m", formatted)
        self.assertIn("mapchooser.sp", formatted)

    def test_github_annotations(self):
        raw = 'mapchooser.sp(145) : error 017: undefined symbol "g_hTimer"'
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            formatted = format_compiler_output(raw, color=False, emit_github_annotations=True)
            self.assertIn(
                '::error file=mapchooser.sp,line=145,title=Error 017::undefined symbol "g_hTimer"',
                formatted,
            )

    def test_no_color_env(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertFalse(is_color_enabled(cli_no_color=False))


class TestParallelCompilation(unittest.TestCase):
    @patch("subprocess.run")
    def test_compile_single_target(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Compilation succeeded."
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        res = _compile_single_target("spcomp", "target1", "/tmp/out")
        self.assertTrue(res["success"])
        self.assertEqual(res["target"], "target1")
        self.assertEqual(res["stdout"], "Compilation succeeded.")

    @patch("sourceknight.commands.compile._compile_single_target")
    def test_compile_parallel_execution(self, mock_worker):
        mock_worker.side_effect = lambda comp, t, out: {
            "target": t,
            "success": True,
            "returncode": 0,
            "stdout": f"Compiled {t}",
            "stderr": "",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-parallel
  targets:
    - plugin_a
    - plugin_b
    - plugin_c
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            build_spcomp = os.path.join(tmpdir, ".sourceknight", "build", "addons", "sourcemod", "scripting")
            os.makedirs(build_spcomp, exist_ok=True)
            with open(os.path.join(build_spcomp, "spcomp"), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")

            args = argparse.Namespace(
                targets=[],
                output=None,
                jobs=3,
                no_color=True,
                fail_fast=False,
                report=None,
            )

            with Context(tmpdir) as ctx:
                cmd = Compile(ctx)
                cmd(args)
                self.assertEqual(mock_worker.call_count, 3)

    @patch("sourceknight.commands.compile._compile_single_target")
    def test_compile_fail_fast(self, mock_worker):
        def _mock_res(comp, t, out):
            return {
                "target": t,
                "success": False,
                "returncode": 1,
                "stdout": f"Failed {t}",
                "stderr": "",
            }

        mock_worker.side_effect = _mock_res

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-fail-fast
  targets:
    - plugin_a
    - plugin_b
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            build_spcomp = os.path.join(tmpdir, ".sourceknight", "build", "addons", "sourcemod", "scripting")
            os.makedirs(build_spcomp, exist_ok=True)
            with open(os.path.join(build_spcomp, "spcomp"), "w") as f:
                f.write("#!/bin/sh\nexit 1\n")

            args = argparse.Namespace(
                targets=[],
                output=None,
                jobs=1,
                no_color=True,
                fail_fast=True,
                report=None,
            )

            with Context(tmpdir) as ctx:
                cmd = Compile(ctx)
                with self.assertRaises(SkError):
                    cmd(args)


class TestConcurrentUpdate(unittest.TestCase):
    @patch("sourceknight.dependencies.DependencyManager.update")
    def test_concurrent_do_update(self, mock_update):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-concurrent-update
  dependencies:
    - name: dep1
      type: git
      repo: https://github.com/example/dep1
    - name: dep2
      type: git
      repo: https://github.com/example/dep2
    - name: dep3
      type: git
      repo: https://github.com/example/dep3
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            with Context(tmpdir) as ctx:
                do_update(ctx, force=False)
                self.assertEqual(mock_update.call_count, 3)


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
                deps = {d["name"]: d["version"] for d in ctx.defs["dependencies"]}
                self.assertEqual(deps["sourcemod"], "1.12.x")
                self.assertEqual(deps["colors"], "v1.2")

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
                    deps = {d["name"]: d["version"] for d in ctx.defs["dependencies"]}
                    self.assertEqual(deps["sourcemod"], "1.11.x")
                    self.assertEqual(deps["extend-map"], "dev-branch")
            finally:
                del os.environ["SK_OVERRIDE_SOURCEMOD"]
                del os.environ["SK_OVERRIDE_EXTEND_MAP"]


if __name__ == "__main__":
    unittest.main()
