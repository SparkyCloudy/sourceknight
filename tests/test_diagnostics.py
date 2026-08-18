import os
import unittest
from unittest.mock import patch

from sourceknight.diagnostics import (
    format_compiler_output,
    is_color_enabled,
    is_github_actions,
    parse_diagnostics,
)


class TestDiagnostics(unittest.TestCase):
    def test_parse_empty_and_no_match(self):
        self.assertEqual(parse_diagnostics(""), [])
        self.assertEqual(parse_diagnostics("Header text without error format"), [])

    def test_parse_multi_line_diagnostics(self):
        sample = """
addons/sourcemod/scripting/my_plugin.sp(42) : error 017: undefined symbol "g_hTimer"
addons/sourcemod/scripting/my_plugin.sp(99) : warning 213: tag mismatch
addons/sourcemod/scripting/fatal_test.sp(1) : fatal error 100: cannot read from file: "test.inc"
"""
        diags = parse_diagnostics(sample)
        self.assertEqual(len(diags), 3)

        self.assertEqual(diags[0]["file"], "addons/sourcemod/scripting/my_plugin.sp")
        self.assertEqual(diags[0]["line"], 42)
        self.assertEqual(diags[0]["kind"], "error")
        self.assertEqual(diags[0]["code"], "017")
        self.assertEqual(diags[0]["message"], 'undefined symbol "g_hTimer"')

        self.assertEqual(diags[1]["line"], 99)
        self.assertEqual(diags[1]["kind"], "warning")

        self.assertEqual(diags[2]["kind"], "fatal error")

    def test_format_compiler_output_with_color_and_annotations(self):
        sample = 'plugin.sp(10) : error 001: expected token: ";", but found "}"'
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            formatted = format_compiler_output(sample, color=True, emit_github_annotations=True)
            self.assertIn("::error file=plugin.sp,line=10,title=Error 001::expected token:", formatted)
            self.assertIn("\033[1;31m", formatted)

    def test_format_compiler_output_no_color(self):
        sample = 'plugin.sp(10) : error 001: expected token: ";", but found "}"'
        formatted = format_compiler_output(sample, color=False, emit_github_annotations=False)
        self.assertEqual(formatted, sample)

    def test_is_color_enabled(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertFalse(is_color_enabled(cli_no_color=False))

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_color_enabled(cli_no_color=True))

        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            self.assertTrue(is_color_enabled(cli_no_color=False))

    def test_is_github_actions(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            self.assertTrue(is_github_actions())
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_github_actions())


if __name__ == "__main__":
    unittest.main()
