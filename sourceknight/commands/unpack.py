import argparse

from .actions import do_unpack
from .command import Command


class Unpack(Command):
    name = "unpack"
    help = "Unpack dependencies into build directory"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('-a,--all', dest='force', action='store_true',
                            help="Force unpacking all dependencies, even if they have not been updated")
        parser.add_argument('-c,--clean', dest='clean', action='store_true',
                            help="Force creating a new unpack directory, even if one already exists")

    def __call__(self, args: argparse.Namespace) -> None:
        do_unpack(self._context, args.force, args.clean)

