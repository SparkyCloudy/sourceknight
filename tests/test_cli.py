import logging
import os
import tempfile
import unittest
from unittest.mock import patch

from sourceknight.errors import SkError
from sourceknight.main import main


def _make_dummy_manifest(tmpdir: str) -> None:
    yaml_content = """project:
  sourceknight: 0.5
  name: test-proj
  targets:
    - dummy_target
"""
    with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
        f.write(yaml_content)


class TestCLI(unittest.TestCase):
    def test_cli_help(self):
        with self.assertRaises(SystemExit) as cm:
            main(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_cli_invalid_command(self):
        with self.assertRaises(SystemExit) as cm:
            main(["non_existent_command"])
        self.assertEqual(cm.exception.code, 2)

    @patch("sourceknight.commands.status.Status.__call__")
    def test_cli_status_dispatch(self, mock_status_call):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with self.assertRaises(SystemExit) as cm:
                main(["-p", tmpdir, "status", "-v"])
            self.assertEqual(cm.exception.code, 0)
            mock_status_call.assert_called_once()

    @patch("sourceknight.commands.build.Build.__call__")
    def test_cli_build_dispatch(self, mock_build_call):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with self.assertRaises(SystemExit) as cm:
                main(["-v", "-p", tmpdir, "build", "--clean", "--force", "-j", "4"])
            self.assertEqual(cm.exception.code, 0)
            mock_build_call.assert_called_once()
            self.assertEqual(logging.getLogger().level, logging.DEBUG)

    @patch("sourceknight.commands.update.Update.__call__")
    def test_cli_update_dispatch(self, mock_update_call):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with self.assertRaises(SystemExit) as cm:
                main(["-p", tmpdir, "update", "--force"])
            self.assertEqual(cm.exception.code, 0)
            mock_update_call.assert_called_once()

    @patch("sourceknight.commands.unpack.Unpack.__call__")
    def test_cli_unpack_dispatch(self, mock_unpack_call):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with self.assertRaises(SystemExit) as cm:
                main(["-p", tmpdir, "unpack", "--clean", "--all"])
            self.assertEqual(cm.exception.code, 0)
            mock_unpack_call.assert_called_once()

    @patch("sourceknight.commands.compile.Compile.__call__")
    def test_cli_compile_dispatch(self, mock_compile_call):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with self.assertRaises(SystemExit) as cm:
                main(["-p", tmpdir, "compile", "--parallel", "2", "--fail-fast", "--no-color"])
            self.assertEqual(cm.exception.code, 0)
            mock_compile_call.assert_called_once()

    @patch("sourceknight.commands.build.Build.__call__")
    def test_cli_sk_error_handling(self, mock_build_call):
        mock_build_call.side_effect = SkError("Intentional test error")
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with self.assertRaises(SystemExit) as cm:
                main(["-p", tmpdir, "build"])
            self.assertEqual(cm.exception.code, 1)

    @patch("sourceknight.commands.build.Build.__call__")
    def test_cli_general_exception_handling(self, mock_build_call):
        mock_build_call.side_effect = RuntimeError("Unexpected internal crash")
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_dummy_manifest(tmpdir)
            with self.assertRaises(SystemExit) as cm:
                main(["-p", tmpdir, "build"])
            self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
