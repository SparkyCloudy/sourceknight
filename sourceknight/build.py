from .update import Update
from .unpack import unpack
from .compilemanager import CompileManager
import logging


class Build:
    def __init__(self, ctx):
        self._ctx = ctx
        self._update = Update
        self._unpack = unpack
        self._compile = CompileManager

    @classmethod
    def install(cls, subparsers):
        return subparsers.add_parser('build', help='Equivalent to running update, unpack, compile')

    @classmethod
    def add_args(cls, parser):
        Update.add_args(parser)
        unpack.add_args(parser)
        CompileManager.add_args(parser)

    def __call__(self, args):
        ctx = self._ctx
        logging.info("Updating...")
        Update(ctx)(args)
        logging.info("Unpacking...")
        unpack(ctx)(args)
        logging.info("Compiling...")
        CompileManager(ctx)(args)
        logging.info("Done")
