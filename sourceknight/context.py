import argparse
import logging
import os
from typing import Any

import yaml

try:
    from yaml import CDumper as yamlDumper  # type: ignore
    from yaml import CLoader as yamlLoader  # type: ignore
except ImportError:
    from yaml import Dumper as yamlDumper  # type: ignore
    from yaml import Loader as yamlLoader  # type: ignore

from .errors import SkError
from .state import State


class Context:
    """Encapsulates project directory context, definitions, and state."""

    def __init__(self, path: str, args: argparse.Namespace | None = None) -> None:
        self.path: str = path
        self.args: argparse.Namespace | None = args
        self._exists: bool = False
        self.defs: dict[str, Any] = {}
        self.state: State = State()

    def ensure_working_directory_exists(self) -> None:
        """Creates the .sourceknight directory inside project root if needed."""
        if not self._exists:
            from sourceknight.utils import ensure_path_exists
            ensure_path_exists(os.path.join(self.path, '.sourceknight'))
            self._exists = True

    def _apply_overrides(self) -> None:
        """Applies version overrides from CLI arguments and environment variables."""
        cli_overrides: dict[str, str] = {}
        if self.args and getattr(self.args, 'override_dep', None):
            for item in self.args.override_dep:
                if '=' in item:
                    dep_name, dep_version = item.split('=', 1)
                    cli_overrides[dep_name.strip()] = dep_version.strip()

        dependencies = self.defs.get('dependencies', [])
        for dep in dependencies:
            name = dep.get('name')
            if not name:
                continue

            # Check CLI overrides
            if name in cli_overrides:
                dep['version'] = cli_overrides[name]
                logging.info("Applied CLI override for %s -> version: %s", name, dep['version'])
                continue

            # Check Environment Variable overrides (e.g. SK_OVERRIDE_SOURCEMOD, SK_OVERRIDE_EXTEND_MAP)
            env_key_standard = f"SK_OVERRIDE_{name.upper()}"
            env_key_sanitized = f"SK_OVERRIDE_{name.upper().replace('-', '_')}"
            env_version = os.environ.get(env_key_standard) or os.environ.get(env_key_sanitized)

            if env_version:
                dep['version'] = env_version
                logging.info("Applied ENV override for %s -> version: %s", name, dep['version'])

    def __enter__(self) -> "Context":
        from sourceknight.utils import check_version

        # Load project definitions
        try:
            path = os.path.join(self.path, 'sourceknight.yaml')
            with open(path, encoding='utf-8') as fh:
                loaded = yaml.load(fh, Loader=yamlLoader)
                if not loaded or 'project' not in loaded:
                    raise SkError("sourceknight.yaml must define a root 'project' section")
                self.defs = loaded['project']
        except OSError as err:
            raise SkError("Project directory does not exist or does not contain sourceknight.yaml") from err
        except yaml.YAMLError as e:
            err_str = str(e)
            mark = getattr(e, 'problem_mark', None)
            if mark is not None:
                err_str += f" ({mark.line + 1}:{mark.column + 1})"
            raise SkError(f"Failed parsing sourceknight.yaml: {err_str}") from e

        check_version(self.defs)
        self._apply_overrides()

        # Load or create state
        try:
            state_path = os.path.join(self.path, '.sourceknight', 'state.yaml')
            with open(state_path, encoding='utf-8') as fh:
                self.state = State.from_yaml(self.defs, yaml.load(fh, Loader=yamlLoader))
            self._exists = True
        except OSError:
            self.state = State()
        except yaml.YAMLError as err:
            raise SkError("sourceknight state is corrupted, try removing the .sourceknight directory") from err

        return self


    def __exit__(self, *exception: object) -> None:
        # Dump state if updated
        if self.state and not self.state.clean():
            self.ensure_working_directory_exists()
            path = os.path.join(self.path, '.sourceknight', 'state.yaml')
            with open(path, 'w', encoding='utf-8') as fh:
                yaml.dump(self.state.serialize(), fh, Dumper=yamlDumper)

