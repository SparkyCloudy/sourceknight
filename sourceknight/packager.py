import glob
import logging
import os
import shutil
import tarfile
import zipfile
from typing import TYPE_CHECKING, Any

from sourceknight.errors import SkError

if TYPE_CHECKING:
    from sourceknight.context import Context


STANDARD_ASSET_DIRS = [
    "addons/sourcemod/translations",
    "addons/sourcemod/configs",
    "addons/sourcemod/gamedata",
    "cfg",
    "sound",
    "models",
    "materials",
]


class Packager:
    """Handles automated and declarative packaging of compiled plugins and runtime assets."""

    def __init__(self, context: "Context") -> None:
        self.context = context
        self.package_defs: dict[str, Any] = context.defs.get("package") or getattr(context, "package_defs", {}) or {}

    def _get_abs_path(self, rel: str) -> str:
        clean = rel.replace("\\", "/").strip().lstrip("/")
        return os.path.abspath(os.path.join(self.context.path, clean))

    def _is_subpath(self, target: str, parent: str) -> bool:
        abs_target = os.path.abspath(target)
        abs_parent = os.path.abspath(parent)
        return abs_target == abs_parent or abs_target.startswith(abs_parent + os.sep)

    def _copy_item(self, src: str, dst: str, abs_dest_root: str) -> None:
        abs_dst = os.path.abspath(dst)
        if not self._is_subpath(abs_dst, abs_dest_root):
            raise SkError(f"Attempted Path Traversal in packaging: {dst}")

        if os.path.isdir(src):
            os.makedirs(abs_dst, exist_ok=True)
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(abs_dst, item)
                # Avoid recursively copying the destination folder if it resides inside source
                if self._is_subpath(abs_dest_root, s):
                    continue
                self._copy_item(s, d, abs_dest_root)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(abs_dst), exist_ok=True)
            shutil.copy2(src, abs_dst)

    def package(
        self,
        output_dir: str | None = None,
        create_zip: bool = False,
        create_tar: bool = False,
        clean: bool = True,
    ) -> str:
        """Packages the project according to manifest definitions and arguments."""
        # 1. Resolve output destination directory
        raw_output = output_dir or self.package_defs.get("output") or os.path.join(".sourceknight", "package")
        abs_dest_root = (
            os.path.abspath(raw_output)
            if os.path.isabs(raw_output)
            else os.path.abspath(os.path.join(self.context.path, raw_output))
        )

        # 2. Clean existing output directory if required
        if clean and os.path.exists(abs_dest_root):
            shutil.rmtree(abs_dest_root, ignore_errors=True)
        os.makedirs(abs_dest_root, exist_ok=True)

        logging.info("Packaging project into %s...", abs_dest_root)

        # 3. Copy compiled .smx target plugins
        self._pack_compiled_plugins(abs_dest_root)

        # 4. Process includes (explicit or auto-detected)
        includes = self.package_defs.get("include")
        if includes is not None:
            self._pack_explicit_includes(includes, abs_dest_root)
        else:
            self._pack_auto_discovery(abs_dest_root)

        # 5. Create compressed archives if requested
        archive_pref = self.package_defs.get("archive", False)
        should_zip = create_zip or archive_pref in ("zip", "both", True)
        should_tar = create_tar or archive_pref in ("tar", "tar.gz", "tgz", "both")

        if should_zip or should_tar:
            self._create_archives(abs_dest_root, should_zip, should_tar)

        return abs_dest_root

    def _pack_compiled_plugins(self, abs_dest_root: str) -> None:
        """Locates and copies compiled .smx target binaries into addons/sourcemod/plugins."""
        out_rel = self.context.defs.get("output", "/addons/sourcemod/plugins/").strip().lstrip("/")
        abs_output = os.path.abspath(os.path.join(self.context.path, out_rel))
        dest_plugins_dir = os.path.join(abs_dest_root, "addons", "sourcemod", "plugins")

        targets = self.context.defs.get("targets", [])
        if not targets and os.path.isdir(abs_output):
            # If no targets listed, copy all .smx from output directory
            for smx in glob.glob(os.path.join(abs_output, "*.smx")):
                self._copy_item(smx, os.path.join(dest_plugins_dir, os.path.basename(smx)), abs_dest_root)
        else:
            for target in targets:
                target_name = target if isinstance(target, str) else target.get("name", "")
                if not target_name:
                    continue
                smx_name = f"{target_name}.smx"
                src_smx = os.path.join(abs_output, smx_name)
                if os.path.exists(src_smx):
                    self._copy_item(src_smx, os.path.join(dest_plugins_dir, smx_name), abs_dest_root)
                else:
                    logging.warning("Compiled plugin binary not found: %s", src_smx)

    def _pack_explicit_includes(self, includes: list[Any], abs_dest_root: str) -> None:
        """Copies explicitly listed paths or mapping dictionaries to the package."""
        for item in includes:
            if isinstance(item, str):
                src_pattern = self._get_abs_path(item)
                matches = glob.glob(src_pattern)
                if not matches and os.path.exists(src_pattern):
                    matches = [src_pattern]

                for match in matches:
                    rel_to_proj = os.path.relpath(match, self.context.path)
                    dst = os.path.join(abs_dest_root, rel_to_proj)
                    self._copy_item(match, dst, abs_dest_root)
            elif isinstance(item, dict):
                src_rel = str(item.get("source", "")).strip().lstrip("/")
                dst_rel = str(item.get("dest", "")).strip().lstrip("/")

                src_pattern = self._get_abs_path(src_rel)
                matches = glob.glob(src_pattern)
                if not matches and os.path.exists(src_pattern):
                    matches = [src_pattern]

                for match in matches:
                    if dst_rel in ("", "."):
                        if os.path.isdir(match):
                            # Copy directory contents into dest root
                            for child in os.listdir(match):
                                self._copy_item(
                                    os.path.join(match, child),
                                    os.path.join(abs_dest_root, child),
                                    abs_dest_root,
                                )
                        else:
                            self._copy_item(
                                match,
                                os.path.join(abs_dest_root, os.path.basename(match)),
                                abs_dest_root,
                            )
                    else:
                        dst = os.path.join(abs_dest_root, dst_rel)
                        self._copy_item(match, dst, abs_dest_root)

    def _pack_auto_discovery(self, abs_dest_root: str) -> None:
        """Auto-detects standard SourceMod and game asset folders in the project tree."""
        # 1. Check standard directories directly in project root
        for asset_rel in STANDARD_ASSET_DIRS:
            abs_src = os.path.join(self.context.path, asset_rel)
            if os.path.exists(abs_src):
                dst = os.path.join(abs_dest_root, asset_rel)
                self._copy_item(abs_src, dst, abs_dest_root)

        # 2. Check if root contains src/ directory (e.g. src/addons/sourcemod/translations)
        src_root = os.path.join(self.context.path, "src")
        if os.path.isdir(src_root):
            for asset_rel in STANDARD_ASSET_DIRS:
                abs_src = os.path.join(src_root, asset_rel)
                if os.path.exists(abs_src):
                    dst = os.path.join(abs_dest_root, asset_rel)
                    self._copy_item(abs_src, dst, abs_dest_root)

        # 3. Check for common/ directory (frequently used in sourcemod repos)
        common_dir = os.path.join(self.context.path, "common")
        if os.path.isdir(common_dir):
            for item in os.listdir(common_dir):
                s = os.path.join(common_dir, item)
                d = os.path.join(abs_dest_root, item)
                self._copy_item(s, d, abs_dest_root)

    def _create_archives(self, abs_dest_root: str, make_zip: bool, make_tar: bool) -> None:
        """Builds .zip and/or .tar.gz archives from the packaged output directory."""
        proj_name = self.context.defs.get("name", "package")
        archive_base = self.package_defs.get("archive_name") or proj_name

        parent_dir = os.path.dirname(abs_dest_root)
        if not parent_dir or parent_dir == abs_dest_root:
            parent_dir = self.context.path

        if make_zip:
            zip_path = os.path.join(parent_dir, f"{archive_base}.zip")
            logging.info("Creating Zip archive: %s...", zip_path)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(abs_dest_root):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, abs_dest_root)
                        zf.write(full_path, arcname=rel_path)

        if make_tar:
            tar_path = os.path.join(parent_dir, f"{archive_base}.tar.gz")
            logging.info("Creating Tar.gz archive: %s...", tar_path)
            with tarfile.open(tar_path, "w:gz") as tf:
                for root, _, files in os.walk(abs_dest_root):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, abs_dest_root)
                        tf.add(full_path, arcname=rel_path)
