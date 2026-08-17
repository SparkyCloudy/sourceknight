import argparse
import logging
import os
import platform
import shutil
import subprocess

from sourceknight import SkError
from sourceknight.utils import cd, ensure_path_exists

from .command import Command


class Compile(Command):
    name = "compile"
    help = "Compile a set of sourcemod targets"

    if platform.architecture()[0] == '64bit':
        _default_compiler = "/addons/sourcemod/scripting/spcomp64"
    else:
        _default_compiler = "/addons/sourcemod/scripting/spcomp"
    _default_workdir = "/addons/sourcemod/scripting/"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('-o,--output-dir', dest='output', default=None,
                            help='Specify directory to store compiled smx files (default from manifest, or current directory if not specified)')
        parser.add_argument('targets', nargs='*',
                            help='List of specific targets to compile (by default, will compile all)')

    def __call__(self, args: argparse.Namespace) -> None:
        self._context.ensure_working_directory_exists()

        all_targets: list[str] = self._context.defs.get('targets', [])
        targets: list[str] = args.targets
        if not len(targets):
            targets = all_targets
        elif any(t not in all_targets for t in targets):
            raise SkError("One or more of specified targets not defined: {}".format(', '.join(targets)))

        workdir = self._context.defs.get('workdir', self._default_workdir)
        workdir = workdir.removeprefix('/')

        compiler = self._context.defs.get('compiler', self._default_compiler)
        compiler = compiler.removeprefix('/')

        root = self._context.defs.get('root')
        if root and root.startswith('/'):
            root = root[1:]

        output = args.output
        if output is None:
            output = self._context.defs.get('output', '.')
            if output.startswith('/'):
                output = output[1:]
            abs_output = os.path.abspath(os.path.join(self._context.path, output))
        else:
            abs_output = os.path.abspath(output)

        buildroot = os.path.join(self._context.path, '.sourceknight', 'build')
        workdir_path = os.path.join(buildroot, workdir)
        compiler_path = os.path.abspath(os.path.join(buildroot, compiler))

        # Resolve compiler executable with cross-platform fallbacks
        candidates = [compiler_path]
        if platform.system() == 'Windows':
            candidates = [
                compiler_path,
                compiler_path + '.exe',
                compiler_path.replace('spcomp64', 'spcomp'),
                compiler_path.replace('spcomp64', 'spcomp') + '.exe',
                compiler_path.replace('spcomp', 'spcomp64'),
                compiler_path.replace('spcomp', 'spcomp64') + '.exe',
            ]
        else:
            candidates = [
                compiler_path,
                compiler_path.replace('spcomp64', 'spcomp'),
                compiler_path.replace('spcomp', 'spcomp64'),
            ]

        resolved_compiler: str | None = None
        for candidate in candidates:
            if os.path.isfile(candidate):
                resolved_compiler = candidate
                break

        if not resolved_compiler:
            raise SkError(f"Compiler executable not found at {compiler_path}")

        compiler_path = resolved_compiler

        if platform.system() != 'Windows':
            try:
                st = os.stat(compiler_path)
                os.chmod(compiler_path, st.st_mode | 0o111)
            except OSError:
                pass

        if root is not None:
            logging.info("Copying sources...")

            def copy_filter(directory: str, contents: list[str]) -> list[str]:
                return list(filter(lambda c: c[0] == '.', contents))

            shutil.copytree(str(os.path.join(self._context.path, root)), buildroot, dirs_exist_ok=True,
                            ignore=copy_filter)

        with cd(workdir_path):
            ensure_path_exists(abs_output)
            for t in targets:
                infile = f'{t}.sp'
                outfile = os.path.join(abs_output, f'{t}.smx')
                logging.info("Building %s...", t)
                result = subprocess.run([compiler_path, infile, f"-o{outfile}"])
                if result.returncode != 0:
                    raise SkError(f"Compilation failed for target '{t}' with exit code {result.returncode}")


