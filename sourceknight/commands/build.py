import argparse
import logging

from .actions import do_package, do_unpack, do_update
from .command import Command
from .compile import Compile
from .unpack import Unpack
from .update import Update


class Build(Command):
    name = "build"
    help = "Equivalent to running update, unpack, compile (and optional package)"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        Update.add_args(parser)
        Unpack.add_args(parser)
        Compile.add_args(parser)
        parser.add_argument(
            "-P",
            "--package",
            dest="package",
            action="store_true",
            default=False,
            help="Package compiled plugins and runtime assets after build",
        )
        parser.add_argument(
            "-o",
            "--package-output",
            "--output",
            dest="package_output",
            default=None,
            help="Destination directory for packaging (when using --package)",
        )
        parser.add_argument(
            "--zip",
            action="store_true",
            default=False,
            help="Generate .zip release archive when packaging",
        )
        parser.add_argument(
            "--tar",
            "--tar-gz",
            dest="tar",
            action="store_true",
            default=False,
            help="Generate .tar.gz release archive when packaging",
        )

    def __call__(self, args: argparse.Namespace) -> None:
        logging.info("Updating...")
        do_update(self._context, args.force)

        logging.info("Unpacking...")
        do_unpack(self._context, args.force, args.clean)

        logging.info("Compiling...")
        Compile(self._context)(args)

        should_package = getattr(args, "package", False) or bool(
            self._context.defs.get("package") or getattr(self._context, "package_defs", None)
        )
        if should_package:
            logging.info("Packaging...")
            do_package(
                self._context,
                output_dir=getattr(args, "package_output", None),
                create_zip=getattr(args, "zip", False),
                create_tar=getattr(args, "tar", False),
                clean=getattr(args, "clean", True),
            )

        logging.info("Done")

