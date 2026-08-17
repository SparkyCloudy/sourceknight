import contextlib
import logging
import mimetypes
import os
import pathlib
import platform
import shutil
import uuid
from collections.abc import Callable
from importlib.metadata import version
from typing import Any, Self
from urllib.parse import urlparse
from urllib.request import url2pathname

import requests
from requests.adapters import HTTPAdapter

from .errors import SkError


# https://stackoverflow.com/a/27786580
class LocalFileAdapter(HTTPAdapter):
    """Adapter to allow requests to fetch local file:// URIs."""

    @staticmethod
    def _chkpath(method: str, path: str) -> tuple[int, str]:
        if method.lower() in ('put', 'delete'):
            return 501, "Not Implemented"
        elif method.lower() not in ('get', 'head'):
            return 405, "Method Not Allowed"
        elif os.path.isdir(path):
            return 400, "Path Not A File"
        elif not os.path.isfile(path):
            return 404, "File Not Found"
        elif not os.access(path, os.R_OK):
            return 403, "Access Denied"
        else:
            return 200, "OK"

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: Any = True,
        cert: Any = None,
        proxies: Any = None,
    ) -> requests.Response:
        path = os.path.normcase(os.path.normpath(url2pathname(request.path_url or "")))
        response = requests.Response()

        method = request.method or "GET"
        response.status_code, response.reason = self._chkpath(method, path)
        if response.status_code == 200 and method.lower() != 'head':
            try:
                response.raw = open(path, 'rb')  # noqa: SIM115
            except OSError as err:
                response.status_code = 500
                response.reason = str(err)

        if isinstance(request.url, bytes):
            response.url = request.url.decode('utf-8')
        else:
            response.url = request.url or ""

        response.request = request
        response.connection = self

        return response

    def close(self) -> None:
        pass


def ensure_path_exists(p: str | pathlib.Path) -> None:
    """Ensures that the directory hierarchy for path p exists."""
    pathlib.Path(p).mkdir(parents=True, exist_ok=True)


class FileManager:
    """Manages temporary files and directories within .sourceknight."""

    def __init__(self, ctx: Any, directory: str, entire_directory: bool = False) -> None:
        self._ctx = ctx
        self._sess = requests.session()
        self._sess.mount("file://", LocalFileAdapter())
        self._tmpfiles: list[str] = []
        self.path: str = str(os.path.join(self._ctx.path, '.sourceknight', directory))
        self._entire_dir: bool = entire_directory
        mimetypes.init()

    def __enter__(self) -> Self:
        ensure_path_exists(self.path)
        return self

    def __exit__(self, *exc: object) -> None:
        for f in self._tmpfiles:
            with contextlib.suppress(OSError):
                os.unlink(f)
        if self._entire_dir:
            shutil.rmtree(self.path, ignore_errors=True)

    def release_dir(self) -> None:
        """Prevents directory from being deleted on exit."""
        self._entire_dir = False

    def release(self, file: str) -> None:
        """Removes a file from temporary tracking."""
        if file in self._tmpfiles:
            self._tmpfiles.remove(file)

    def acquire(self, url: str) -> str:
        """Downloads or fetches a file from URL and saves it to a temp path."""
        logging.info(" Downloading %s...", url)
        req = self._sess.get(url)
        req.raise_for_status()

        ext: str | None = None
        content_type = req.headers.get('content-type')
        if content_type:
            ext = mimetypes.guess_extension(content_type)
        if ext is None:
            guessed_type = mimetypes.guess_type(url)[0]
            if guessed_type:
                ext = mimetypes.guess_extension(guessed_type)
        if ext is None:
            ext = os.path.splitext(urlparse(url).path)[1]

        tmp = os.path.join(self.path, f'{uuid.uuid4().hex}{ext}')
        self._tmpfiles.append(tmp)

        with open(tmp, 'wb') as fh:
            fh.write(req.content)

        return tmp


class cd:
    """Context manager for temporarily changing working directory."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._prev = os.getcwd()

    def __enter__(self) -> None:
        self._prev = os.getcwd()
        os.chdir(self._path)

    def __exit__(self, *exc: object) -> None:
        os.chdir(self._prev)


def once[F: Callable[..., Any]](fn: F) -> F:
    """Decorator to ensure a function only executes once and caches result."""
    state = {'already_run': False, 'last_res': None}

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if state['already_run']:
            return state['last_res']
        state['last_res'] = fn(*args, **kwargs)
        state['already_run'] = True
        return state['last_res']

    return wrapped  # type: ignore[return-value]



class SkVersion:
    """Sourceknight version comparator."""

    class SkCompatible:
        major: bool = False
        newer: bool = False

    def __init__(self, v: Any) -> None:
        v_str = str(v)
        parts = v_str.split('.', 2)
        self.major = int(parts[0])
        self.minor = int(parts[1]) if len(parts) > 1 else 0

    def compatibility(self, other: "SkVersion") -> "SkVersion.SkCompatible":
        res = SkVersion.SkCompatible()
        if self.major != other.major:
            res.major = True
        elif self.minor < other.minor:
            res.newer = True
        return res

    def __str__(self) -> str:
        return f"{self.major:d}.{self.minor:d}"


@once
def check_version(defs: dict[str, Any]) -> None:
    """Validates manifest sourceknight version against currently installed version."""
    try:
        ver_str = defs['sourceknight']
    except KeyError:
        logging.warning("No version detected in manifest, defaulting to 0.1. In the future, a version will be required in the manifest.")
        ver_str = "0.1"
    ver = SkVersion(ver_str)
    try:
        cur_ver_str = version('sourceknight')
    except Exception:
        # Fallback when running directly from source tree
        cur_ver_str = "0.5"
    cur = SkVersion(cur_ver_str)
    err = RuntimeError("this version of sourceknight is incompatible with this manifest")
    compat = cur.compatibility(ver)
    if compat.major:
        logging.error("This manifest is from a different major version of sourceknight than what is currently installed (%s vs %s)", ver, cur)
        raise err
    if compat.newer:
        logging.error("This manifest requires a newer version of sourceknight than is currently installed (%s vs %s)", ver, cur)
        raise err


def resolve_heuristic_locations(base_path: str) -> list[dict[str, str]]:
    """
    Scans base_path for standard SourceMod directory structures and
    generates automatic unpack location mappings.
    """
    locations: list[dict[str, str]] = []

    if not os.path.exists(base_path):
        return locations

    # 1. If 'addons' folder exists at top level (e.g. SourceMod full package)
    if os.path.isdir(os.path.join(base_path, 'addons')):
        locations.append({'source': '/addons', 'dest': '/addons'})
        return locations

    # 2. Check standard SourceMod subdirectories at root
    mappings = {
        'scripting': '/addons/sourcemod/scripting',
        'include': '/addons/sourcemod/scripting/include',
        'plugins': '/addons/sourcemod/plugins',
        'gamedata': '/addons/sourcemod/gamedata',
        'translations': '/addons/sourcemod/translations',
        'extensions': '/addons/sourcemod/extensions',
        'configs': '/addons/sourcemod/configs',
    }

    for folder, dest in mappings.items():
        if os.path.isdir(os.path.join(base_path, folder)):
            locations.append({'source': f'/{folder}', 'dest': dest})

    # 3. If there are loose .inc files in the root
    if os.path.isdir(base_path):
        has_loose_inc = any(f.endswith('.inc') and os.path.isfile(os.path.join(base_path, f)) for f in os.listdir(base_path))
        if has_loose_inc and not any(loc['dest'] == '/addons/sourcemod/scripting/include' for loc in locations):
            for f in os.listdir(base_path):
                if f.endswith('.inc') and os.path.isfile(os.path.join(base_path, f)):
                    locations.append({'source': f'/{f}', 'dest': f'/addons/sourcemod/scripting/include/{f}'})

    return locations


def extract_and_copy(drvcls: Any, locations: list[dict[str, str]], mgr: FileManager, tmp: FileManager) -> None:
    """Extracts files from driver source and copies them into the target build tree."""
    from sourceknight.drivers import GitDriver

    # Apply heuristic auto-unpacking if no unpack locations were explicitly provided
    if not locations:
        if isinstance(drvcls, GitDriver):
            base_search = os.path.normpath(os.path.join(drvcls.ctx.path, str(drvcls.model.params.get('location', ''))))
        else:
            base_search = tmp.path
        locations = resolve_heuristic_locations(base_search)
        if locations:
            logging.info(" Auto-detected unpack locations: %s", locations)
        else:
            logging.warning(" No unpack rules specified and no standard SourceMod directories detected for %s.", drvcls.model.name)

    for loc_rule in locations:
        src_entry = str(loc_rule['source'])
        dest_entry = str(loc_rule['dest'])
        src_entry = src_entry.removeprefix('/')
        dest_entry = dest_entry.removeprefix('/')

        if isinstance(drvcls, GitDriver):
            src = os.path.normpath(os.path.join(drvcls.ctx.path, str(drvcls.model.params.get('location', '')), src_entry))
        else:
            src = os.path.normpath(os.path.join(tmp.path, src_entry))
        dst = os.path.normpath(os.path.join(mgr.path, dest_entry))

        logging.info("Extracting %s to %s", src, dst)

        if not os.path.exists(src):
            logging.error("Source path does not exist: %s", src)
            continue

        if os.path.isdir(src):
            ensure_path_exists(dst)
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            ensure_path_exists(os.path.dirname(dst))
            shutil.copy(src, dst)

    drvcls.ctx.state.update(build={
        drvcls.model.name: drvcls.model.state(driver=drvcls.model.type)
    })


def tar_is_within_directory(directory: str, target: str) -> bool:
    """Verifies that target is inside directory to prevent path traversal."""
    abs_directory = os.path.abspath(directory)
    abs_target = os.path.abspath(target)
    prefix = os.path.commonprefix([abs_directory, abs_target])
    return prefix == abs_directory


def tar_safe_extract(tar: Any, path: str = ".", members: Any = None, *, numeric_owner: bool = False) -> None:
    """Safely extracts members from a tar archive, preventing directory traversal."""
    for member in tar.getmembers():
        member_path = os.path.join(path, member.name)
        if not tar_is_within_directory(path, member_path):
            raise SkError("Attempted Path Traversal in Tar File")

    tar.extractall(path, members, numeric_owner=numeric_owner)



def adjust_sourcemod_platform(model: Any) -> Any:
    """Adjusts sourcemod archive platform extension based on host operating system."""
    if model.type == "smdrop":
        return model
    if str(model.name).lower() == "sourcemod":
        if platform.system() == "Windows":
            model.type = "zip"
            model.params['location'] = str(model.params.get('location', '')).replace("linux.tar.gz", "windows.zip")
        elif platform.system() == "Linux":
            model.type = "tar"
            model.params['location'] = str(model.params.get('location', '')).replace("windows.zip", "linux.tar.gz")

    return model