from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sourceknight.context import Context


class Command(ABC):
    """
    Abstract base class for all sourceknight commands.
    """
    # The name of the command, e.g., 'build', 'update'
    name: str = ""
    # The help text for the command
    help: str = ""

    def __init__(self, context: Context) -> None:
        self._context: Context = context

    @classmethod
    def install(cls, subparsers: Any) -> None:
        """Installs the command's subparser and arguments."""
        parser = subparsers.add_parser(cls.name, help=cls.help)
        cls.add_args(parser)

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:  # noqa: B027
        """Adds command-specific arguments to the parser. Can be overridden by subclasses."""


    @abstractmethod
    def __call__(self, args: argparse.Namespace) -> None:
        """Executes the command's logic."""
