import argparse
from typing import Any

from .actions import do_package
from .command import Command


class Package(Command):
    name = "package"
    help = "Package compiled plugins and runtime assets for distribution"

    @classmethod
    def install(cls, subparsers: Any) -> None:
        parser = subparsers.add_parser(cls.name, help=cls.help, aliases=["pack"])
        cls.add_args(parser)

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-o",
            "--output",
            dest="output",
            default=None,
            help="Destination directory for the package (defaults to manifest or .sourceknight/package)",
        )
        parser.add_argument(
            "--zip",
            action="store_true",
            default=False,
            help="Generate .zip compressed release archive",
        )
        parser.add_argument(
            "--tar",
            "--tar-gz",
            dest="tar",
            action="store_true",
            default=False,
            help="Generate .tar.gz compressed release archive",
        )
        parser.add_argument(
            "--no-clean",
            dest="clean",
            action="store_false",
            default=True,
            help="Do not delete existing output directory before packaging",
        )

    def __call__(self, args: argparse.Namespace) -> None:
        do_package(
            self._context,
            output_dir=getattr(args, "output", None),
            create_zip=getattr(args, "zip", False),
            create_tar=getattr(args, "tar", False),
            clean=getattr(args, "clean", True),
        )
