import contextlib
import logging
import mimetypes
import os
import pathlib
import platform
import shutil
import tarfile
import threading
import uuid
import zipfile
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
        self._lock = threading.Lock()
        self.path: str = str(os.path.join(self._ctx.path, '.sourceknight', directory))
        self._entire_dir: bool = entire_directory
        mimetypes.init()

    def __enter__(self) -> Self:
        ensure_path_exists(self.path)
        return self

    def __exit__(self, *exc: object) -> None:
        with self._lock:
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
        with self._lock:
            if file in self._tmpfiles:
                self._tmpfiles.remove(file)

    def acquire(self, url: str) -> str:
        """Downloads or fetches a file from URL and saves it to a temp path using streaming."""
        logging.info(" Downloading %s...", url)
        with self._sess.get(url, stream=True) as req:
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
            with self._lock:
                self._tmpfiles.append(tmp)

            with open(tmp, 'wb') as fh:
                shutil.copyfileobj(req.raw, fh, length=64 * 1024)

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
        cur_ver_str = "0.6.2"
    cur = SkVersion(cur_ver_str)
    err = RuntimeError("this version of sourceknight is incompatible with this manifest")
    compat = cur.compatibility(ver)
    if compat.major:
        logging.error("This manifest is from a different major version of sourceknight than what is currently installed (%s vs %s)", ver, cur)
        raise err
    if compat.newer:
        logging.error("This manifest requires a newer version of sourceknight than is currently installed (%s vs %s)", ver, cur)
        raise err


def resolve_heuristic_locations(base: str | list[str]) -> list[dict[str, str]]:
    """
    Scans a base path (directory on disk) or a list of entry paths (from archive)
    for standard SourceMod directory structures and generates automatic unpack
    location mappings.
    """
    locations: list[dict[str, str]] = []

    if isinstance(base, list):
        norm_paths = [p.replace('\\', '/').strip().lstrip('./').lstrip('/') for p in base]

        # 1. Top level 'addons' folder
        if any(p == 'addons' or p.startswith('addons/') for p in norm_paths):
            locations.append({'source': '/addons', 'dest': '/addons'})
            return locations

        # 2. Check for '<item>/addons' (e.g. 'game/addons')
        for p in norm_paths:
            parts = p.split('/')
            if len(parts) >= 2 and parts[1] == 'addons':
                item = parts[0]
                locations.append({'source': f'/{item}/addons', 'dest': '/addons'})
                return locations

        # 3. Check standard SourceMod subdirectories at root
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
            if any(p == folder or p.startswith(f'{folder}/') for p in norm_paths):
                locations.append({'source': f'/{folder}', 'dest': dest})

        # 4. Check loose .inc files at root
        has_loose_inc = any('/' not in p and p.endswith('.inc') for p in norm_paths)
        if has_loose_inc and not any(loc['dest'] == '/addons/sourcemod/scripting/include' for loc in locations):
            for p in norm_paths:
                if '/' not in p and p.endswith('.inc'):
                    locations.append({'source': f'/{p}', 'dest': f'/addons/sourcemod/scripting/include/{p}'})

        return locations

    base_path = base
    if not os.path.exists(base_path):
        return locations

    # 1. If 'addons' folder exists at top level (e.g. SourceMod full package)
    if os.path.isdir(os.path.join(base_path, 'addons')):
        locations.append({'source': '/addons', 'dest': '/addons'})
        return locations

    # 2. Check for nested 'game/addons' or 'addons' in immediate subdirectories
    for item in os.listdir(base_path):
        sub_addons = os.path.join(base_path, item, 'addons')
        if os.path.isdir(sub_addons):
            locations.append({'source': f'/{item}/addons', 'dest': '/addons'})
            return locations

    # 3. Check standard SourceMod subdirectories at root
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

    # 4. If there are loose .inc files in the root
    if os.path.isdir(base_path):
        has_loose_inc = any(f.endswith('.inc') and os.path.isfile(os.path.join(base_path, f)) for f in os.listdir(base_path))
        if has_loose_inc and not any(loc['dest'] == '/addons/sourcemod/scripting/include' for loc in locations):
            for f in os.listdir(base_path):
                if f.endswith('.inc') and os.path.isfile(os.path.join(base_path, f)):
                    locations.append({'source': f'/{f}', 'dest': f'/addons/sourcemod/scripting/include/{f}'})

    return locations


def _map_entry_target(entry_name: str, src_prefix: str, dest_prefix: str) -> str | None:
    """Maps an entry name from an archive to its destination relative path if it matches source prefix."""
    entry_clean = entry_name.replace('\\', '/').strip()
    if entry_clean.startswith('/'):
        entry_clean = entry_clean.lstrip('/')
    elif entry_clean.startswith('./'):
        entry_clean = entry_clean[2:]

    clean_src = src_prefix.replace('\\', '/').strip()
    if clean_src.startswith('/'):
        clean_src = clean_src.lstrip('/')
    elif clean_src.startswith('./'):
        clean_src = clean_src[2:]

    clean_dest = dest_prefix.replace('\\', '/').strip()
    if clean_dest.startswith('/'):
        clean_dest = clean_dest.lstrip('/')
    elif clean_dest.startswith('./'):
        clean_dest = clean_dest[2:]

    if clean_src:
        if entry_clean == clean_src:
            rel = ""
        elif entry_clean.startswith(clean_src + "/"):
            rel = entry_clean[len(clean_src) + 1:]
        else:
            return None
    else:
        rel = entry_clean

    if rel:
        return os.path.join(clean_dest, rel) if clean_dest else rel
    return clean_dest


def direct_unpack_tar(archive_path: str, dest_root: str, locations: list[dict[str, str]]) -> None:
    """Directly extracts matching members from a tar archive to the destination build tree without intermediate copies."""
    with tarfile.open(archive_path) as tar:
        if not locations:
            names = [m.name for m in tar.getmembers()]
            locations = resolve_heuristic_locations(names)
            if locations:
                logging.info(" Auto-detected unpack locations: %s", locations)
            else:
                logging.warning(" No unpack rules specified and no standard SourceMod directories detected in archive.")
                return

        abs_dest_root = os.path.abspath(dest_root)

        for loc in locations:
            src_rule = str(loc.get('source', ''))
            dest_rule = str(loc.get('dest', ''))

            for member in tar.getmembers():
                target_rel = _map_entry_target(member.name, src_rule, dest_rule)
                if target_rel is None:
                    continue

                target_path = os.path.abspath(os.path.join(dest_root, target_rel))
                if target_path != abs_dest_root and not target_path.startswith(abs_dest_root + os.sep):
                    raise SkError(f"Attempted Path Traversal in Tar File: {member.name}")

                if member.isdir():
                    os.makedirs(target_path, exist_ok=True)
                elif member.isfile() or member.isreg():
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    f_obj = tar.extractfile(member)
                    if f_obj is not None:
                        with open(target_path, "wb") as out_f:
                            shutil.copyfileobj(f_obj, out_f, length=64 * 1024)
                        if member.mode & 0o111:
                            with contextlib.suppress(OSError):
                                os.chmod(target_path, os.stat(target_path).st_mode | 0o755)
                elif member.issym() or member.islnk():
                    with contextlib.suppress(OSError):
                        if os.path.islink(target_path) or os.path.exists(target_path):
                            os.unlink(target_path)
                        os.symlink(member.linkname, target_path)


def direct_unpack_zip(archive_path: str, dest_root: str, locations: list[dict[str, str]]) -> None:
    """Directly extracts matching members from a zip archive to the destination build tree without intermediate copies."""
    with zipfile.ZipFile(archive_path, 'r') as zf:
        if not locations:
            names = zf.namelist()
            locations = resolve_heuristic_locations(names)
            if locations:
                logging.info(" Auto-detected unpack locations: %s", locations)
            else:
                logging.warning(" No unpack rules specified and no standard SourceMod directories detected in archive.")
                return

        abs_dest_root = os.path.abspath(dest_root)

        for loc in locations:
            src_rule = str(loc.get('source', ''))
            dest_rule = str(loc.get('dest', ''))

            for member in zf.infolist():
                target_rel = _map_entry_target(member.filename, src_rule, dest_rule)
                if target_rel is None:
                    continue

                target_path = os.path.abspath(os.path.join(dest_root, target_rel))
                if target_path != abs_dest_root and not target_path.startswith(abs_dest_root + os.sep):
                    raise SkError(f"Attempted Path Traversal in Zip File: {member.filename}")

                norm_name = member.filename.replace('\\', '/').strip()
                if member.is_dir() or norm_name.endswith('/'):
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zf.open(member, 'r') as src_f, open(target_path, "wb") as out_f:
                        shutil.copyfileobj(src_f, out_f, length=64 * 1024)

                    perms = (member.external_attr >> 16) & 0o777
                    if perms & 0o111:
                        with contextlib.suppress(OSError):
                            os.chmod(target_path, os.stat(target_path).st_mode | 0o755)


def extract_and_copy(drvcls: Any, locations: list[dict[str, str]], mgr: FileManager, tmp: FileManager | None = None) -> None:
    """Extracts files from driver source and copies them into the target build tree."""
    from sourceknight.drivers import GitDriver

    # Apply heuristic auto-unpacking if no unpack locations were explicitly provided
    if not locations:
        if isinstance(drvcls, GitDriver):
            state = getattr(drvcls.ctx, "state", None)
            dep_state = state.dependencies.get(drvcls.model.name, {}) if state else {}
            loc = dep_state.get('location', drvcls.model.params.get('location', f".sourceknight/cache/{drvcls.model.name}"))
            base_search = os.path.normpath(os.path.join(drvcls.ctx.path, str(loc)))
        elif tmp is not None:
            base_search = tmp.path
        else:
            base_search = ""
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
            state = getattr(drvcls.ctx, "state", None)
            dep_state = state.dependencies.get(drvcls.model.name, {}) if state else {}
            loc = dep_state.get('location', drvcls.model.params.get('location', f".sourceknight/cache/{drvcls.model.name}"))
            src = os.path.normpath(os.path.join(drvcls.ctx.path, str(loc), src_entry))
        elif tmp is not None:
            src = os.path.normpath(os.path.join(tmp.path, src_entry))
        else:
            continue
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