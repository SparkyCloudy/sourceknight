import contextlib
import logging
import os
import tarfile
import uuid
from typing import TYPE_CHECKING

from ..utils import FileManager, extract_and_copy, tar_safe_extract
from .base import basedriver

if TYPE_CHECKING:
    from sourceknight.context import Context
    from sourceknight.dependencies import Dependency


class TarDriver(basedriver):
    """Driver for downloading and unpacking .tar and .tar.gz archives."""

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
            self.model.name: self.model.state(location=os.path.relpath(path, self.ctx.path), driver='tar')
        })

    def unpack(self, mgr: FileManager, locations: list[dict[str, str]]) -> None:
        with FileManager(self.ctx, uuid.uuid4().hex, True) as tmp:
            state = self.ctx.state.dependencies.get(self.model.name, {})
            loc = state.get('location', self.model.params.get('location', ''))
            archive_path = os.path.join(self.ctx.path, str(loc))
            with tarfile.open(archive_path) as tar:
                logging.info(" Unpacking archive...")
                tar_safe_extract(tar, tmp.path)

            extract_and_copy(self, locations, mgr, tmp)