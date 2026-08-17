import os
from typing import TYPE_CHECKING

from ..errors import SkError
from ..utils import FileManager, extract_and_copy
from .base import basedriver

if TYPE_CHECKING:
    from sourceknight.context import Context
    from sourceknight.dependencies import Dependency


class FileDriver(basedriver):
    """Driver for managing local file and directory dependencies."""

    def __init__(self, ctx: "Context", model: "Dependency") -> None:
        super().__init__(ctx, model)

    def update(self, mgr: FileManager) -> None:
        src_path = os.path.normpath(os.path.join(self.ctx.path, str(self.model.params.get('path', ''))))
        if not os.path.exists(src_path):
            raise SkError(f"Local file dependency not found: {src_path}")

        self.ctx.state.update(dependencies={
            self.model.name: self.model.state(location=os.path.relpath(src_path, self.ctx.path), driver='file')
        })

    def unpack(self, mgr: FileManager, locations: list[dict[str, str]]) -> None:
        with FileManager(self.ctx, 'cache') as tmp:
            extract_and_copy(self, locations, mgr, tmp)