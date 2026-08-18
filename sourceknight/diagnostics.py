import os
import re
import sys
from typing import Any

# Pre-compiled regex for spcomp diagnostic lines:
# Format: <file>(<line>) : (error|warning|fatal error) <code>: <message>
DIAGNOSTIC_PATTERN = re.compile(
    r"^([^\r\n]+?)\((\d+)\)\s*:\s*(error|warning|fatal error)\s+(\d+)\s*:\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

# ANSI escape codes
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_CYAN = "\033[36m"
ANSI_GREEN = "\033[1;32m"
ANSI_GRAY = "\033[90m"


def is_color_enabled(cli_no_color: bool = False) -> bool:
    """
    Determines if ANSI color rendering should be enabled.
    Disabled if:
    - cli_no_color is True
    - NO_COLOR environment variable is set
    - stdout is not a TTY and CI environment variable is not active
    """
    if cli_no_color or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true":
        return True
    return sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False


def is_github_actions() -> bool:
    """Checks if running inside a GitHub Actions environment."""
    return os.environ.get("GITHUB_ACTIONS") == "true"


def parse_diagnostics(text: str) -> list[dict[str, Any]]:
    """
    Parses compiler diagnostic output into structured items.
    """
    diagnostics: list[dict[str, Any]] = []
    if not text:
        return diagnostics

    for match in DIAGNOSTIC_PATTERN.finditer(text):
        filename, line_str, kind, code, message = match.groups()
        diagnostics.append(
            {
                "file": filename.strip(),
                "line": int(line_str),
                "kind": kind.lower().strip(),
                "code": code.strip(),
                "message": message.strip(),
                "raw": match.group(0),
            }
        )
    return diagnostics


def format_compiler_output(
    raw_output: str,
    color: bool = True,
    emit_github_annotations: bool = True,
) -> str:
    """
    Formats compiler output with ANSI colors and optional GitHub Actions workflow annotations.
    """
    if not raw_output:
        return ""

    diagnostics = parse_diagnostics(raw_output)
    formatted_lines: list[str] = []

    # If running in GitHub Actions and annotations requested, prepend workflow commands
    if emit_github_annotations and is_github_actions():
        for diag in diagnostics:
            level = "error" if "error" in diag["kind"] else "warning"
            title = f"{diag['kind'].title()} {diag['code']}"
            formatted_lines.append(
                f"::{level} file={diag['file']},line={diag['line']},title={title}::{diag['message']}"
            )

    if not color:
        if formatted_lines:
            return "\n".join(formatted_lines) + "\n" + raw_output
        return raw_output

    def _colorize_match(match: re.Match[str]) -> str:
        filename, line_str, kind, code, message = match.groups()
        k_lower = kind.lower().strip()

        kind_color = ANSI_RED if "error" in k_lower else ANSI_YELLOW

        return (
            f"{ANSI_CYAN}{filename}{ANSI_RESET}:{ANSI_BOLD}{line_str}{ANSI_RESET}: "
            f"{kind_color}{kind} {code}{ANSI_RESET}: {message}"
        )

    colorized_text = DIAGNOSTIC_PATTERN.sub(_colorize_match, raw_output)

    if formatted_lines:
        return "\n".join(formatted_lines) + "\n" + colorized_text
    return colorized_text
