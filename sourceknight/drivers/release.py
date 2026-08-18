import fnmatch
import logging
import os
import platform
import re
import tarfile
import urllib.parse
import zipfile
from typing import TYPE_CHECKING, Any, Optional

import requests

from sourceknight.errors import SkError
from sourceknight.utils import FileManager, extract_and_copy

from .base import basedriver

if TYPE_CHECKING:
    from sourceknight.dependencies import Dependency


class ReleaseDriver(basedriver):
    """
    Downloads and extracts pre-built release archives from Git hosting platforms
    (GitHub, GitLab, Gitea, Forgejo, or direct archive URLs).
    """

    def __init__(self, ctx: Any, model: Any) -> None:
        super().__init__(ctx, model)

    def _get_platform_pattern(self) -> str:
        """Returns default platform matching pattern if none is provided."""
        custom_pattern = self.model.params.get("asset_pattern")
        if custom_pattern:
            return str(custom_pattern)

        system = platform.system().lower()
        patterns = {
            "windows": "*win*.zip;*windows*.zip;*.zip",
            "linux": "*linux*.tar.gz;*linux*.zip;*.tar.gz;*.zip",
            "darwin": "*mac*.tar.gz;*darwin*.tar.gz;*mac*.zip;*.zip",
        }
        return patterns.get(system, "*.zip;*.tar.gz")

    def _match_asset(self, asset_names: list[str], patterns: str) -> str | None:
        """Finds the best matching asset name based on pattern list."""
        for pattern in patterns.split(";"):
            pattern = pattern.strip()
            for name in asset_names:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    return name
        return asset_names[0] if asset_names else None

    def _resolve_github_asset_url(self, repo: str, version: str) -> tuple[str, str]:
        """Resolves asset download URL from GitHub Releases API."""
        # Clean repo string: e.g. "https://github.com/owner/repo" -> "owner/repo"
        repo_clean = re.sub(r"^https?://github\.com/", "", repo).rstrip("/").removesuffix(".git")
        parts = repo_clean.split("/")
        if len(parts) != 2:
            raise SkError(f"Invalid GitHub repository identifier '{repo}' for release driver")

        owner, repo_name = parts
        if not version or version.lower() == "latest":
            api_url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest"
        else:
            tag = version if version.startswith("v") else f"v{version}"
            api_url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{tag}"

        headers = {"User-Agent": "SourceKnight-Build-System"}
        github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        req = requests.get(api_url, headers=headers)
        if req.status_code == 404 and version and not version.startswith("v"):
            # Try exact tag name without 'v' prefix
            api_url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{version}"
            req = requests.get(api_url, headers=headers)

        req.raise_for_status()
        data = req.json()

        assets = data.get("assets", [])
        if not assets:
            raise SkError(f"No release assets found in GitHub release for '{repo}' ({version})")

        asset_map = {a["name"]: a["browser_download_url"] for a in assets}
        pattern = self._get_platform_pattern()
        matched_name = self._match_asset(list(asset_map.keys()), pattern)

        if not matched_name or matched_name not in asset_map:
            raise SkError(
                f"No asset matching pattern '{pattern}' found among: {list(asset_map.keys())}"
            )

        resolved_tag = data.get("tag_name", version)
        return asset_map[matched_name], resolved_tag

    def _resolve_gitlab_asset_url(self, repo: str, version: str) -> tuple[str, str]:
        """Resolves asset download URL from GitLab Releases API."""
        parsed = urllib.parse.urlparse(repo)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.strip("/").removesuffix(".git")
        encoded_path = urllib.parse.quote(path, safe="")

        tag = version if version and version.lower() != "latest" else ""
        if tag:
            api_url = f"{base_url}/api/v4/projects/{encoded_path}/releases/{tag}"
        else:
            api_url = f"{base_url}/api/v4/projects/{encoded_path}/releases"

        headers = {"User-Agent": "SourceKnight-Build-System"}
        gitlab_token = os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN")
        if gitlab_token:
            headers["PRIVATE-TOKEN"] = gitlab_token

        req = requests.get(api_url, headers=headers)
        req.raise_for_status()
        data = req.json()
        release_data = data[0] if isinstance(data, list) and len(data) else data
        if not isinstance(release_data, dict):
            raise SkError(f"Unexpected response format from GitLab release API for '{repo}'")

        assets_dict = release_data.get("assets", {})
        assets = assets_dict.get("links", []) if isinstance(assets_dict, dict) else []
        if not assets:
            raise SkError(f"No asset links found in GitLab release for '{repo}'")

        asset_map = {a["name"]: a["url"] for a in assets}
        pattern = self._get_platform_pattern()
        matched_name = self._match_asset(list(asset_map.keys()), pattern)

        if not matched_name or matched_name not in asset_map:
            raise SkError(f"No asset matching pattern '{pattern}' in GitLab release for '{repo}'")

        return asset_map[matched_name], str(release_data.get("tag_name", version))

    def _resolve_asset_url(self) -> tuple[str, str]:
        """Determines the target download URL and resolved release tag."""
        repo = str(self.model.params.get("repo", self.model.params.get("location", "")))
        version = str(self.model.version or "latest")

        if "gitlab.com" in repo:
            return self._resolve_gitlab_asset_url(repo, version)
        elif "github.com" in repo or ("/" in repo and not repo.startswith("http")):
            return self._resolve_github_asset_url(repo, version)
        elif repo.startswith("http") and (repo.endswith(".zip") or repo.endswith(".tar.gz")):
            return repo, version
        else:
            # Default to GitHub resolution
            return self._resolve_github_asset_url(repo, version)

    def check_update(self, current: Optional["Dependency"]) -> bool:
        if current is None:
            return True
        if self.model.version is None or self.model.version.lower() == "latest":
            return True
        return str(self.model.version) != str(current.version)

    def update(self, mgr: FileManager) -> None:
        download_url, resolved_version = self._resolve_asset_url()
        logging.info(" Downloading release asset %s (%s)...", self.model.name, resolved_version)
        local_archive = mgr.acquire(download_url)
        self.ctx.state.update(
            dependencies={
                self.model.name: self.model.state(
                    driver="release",
                    file=os.path.basename(local_archive),
                    resolved_version=resolved_version,
                )
            }
        )

    def unpack(self, mgr: FileManager, locations: list[dict[str, str]]) -> None:
        name = str(self.model.name or "")
        state = self.ctx.state.dependencies.get(name, {})
        with FileManager(self.ctx, "cache") as fmgr:
            archive_path = os.path.join(fmgr.path, state.get("file", ""))

            with FileManager(self.ctx, "tmp") as tmp:
                if zipfile.is_zipfile(archive_path):
                    with zipfile.ZipFile(archive_path, "r") as zf:
                        zf.extractall(tmp.path)
                elif tarfile.is_tarfile(archive_path):
                    with tarfile.open(archive_path, "r:*") as tf:
                        tf.extractall(tmp.path)
                else:
                    raise SkError(f"Unsupported archive format for release dependency '{self.model.name}'")

                extract_and_copy(self, locations, mgr, tmp)

        self.ctx.state.update(
            build={
                self.model.name: self.model.state(
                    driver="release",
                    version=state.get("resolved_version", self.model.version),
                )
            }
        )
