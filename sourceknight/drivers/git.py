import logging
import os
import shutil
from typing import TYPE_CHECKING, Optional

from git.repo import Repo

from ..utils import FileManager, extract_and_copy
from .base import basedriver

if TYPE_CHECKING:
    from sourceknight.context import Context
    from sourceknight.dependencies import Dependency


class GitDriver(basedriver):
    """Driver for cloning and checking out Git repositories."""

    def __init__(self, ctx: "Context", model: "Dependency") -> None:
        super().__init__(ctx, model)

    def check_update(self, current: Optional["Dependency"]) -> bool:
        return True

    def update(self, mgr: FileManager) -> None:
        loc = str(os.path.join(self.ctx.path, '.sourceknight', 'cache', str(self.model.name)))

        fetched = False
        if os.path.isdir(loc):
            repo = Repo(loc)
        else:
            logging.info(" Cloning from %s (shallow)", self.model.params['repo'])
            try:
                if self.model.version is not None:
                    repo = Repo.clone_from(self.model.params['repo'], loc, depth=1, branch=str(self.model.version))
                else:
                    repo = Repo.clone_from(self.model.params['repo'], loc, depth=1)
                fetched = True
            except Exception:
                if os.path.exists(loc):
                    shutil.rmtree(loc, ignore_errors=True)
                logging.info(" Shallow clone fallback: performing full clone from %s", self.model.params['repo'])
                repo = Repo.clone_from(self.model.params['repo'], loc)
                fetched = True


        try:
            if self.model.version is None:
                if not fetched:
                    logging.info(" Pulling from %s", repo.remote().url)
                    repo.remote().pull()
                self.model.version = str(repo.head.commit.hexsha)
            else:
                if not fetched:
                    logging.info(" Fetching from %s", repo.remote().url)
                    repo.remote().fetch()
                repo.head.reset(self.model.version, working_tree=True)

            self.ctx.state.update(dependencies={
                self.model.name: self.model.state(location=os.path.relpath(loc, self.ctx.path), driver=self.model.type)
            })
        finally:
            repo.close()

    def unpack(self, mgr: FileManager, locations: list[dict[str, str]]) -> None:
        with FileManager(self.ctx, 'cache') as tmp:
            extract_and_copy(self, locations, mgr, tmp)