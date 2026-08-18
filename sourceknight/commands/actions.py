import concurrent.futures
import logging
import os
import shutil
from typing import TYPE_CHECKING, Any

from sourceknight import DependencyManager
from sourceknight.utils import FileManager

if TYPE_CHECKING:
    from sourceknight.context import Context


def do_update(context: "Context", force: bool = False) -> None:
    """Logic for the update command."""
    context.ensure_working_directory_exists()
    dmgr = DependencyManager(context)
    deps: list[dict[str, Any]] = context.defs.get("dependencies", [])

    if not deps:
        return

    with FileManager(context, "cache") as fmgr:
        if len(deps) > 1:
            max_workers = min(8, len(deps))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(dmgr.update, dep, fmgr, force)
                    for dep in deps
                ]
                for future in concurrent.futures.as_completed(futures):
                    future.result()
        else:
            for dep in deps:
                dmgr.update(dep, fmgr, force)


def do_unpack(context: "Context", force: bool = False, clean: bool = False) -> None:
    """Logic for the unpack command."""
    context.ensure_working_directory_exists()
    if clean:
        build_dir = os.path.join(context.path, ".sourceknight", "build")
        logging.info("Deleting existing build directory (%s)...", build_dir)
        shutil.rmtree(build_dir, ignore_errors=True)
        context.state.clear_build_state()

    dmgr = DependencyManager(context)
    deps: list[dict[str, Any]] = [
        dep for dep in context.defs.get("dependencies", [])
        if dep.get("name") and dep.get("name") in context.state.dependencies
    ]

    if not deps:
        return

    with FileManager(context, "build", True) as fmgr:
        if len(deps) > 1:
            max_workers = min(8, len(deps))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        dmgr.unpack,
                        context.state.dependencies[dep["name"]],
                        dep.get("unpack", []),
                        fmgr,
                        force,
                    )
                    for dep in deps
                ]
                for future in concurrent.futures.as_completed(futures):
                    future.result()
        else:
            for dep in deps:
                dmgr.unpack(
                    context.state.dependencies[dep["name"]],
                    dep.get("unpack", []),
                    fmgr,
                    force,
                )
        fmgr.release_dir()


def do_package(
    context: "Context",
    output_dir: str | None = None,
    create_zip: bool = False,
    create_tar: bool = False,
    clean: bool = True,
) -> str:
    """Logic for the package command."""
    from sourceknight.packager import Packager

    packager = Packager(context)
    return packager.package(
        output_dir=output_dir,
        create_zip=create_zip,
        create_tar=create_tar,
        clean=clean,
    )

