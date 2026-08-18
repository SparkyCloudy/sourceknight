import argparse
import json
import os
import platform
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sourceknight.commands.actions import do_unpack, do_update
from sourceknight.commands.build import Build
from sourceknight.commands.compile import Compile
from sourceknight.commands.status import Status
from sourceknight.commands.unpack import Unpack
from sourceknight.commands.update import Update
from sourceknight.context import Context
from sourceknight.errors import SkError


def _make_dummy_manifest(tmpdir: str, content: str | None = None) -> None:
    if content is None:
        content = """project:
  sourceknight: 0.5
  name: test-proj
  dependencies:
    - name: dep_a
      type: git
      version: v1.0
    - name: dep_b
      type: git
      version: v2.0
  targets:
    - plugin_a
    - plugin_b
"""
    with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
        f.write(content)


class TestActions(unittest.TestCase):
    @patch("sourceknight.dependencies.DependencyManager.update")
    def test_do_update_multi_threaded_and_empty(self, mock_dmgr_update):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                do_update(ctx, force=True)
                self.assertEqual(mock_dmgr_update.call_count, 2)

        # Empty dependencies branch
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir, "project:\n  sourceknight: 0.5\n  name: empty\n")
            with Context(tmpdir) as ctx:
                do_update(ctx, force=False)

    @patch("sourceknight.dependencies.DependencyManager.unpack")
    def test_do_unpack_lifecycle(self, mock_dmgr_unpack):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                ctx.state.update(
                    dependencies={
                        "dep_a": {"name": "dep_a", "version": "v1.0", "driver": "git"},
                        "dep_b": {"name": "dep_b", "version": "v2.0", "driver": "git"},
                    }
                )
                do_unpack(ctx, force=True, clean=True)
                self.assertEqual(mock_dmgr_unpack.call_count, 2)


class TestCommands(unittest.TestCase):
    @patch("sourceknight.commands.build.do_update")
    @patch("sourceknight.commands.build.do_unpack")
    @patch("sourceknight.commands.build.Compile.__call__")
    def test_build_command(self, mock_compile, mock_unpack, mock_update):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                cmd = Build(ctx)
                args = argparse.Namespace(force=True, clean=True)
                cmd(args)
                mock_update.assert_called_once_with(ctx, True)
                mock_unpack.assert_called_once_with(ctx, True, True)
                mock_compile.assert_called_once_with(args)

    @patch("sourceknight.commands.update.do_update")
    def test_update_command(self, mock_update):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                cmd = Update(ctx)
                args = argparse.Namespace(force=True)
                cmd(args)
                mock_update.assert_called_once_with(ctx, True)

    @patch("sourceknight.commands.unpack.do_unpack")
    def test_unpack_command(self, mock_unpack):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with Context(tmpdir) as ctx:
                cmd = Unpack(ctx)
                args = argparse.Namespace(force=False, clean=True)
                cmd(args)
                mock_unpack.assert_called_once_with(ctx, False, True)

    def test_status_command_rendering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-status
  dependencies:
    - name: dep_ok
      type: git
      version: v1.0
    - name: dep_diff
      type: git
      version: v2.0
    - name: dep_missing
      type: git
      version: v1.0
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            with Context(tmpdir) as ctx:
                ctx.state.dependencies["dep_ok"] = {"name": "dep_ok", "version": "v1.0"}
                ctx.state.build["dep_ok"] = {"name": "dep_ok", "version": "v1.0"}

                ctx.state.dependencies["dep_diff"] = {"name": "dep_diff", "version": "v2.0"}
                ctx.state.build["dep_diff"] = {"name": "dep_diff", "version": "v1.5"}

                cmd = Status(ctx)
                args = argparse.Namespace(verbose=False)
                cmd(args)
                args.verbose = True
                cmd(args)


class TestCompileCommandDeep(unittest.TestCase):
    def test_compile_undefined_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-compile
  targets:
    - target_a
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            with Context(tmpdir) as ctx:
                cmd = Compile(ctx)
                args = argparse.Namespace(
                    targets=["target_invalid"],
                    output=None,
                    jobs=1,
                    no_color=True,
                    fail_fast=False,
                    report=None,
                )
                with self.assertRaises(SkError) as cm:
                    cmd(args)
                self.assertIn("target_invalid", str(cm.exception))

    def test_compile_missing_compiler(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-compile
  targets:
    - target_a
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            with Context(tmpdir) as ctx:
                cmd = Compile(ctx)
                args = argparse.Namespace(
                    targets=[],
                    output=None,
                    jobs=1,
                    no_color=True,
                    fail_fast=False,
                    report=None,
                )
                with self.assertRaises(SkError) as cm:
                    cmd(args)
                self.assertIn("Compiler executable not found", str(cm.exception))

    @patch("subprocess.run")
    def test_compile_parallel_multi_target_and_fail_fast(self, mock_run):
        mock_proc_ok = MagicMock()
        mock_proc_ok.returncode = 0
        mock_proc_ok.stdout = "Compiled target OK"
        mock_proc_ok.stderr = ""

        mock_proc_err = MagicMock()
        mock_proc_err.returncode = 1
        mock_proc_err.stdout = "Error compiling plugin"
        mock_proc_err.stderr = "plugin_b.sp(10): error 001"

        # plugin_a succeeds, plugin_b fails
        mock_run.side_effect = [mock_proc_ok, mock_proc_err]

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-compile
  targets:
    - plugin_a
    - plugin_b
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            build_spcomp = os.path.join(tmpdir, ".sourceknight", "build", "addons", "sourcemod", "scripting")
            os.makedirs(build_spcomp, exist_ok=True)
            ext = ".exe" if platform.system() == "Windows" else ""
            with open(os.path.join(build_spcomp, f"spcomp{ext}"), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")

            with Context(tmpdir) as ctx:
                cmd = Compile(ctx)
                args = argparse.Namespace(
                    targets=[],
                    output=None,
                    jobs=2,
                    no_color=True,
                    fail_fast=True,
                    report="json",
                )
                with self.assertRaises(SkError) as cm:
                    cmd(args)
                self.assertIn("Compilation failed for 1 target(s)", str(cm.exception))

    @patch("subprocess.run")
    def test_compile_with_explicit_sp_extension_and_spcomp64(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Compiled 64-bit target OK"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-compile
  targets:
    - plugin_x.sp
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            build_spcomp = os.path.join(tmpdir, ".sourceknight", "build", "addons", "sourcemod", "scripting")
            os.makedirs(build_spcomp, exist_ok=True)
            # Create 64-bit compiler binary
            with open(os.path.join(build_spcomp, "spcomp64"), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")

            with Context(tmpdir) as ctx:
                cmd = Compile(ctx)
                args = argparse.Namespace(
                    targets=["plugin_x.sp"],
                    output=None,
                    jobs=1,
                    no_color=True,
                    fail_fast=False,
                    report=None,
                )
                with patch("platform.system", return_value="Linux"):
                    cmd(args)
                    self.assertEqual(mock_run.call_count, 1)

    @patch("subprocess.run")
    def test_compile_with_root_copy_and_json_report(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Compiling target_a successful"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-compile
  root: /plugins
  targets:
    - target_a
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            plugins_dir = os.path.join(tmpdir, "plugins")
            os.makedirs(plugins_dir, exist_ok=True)
            with open(os.path.join(plugins_dir, "target_a.sp"), "w") as f:
                f.write("// plugin source")
            with open(os.path.join(plugins_dir, ".hidden_file"), "w") as f:
                f.write("// hidden file")

            build_spcomp = os.path.join(tmpdir, ".sourceknight", "build", "addons", "sourcemod", "scripting")
            os.makedirs(build_spcomp, exist_ok=True)
            ext = ".exe" if platform.system() == "Windows" else ""
            with open(os.path.join(build_spcomp, f"spcomp{ext}"), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")

            out_dir = os.path.join(tmpdir, "custom_out")
            args = argparse.Namespace(
                targets=["target_a"],
                output=out_dir,
                jobs=1,
                no_color=True,
                fail_fast=False,
                report="json",
            )

            with Context(tmpdir) as ctx:
                cmd = Compile(ctx)
                cmd(args)

                report_file = os.path.join(tmpdir, "compile_report.json")
                self.assertTrue(os.path.exists(report_file))
                with open(report_file, encoding="utf-8") as f:
                    data = json.load(f)
                self.assertEqual(data["summary"]["success"], 1)
                self.assertEqual(data["summary"]["failed"], 0)
                self.assertEqual(len(data["targets"]), 1)


if __name__ == "__main__":
    unittest.main()
