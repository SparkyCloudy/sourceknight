import argparse
import logging

from .actions import do_unpack, do_update
from .command import Command
from .compile import Compile
from .unpack import Unpack
from .update import Update


class Build(Command):
    name = "build"
    help = "Equivalent to running update, unpack, compile"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        Update.add_args(parser)
        Unpack.add_args(parser)
        Compile.add_args(parser)

    def __call__(self, args: argparse.Namespace) -> None:
        logging.info("Updating...")
        do_update(self._context, args.force)

        logging.info("Unpacking...")
        do_unpack(self._context, args.force, args.clean)

        logging.info("Compiling...")
        Compile(self._context)(args)

        logging.info("Done")

