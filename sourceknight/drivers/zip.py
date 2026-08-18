import contextlib
import logging
import os
from typing import TYPE_CHECKING

from ..utils import FileManager, direct_unpack_zip
from .base import basedriver

if TYPE_CHECKING:
    from sourceknight.context import Context
    from sourceknight.dependencies import Dependency


class ZipDriver(basedriver):
    """Driver for downloading and unpacking .zip archives."""

    def __init__(self, ctx: "Context", model: "Dependency") -> None:
        super().__init__(ctx, model)

    def cleanup(self) -> None:
        loc = self.model.params.get('location')
        if loc:
            full_path = os.path.join(self.ctx.path, loc)
            if os.path.isfile(full_path):
                with contextlib.suppress(OSError):
                    os.unlink(full_path)

    def update(self, mgr: FileManager) -> None:
        path = mgr.acquire(self.model.params['location'])
        mgr.release(path)
        self.ctx.state.update(dependencies={
            self.model.name: self.model.state(location=os.path.relpath(path, self.ctx.path), driver='zip')
        })

    def unpack(self, mgr: FileManager, locations: list[dict[str, str]]) -> None:
        logging.info(" Unpacking %s...", self.model.name)
        name = str(self.model.name or "")
        state = self.ctx.state.dependencies.get(name, {})
        loc = state.get('location', self.model.params.get('location', ''))
        archive_path = os.path.join(self.ctx.path, str(loc))

        direct_unpack_zip(archive_path, mgr.path, locations)

        self.ctx.state.update(build={
            self.model.name: self.model.state(driver='zip')
        })

