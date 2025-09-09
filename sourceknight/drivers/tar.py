import logging
import os
import tarfile
import uuid

from .base import basedriver
from ..utils import FileManager, tar_safe_extract, extract_and_copy


class TarDriver(basedriver):
    def __init__(self, ctx, model):
        super().__init__(ctx, model)

    def cleanup(self):
        os.unlink(os.path.join(self.ctx.path, self.model.params['location']))

    def update(self, mgr):
        path = mgr.acquire(self.model.params['location'])
        mgr.release(path)
        self.ctx.state.update(dependencies={
            self.model.name: self.model.state(location=os.path.relpath(path, self.ctx.path), driver='tar')
        })

    def unpack(self, mgr, locations):
        with FileManager(self.ctx, uuid.uuid4().hex, True) as tmp:
            with tarfile.open(os.path.join(self.ctx.path, self.model.params['location'])) as tar:
                logging.info(" Unpacking archive...")
                tar_safe_extract(tar, tmp.path)

            extract_and_copy(self, locations, mgr, tmp)