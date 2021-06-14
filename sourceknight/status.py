
from .dependencies import dependency

class status (object):
    def __init__(self, context):
        self._ctx = context

    @classmethod
    def install(cls, subparsers):
        parser = subparsers.add_parser('status', help='Print status of dependencies')
        parser.add_argument('-v,--verbose', dest='verbose', action='store_true', help="Print additional information")

    def __call__(self, args):
        for dep in map(dependency.from_yaml, self._ctx._defs['project']['dependencies']):
            cache = dependency()
            build = dependency()
            if dep.name in self._ctx._state.dependencies:
                cache = dependency.from_yaml(self._ctx._state.dependencies[dep.name])
            if dep.name in self._ctx._state.build:
                build = dependency.from_yaml(self._ctx._state.build[dep.name])
            print(dep.name)
            if cache.version is not None:
                print(" Cached version: {:s}".format(cache.version))
            if build.version is not None:
                print(" Unpacked version: {:s}".format(build.version))
            if args.verbose:
                print(" Additional parameters:")
                for k, v in cache.params.items():
                    print("  {:s} = {:s}".format(k,v))
