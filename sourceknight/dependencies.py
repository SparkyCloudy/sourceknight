import contextlib
import logging
from typing import TYPE_CHECKING, Any

from sourceknight.drivers import (
    FileDriver,
    GitDriver,
    ReleaseDriver,
    SmdropDriver,
    TarDriver,
    ZipDriver,
    basedriver,
)

from .errors import SkError
from .utils import FileManager, adjust_sourcemod_platform

if TYPE_CHECKING:
    from .context import Context


class Dependency:
    """Represents a single dependency model and configuration."""

    def __init__(self) -> None:
        self.name: str | None = None
        self.type: str | None = None
        self.version: str | None = None
        self.params: dict[str, Any] = {}

    def state(self, **kwargs: Any) -> dict[str, Any]:
        """Produces state serialization dictionary for this dependency."""
        d: dict[str, Any] = {
            'name': self.name,
            'version': self.version,
        }
        d.update(kwargs)
        return d

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> "Dependency":
        """Constructs a Dependency instance from YAML dictionary."""
        o = cls()

        def unpack(name: str | None = None, type: str | None = None, version: str | None = None, **kwargs: Any) -> None:
            o.name = name
            o.type = type
            o.version = str(version) if version is not None else None
            o.params.update(kwargs)

        unpack(**data)
        return o


drivers_by_name: dict[str, type[basedriver]] = {
    'tar': TarDriver,
    'git': GitDriver,
    'file': FileDriver,
    'zip': ZipDriver,
    'smdrop': SmdropDriver,
    'release': ReleaseDriver,
}


class DependencyManager:
    """Handles updating and unpacking lifecycle for dependencies."""

    def __init__(self, ctx: "Context") -> None:
        self._ctx = ctx

    def unpack(self, dep: dict[str, Any], locations: list[dict[str, str]], fmgr: FileManager, force: bool = False) -> None:
        """Unpacks dependency into the isolated build tree."""
        d = Dependency.from_yaml(dep)
        if not d.name:
            return

        current_model: Dependency | None = None
        with contextlib.suppress(KeyError):
            current_model = Dependency.from_yaml(self._ctx.state.build[d.name])

        should_unpack = False
        if force or d.version is None or current_model is None or d.version != current_model.version:
            should_unpack = True

        if should_unpack:
            logging.info("Unpacking %s...", d.name)
            driver_name = d.params.get('driver', d.type)
            if not driver_name or driver_name not in drivers_by_name:
                raise SkError(f"Unknown driver '{driver_name}' for dependency '{d.name}'")
            drivers_by_name[driver_name](self._ctx, d).unpack(fmgr, locations)
        else:
            logging.info("Already up to date: %s", d.name)

    def update(self, dep: dict[str, Any], fmgr: FileManager, force: bool = False) -> None:
        """Downloads/fetches dependency into local cache."""
        new_model = Dependency.from_yaml(dep)
        if not new_model.name:
            return

        current_model: Dependency | None = None
        with contextlib.suppress(KeyError):
            current_model = Dependency.from_yaml(self._ctx.state.dependencies[new_model.name])


        # Adjust sourcemod platform if necessary
        new_model = adjust_sourcemod_platform(new_model)

        if not new_model.type or new_model.type not in drivers_by_name:
            raise SkError(f"Unsupported dependency type '{new_model.type}' for '{new_model.name}'")

        driver = drivers_by_name[new_model.type](self._ctx, new_model)

        if force or driver.check_update(current_model):
            logging.info("Updating: %s", new_model.name)
            if current_model is not None:
                curr_driver = current_model.params.get('driver')
                if curr_driver and curr_driver in drivers_by_name:
                    drivers_by_name[curr_driver](self._ctx, current_model).cleanup()
            driver.update(fmgr)
        else:
            logging.info("Already up to date: %s", new_model.name)

