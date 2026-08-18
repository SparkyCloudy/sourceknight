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
        rel_path = str(self.model.params.get('path') or self.model.params.get('location') or '')
        src_path = os.path.normpath(os.path.join(self.ctx.path, rel_path))
        if not os.path.exists(src_path):
            raise SkError(f"Local file dependency not found: {src_path}")

        self.ctx.state.update(dependencies={
            self.model.name: self.model.state(location=os.path.relpath(src_path, self.ctx.path), driver='file')
        })

    def unpack(self, mgr: FileManager, locations: list[dict[str, str]]) -> None:
        name = str(self.model.name or "")
        state = self.ctx.state.dependencies.get(name, {})
        loc = state.get('location', self.model.params.get('path', self.model.params.get('location', '')))
        src_path = os.path.normpath(os.path.join(self.ctx.path, str(loc)))

        class _LocalPathWrapper:
            def __init__(self, path: str) -> None:
                self.path = path

        extract_and_copy(self, locations, mgr, _LocalPathWrapper(src_path))  # type: ignore[arg-type]