from .base import basedriver

class FileDriver (basedriver):
    def __init__(self, ctx, model):
        super().__init__(ctx, model)
        raise NotImplementedError

    