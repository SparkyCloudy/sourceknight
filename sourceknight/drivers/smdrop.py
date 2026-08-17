import contextlib
import logging
import os
import platform
import re
import tarfile
import uuid
import zipfile
from typing import Any

import requests

from ..errors import SkError
from ..utils import FileManager, extract_and_copy, tar_safe_extract
from .base import basedriver


class SmdropDriver(basedriver):
    """Driver for resolving and downloading SourceMod builds from AlliedModders smdrop."""

    BASE_URL = "https://sm.alliedmods.net/smdrop"

    def __init__(self, ctx: Any, model: Any) -> None:
        super().__init__(ctx, model)
        self._cached_resolved_url: str | None = None

    def _get_platform_info(self) -> tuple[str, str]:
        """Returns the platform string and archive extension."""
        sys_name = platform.system().lower()
        if sys_name == "windows":
            return "windows", ".zip"
        return "linux", ".tar.gz"


    def _resolve_url(self) -> str:
        """Resolves the shorthand version or branch to a direct download URL."""
        raw_version = str(self.model.version or "1.12.x").strip()

        # Extract major.minor branch, e.g., '1.12.x' -> '1.12', '1.11' -> '1.11'
        match = re.match(r"^(\d+\.\d+)", raw_version)
        if not match:
            raise SkError(f"Invalid smdrop version format: '{raw_version}'. Expected format like '1.12' or '1.12.x'")

        branch = match.group(1)
        plat_str, ext = self._get_platform_info()

        # If full artifact specified, construct directly
        if raw_version.endswith((".tar.gz", ".zip")):
            return f"{self.BASE_URL}/{branch}/{raw_version}"

        # Otherwise query the AlliedModders latest pointer
        latest_pointer_url = f"{self.BASE_URL}/{branch}/sourcemod-latest-{plat_str}"
        logging.info(" Resolving smdrop version via %s...", latest_pointer_url)

        try:
            resp = requests.get(latest_pointer_url, timeout=15)
            resp.raise_for_status()
            filename = resp.text.strip()
            if not filename:
                raise SkError(f"Empty response received from {latest_pointer_url}")
            return f"{self.BASE_URL}/{branch}/{filename}"
        except requests.RequestException as e:
            raise SkError(f"Failed to resolve SourceMod build from smdrop ({latest_pointer_url}): {e}") from e

    def check_update(self, current: Any | None) -> bool:
        if current is None or current.version is None or self.model.version is None:
            return True
        if current.version != self.model.version:
            return True
        return not current.params.get('location') or not os.path.exists(os.path.join(self.ctx.path, current.params['location']))

    def cleanup(self) -> None:
        loc = self.model.params.get('location')
        if loc:
            full_path = os.path.join(self.ctx.path, loc)
            if os.path.isfile(full_path):
                with contextlib.suppress(OSError):
                    os.unlink(full_path)


    def update(self, mgr: FileManager) -> None:
        download_url = self._resolve_url()
        path = mgr.acquire(download_url)
        mgr.release(path)

        self.ctx.state.update(dependencies={
            self.model.name: self.model.state(
                location=os.path.relpath(path, self.ctx.path),
                driver='smdrop',
                resolved_url=download_url
            )
        })

    def unpack(self, mgr: FileManager, locations: list[dict[str, str]]) -> None:
        archive_rel = self.model.params.get('location')
        if not archive_rel:
            raise SkError(f"No archive location found for dependency {self.model.name}")

        archive_path = os.path.join(self.ctx.path, str(archive_rel))

        with FileManager(self.ctx, uuid.uuid4().hex, True) as tmp:
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    logging.info(" Unpacking zip archive...")
                    tmp_abs = os.path.abspath(tmp.path)
                    for member in zip_ref.namelist():
                        member_path = os.path.abspath(os.path.join(tmp.path, member))
                        if not member_path.startswith(tmp_abs):
                            raise SkError("Attempted path traversal in zip file")
                    zip_ref.extractall(tmp.path)
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path) as tar:
                    logging.info(" Unpacking tar archive...")
                    tar_safe_extract(tar, tmp.path)
            else:
                raise SkError(f"Unknown archive format for {archive_path}")

            extract_and_copy(self, locations, mgr, tmp)
