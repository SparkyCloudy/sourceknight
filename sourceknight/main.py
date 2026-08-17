import argparse
import logging
import sys

from sourceknight import Context, SkError
from sourceknight.commands.build import Build
from sourceknight.commands.compile import Compile
from sourceknight.commands.status import Status
from sourceknight.commands.unpack import Unpack
from sourceknight.commands.update import Update


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser("sourceknight", description="simple dependency manager for sourcemod projects")
    parser.add_argument('-p,--path', dest="path",
                        help="Path to the root of your project (directory containing sourceknight.yaml) - defaults to current directory",
                        default=".")
    parser.add_argument('--override-dep', action='append', default=[],
                        help="Override dependency version (e.g. --override-dep sourcemod=1.12.x)")

    subparsers = parser.add_subparsers(dest='command')
    subparsers.required = True

    # A list of all available command classes
    commands = [Update, Status, Unpack, Compile, Build]

    # Dynamically create a map from command name to class
    command_map = {cmd.name: cmd for cmd in commands}

    # Install all commands
    for command in commands:
        command.install(subparsers)

    args = parser.parse_args()

    try:
        try:
            command = command_map[args.command]
        except KeyError:
            raise SkError(f"Unknown command {args.command}") from None
        with Context(args.path, args=args) as ctx:
            command(ctx)(args)
    except SkError as e:

        logging.error(e)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

