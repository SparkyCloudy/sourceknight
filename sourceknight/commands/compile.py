import argparse
import concurrent.futures
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from typing import Any

from sourceknight import SkError
from sourceknight.diagnostics import format_compiler_output, is_color_enabled
from sourceknight.utils import cd, ensure_path_exists

from .command import Command


def _compile_single_target(compiler_path: str, target: str, abs_output: str) -> dict[str, Any]:
    """Compiles a single SourcePawn target in the current working directory."""
    infile = f"{target}.sp"
    outfile = os.path.join(abs_output, f"{target}.smx")
    result = subprocess.run(
        [compiler_path, infile, f"-o{outfile}"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    return {
        "target": target,
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


class Compile(Command):
    name = "compile"
    help = "Compile a set of sourcemod targets"

    if platform.architecture()[0] == "64bit":
        _default_compiler = "/addons/sourcemod/scripting/spcomp64"
    else:
        _default_compiler = "/addons/sourcemod/scripting/spcomp"
    _default_workdir = "/addons/sourcemod/scripting/"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-o,--output-dir",
            dest="output",
            default=None,
            help="Specify directory to store compiled smx files (default from manifest, or current directory if not specified)",
        )
        parser.add_argument(
            "-j",
            "--jobs",
            "--parallel",
            dest="jobs",
            type=int,
            default=None,
            help="Number of concurrent compilation jobs to run in parallel (default: auto-detect based on CPU cores)",
        )
        parser.add_argument(
            "--no-color",
            dest="no_color",
            action="store_true",
            default=False,
            help="Disable ANSI color output in compiler diagnostics",
        )
        parser.add_argument(
            "--fail-fast",
            dest="fail_fast",
            action="store_true",
            help="Abort immediately on the first compilation failure",
        )
        parser.add_argument(
            "--report",
            dest="report",
            default=None,
            choices=["json"],
            help="Generate a structured report of the compilation results (e.g., json)",
        )
        parser.add_argument(
            "targets",
            nargs="*",
            help="List of specific targets to compile (by default, will compile all)",
        )

    def __call__(self, args: argparse.Namespace) -> None:
        self._context.ensure_working_directory_exists()

        all_targets: list[str] = self._context.defs.get("targets", [])
        targets: list[str] = args.targets
        if not len(targets):
            targets = all_targets
        elif any(t not in all_targets for t in targets):
            raise SkError(
                "One or more of specified targets not defined: {}".format(
                    ", ".join(targets)
                )
            )

        workdir = self._context.defs.get("workdir", self._default_workdir)
        workdir = workdir.removeprefix("/")

        compiler = self._context.defs.get("compiler", self._default_compiler)
        compiler = compiler.removeprefix("/")

        root = self._context.defs.get("root")
        if root and root.startswith("/"):
            root = root[1:]

        output = args.output
        if output is None:
            output = self._context.defs.get("output", ".")
            if output.startswith("/"):
                output = output[1:]
            abs_output = os.path.abspath(os.path.join(self._context.path, output))
        else:
            abs_output = os.path.abspath(output)

        buildroot = os.path.join(self._context.path, ".sourceknight", "build")
        workdir_path = os.path.join(buildroot, workdir)
        compiler_path = os.path.abspath(os.path.join(buildroot, compiler))

        # Resolve compiler executable with cross-platform fallbacks
        candidates = [compiler_path]
        if platform.system() == "Windows":
            candidates = [
                compiler_path,
                compiler_path + ".exe",
                compiler_path.replace("spcomp64", "spcomp"),
                compiler_path.replace("spcomp64", "spcomp") + ".exe",
                compiler_path.replace("spcomp", "spcomp64"),
                compiler_path.replace("spcomp", "spcomp64") + ".exe",
            ]
        else:
            candidates = [
                compiler_path,
                compiler_path.replace("spcomp64", "spcomp"),
                compiler_path.replace("spcomp", "spcomp64"),
            ]

        resolved_compiler: str | None = None
        for candidate in candidates:
            if os.path.isfile(candidate):
                resolved_compiler = candidate
                break

        if not resolved_compiler:
            raise SkError(f"Compiler executable not found at {compiler_path}")

        compiler_path = resolved_compiler

        if platform.system() != "Windows":
            try:
                st = os.stat(compiler_path)
                os.chmod(compiler_path, st.st_mode | 0o111)
            except OSError:
                pass

        if root is not None:
            logging.info("Copying sources...")

            def copy_filter(directory: str, contents: list[str]) -> list[str]:
                return list(filter(lambda c: c[0] == ".", contents))

            shutil.copytree(
                str(os.path.join(self._context.path, root)),
                buildroot,
                dirs_exist_ok=True,
                ignore=copy_filter,
            )

        report_path = os.path.abspath(
            os.path.join(self._context.path, "compile_report.json")
        )
        color_enabled = is_color_enabled(getattr(args, "no_color", False))

        # Determine concurrency level
        num_targets = len(targets)
        if args.jobs is not None:
            jobs = max(1, args.jobs)
        else:
            cpu_cores = os.cpu_count() or 4
            jobs = min(cpu_cores, max(1, num_targets))

        with cd(workdir_path):
            ensure_path_exists(abs_output)
            results_by_target: dict[str, dict[str, Any]] = {}
            has_failure = False

            if jobs > 1 and num_targets > 1:
                logging.info(
                    "Compiling %d target(s) in parallel (jobs=%d)...", num_targets, jobs
                )
                with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
                    future_to_target = {
                        executor.submit(
                            _compile_single_target, compiler_path, t, abs_output
                        ): t
                        for t in targets
                    }

                    for future in concurrent.futures.as_completed(future_to_target):
                        t = future_to_target[future]
                        res = future.result()
                        results_by_target[t] = res

                        logging.info("Building %s...", t)
                        if res["stdout"]:
                            formatted = format_compiler_output(
                                res["stdout"], color=color_enabled
                            )
                            sys.stdout.write(formatted)
                        if res["stderr"]:
                            formatted = format_compiler_output(
                                res["stderr"], color=color_enabled
                            )
                            sys.stderr.write(formatted)

                        if not res["success"]:
                            has_failure = True
                            logging.error(
                                "Compilation failed for target '%s' with exit code %s",
                                t,
                                res["returncode"],
                            )
                            if args.fail_fast:
                                for f in future_to_target:
                                    f.cancel()
                                break
            else:
                for t in targets:
                    logging.info("Building %s...", t)
                    res = _compile_single_target(compiler_path, t, abs_output)
                    results_by_target[t] = res

                    if res["stdout"]:
                        formatted = format_compiler_output(
                            res["stdout"], color=color_enabled
                        )
                        sys.stdout.write(formatted)
                    if res["stderr"]:
                        formatted = format_compiler_output(
                            res["stderr"], color=color_enabled
                        )
                        sys.stderr.write(formatted)

                    if not res["success"]:
                        has_failure = True
                        logging.error(
                            "Compilation failed for target '%s' with exit code %s",
                            t,
                            res["returncode"],
                        )
                        if args.fail_fast:
                            break

            # Preserve deterministic original target order in results
            results = [
                results_by_target[t]
                for t in targets
                if t in results_by_target
            ]

            success_count = sum(1 for r in results if r["success"])
            fail_count = len(results) - success_count

            if len(targets) > 1 or args.report:
                logging.info(
                    "Compilation summary: %d succeeded, %d failed out of %d total target(s).",
                    success_count,
                    fail_count,
                    len(results),
                )

            if args.report == "json":
                report_data = {
                    "summary": {
                        "total": len(results),
                        "success": success_count,
                        "failed": fail_count,
                    },
                    "targets": results,
                }
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(report_data, f, indent=2)
                logging.info(f"Structured JSON report written to {report_path}")

            if has_failure:
                raise SkError(f"Compilation failed for {fail_count} target(s).")
