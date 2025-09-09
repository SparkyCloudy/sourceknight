import argparse
import sys
import logging

from sourceknight import Update, Status, unpack, CompileManager, Build, context
from .errors import SkError

def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser("sourceknight", description="simple dependency manager for sourcemod projects")
    parser.add_argument('-p,--path', dest="path",
                        help="Path to the root of your project (directory containing sourceknight.yaml) - defaults to current directory",
                        default=".")

    subparsers = parser.add_subparsers(dest='command')
    subparsers.required = True

    Update.add_args(Update.install(subparsers))
    Status.add_args(Status.install(subparsers))
    unpack.add_args(unpack.install(subparsers))
    CompileManager.add_args(CompileManager.install(subparsers))
    Build.add_args(Build.install(subparsers))

    args = parser.parse_args()

    command_map = {
        'update': Update,
        'status': Status,
        'unpack': unpack,
        'compile': CompileManager,
        'build': Build
    }

    try:
        try:
            command = command_map[args.command]
        except KeyError:
            raise SkError("Unknown command {:s}".format(args.command))
        with context(args.path) as ctx:
            command(ctx)(args)
    except SkError as e:
        logging.error(e)
        sys.exit(1)

    sys.exit(0)
