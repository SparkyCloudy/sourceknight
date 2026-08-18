import argparse

from .actions import do_update
from .command import Command


class Update(Command):
    name = "update"
    help = "Fetch or update dependencies"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('-f', '--force', dest='force', action='store_true',
                            help="Force updating all dependencies, even if they have already been cached")

    def __call__(self, args: argparse.Namespace) -> None:
        do_update(self._context, args.force)
