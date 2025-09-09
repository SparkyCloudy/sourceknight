from .dependencies import DependencyManager
from .utils import FileManager


class Update:
    def __init__(self, context):
        self._ctx = context

    @classmethod
    def install(cls, subparsers):
        return subparsers.add_parser('update', help='Fetch or update dependencies')

    @classmethod
    def add_args(cls, parser):
        parser.add_argument('-f,--force', dest='force', action='store_true',
                            help="Force updating all dependencies, even if they are believed to be up to date")

    def __call__(self, args):
        self._ctx.ensure_working_directory_exists()
        dmgr = DependencyManager(self._ctx)
        with FileManager(self._ctx, "cache") as fmgr:
            for dep in self._ctx.defs['dependencies']:
                dmgr.update(dep, fmgr, args.force)
