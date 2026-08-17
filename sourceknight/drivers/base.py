from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sourceknight.context import Context
    from sourceknight.dependencies import Dependency
    from sourceknight.utils import FileManager


class basedriver:
    """Abstract base class for all dependency driver implementations."""

    def __init__(self, ctx: "Context", model: "Dependency") -> None:
        self.ctx: Context = ctx
        self.model: Dependency = model

    def check_update(self, current: Optional["Dependency"]) -> bool:
        """Determines if a dependency needs to be updated."""
        if current is None or current.version is None:
            return True
        return current.version != self.model.version


    def update(self, mgr: "FileManager") -> None:
        """Fetches or downloads dependency into local cache."""
        raise NotImplementedError()

    def unpack(self, mgr: "FileManager", locations: list[dict[str, str]]) -> None:
        """Unpacks dependency into target build tree."""
        raise NotImplementedError()

    def cleanup(self) -> None:
        """Performs cleanup of cached files if necessary."""
