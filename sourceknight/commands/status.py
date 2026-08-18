import argparse
import logging

from sourceknight import Dependency

from .command import Command


class Status(Command):
    name = "status"
    help = "Print status of dependencies"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help="Print additional information")

    def __call__(self, args: argparse.Namespace) -> None:
        for dep in map(Dependency.from_yaml, self._context.defs.get('dependencies', [])):
            if not dep.name:
                continue
            cache = Dependency()
            build = Dependency()
            if dep.name in self._context.state.dependencies:
                cache = Dependency.from_yaml(self._context.state.dependencies[dep.name])
            if dep.name in self._context.state.build:
                build = Dependency.from_yaml(self._context.state.build[dep.name])
            logging.info(dep.name)
            if cache.version is not None:
                logging.info(" Cached version: %s", cache.version)
            if build.version is not None:
                logging.info(" Unpacked version: %s", build.version)
            if args.verbose:
                logging.info(" Additional parameters:")
                for k, v in cache.params.items():
                    logging.info("  %s = %s", k, v)

