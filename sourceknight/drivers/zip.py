import contextlib
import logging
import os
import platform
import uuid
import zipfile
from typing import TYPE_CHECKING

from ..errors import SkError
from ..utils import FileManager, extract_and_copy
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
        with FileManager(self.ctx, uuid.uuid4().hex, True) as tmp:
            zip_path = os.path.join(self.ctx.path, str(self.model.params['location']))
            tmp_path = tmp.path

            if platform.system() == 'Windows':
                tmp_path = tmp_path.replace('/', '\\')

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                logging.info(" Unpacking archive...")

                tmp_abs = os.path.abspath(tmp_path)
                for member in zip_ref.namelist():
                    member_path = os.path.abspath(os.path.join(tmp_path, member))
                    if not member_path.startswith(tmp_abs):
                        raise SkError("Attempted Path Traversal in Zip File")

                zip_ref.extractall(tmp_path)

            extract_and_copy(self, locations, mgr, tmp)

