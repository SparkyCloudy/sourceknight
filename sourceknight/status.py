
from .dependencies import Dependency

import logging

class Status:
    def __init__(self, context):
        self._ctx = context

    @classmethod
    def install(cls, subparsers):
        return subparsers.add_parser('status', help='Print status of dependencies')
    
    @classmethod
    def add_args(cls, parser):
        parser.add_argument('-v,--verbose', dest='verbose', action='store_true', help="Print additional information")

    def __call__(self, args):
        for dep in map(Dependency.from_yaml, self._ctx.defs['dependencies']):
            cache = Dependency()
            build = Dependency()
            if dep.name in self._ctx.State.dependencies:
                cache = Dependency.from_yaml(self._ctx.State.dependencies[dep.name])
            if dep.name in self._ctx.State.Build:
                build = Dependency.from_yaml(self._ctx.State.Build[dep.name])
            logging.info(dep.name)
            if cache.version is not None:
                logging.info(" Cached version: {:s}".format(cache.version))
            if build.version is not None:
                logging.info(" Unpacked version: {:s}".format(build.version))
            if args.verbose:
                logging.info(" Additional parameters:")
                for k, v in cache.params.items():
                    logging.info("  {:s} = {:s}".format(k,v))
