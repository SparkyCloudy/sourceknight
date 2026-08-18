import os
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

import yaml

from sourceknight.commands.build import Build
from sourceknight.commands.package import Package
from sourceknight.context import Context
from sourceknight.errors import SkError
from sourceknight.packager import Packager


class TestPackager(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_file(self, rel_path: str, content: str = "test content") -> str:
        full_path = os.path.join(self.test_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return full_path

    def _write_manifest(self, manifest_data: dict) -> None:
        manifest_path = os.path.join(self.test_dir, "sourceknight.yaml")
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest_data, f)

    def test_zero_config_auto_discovery(self) -> None:
        """Tests that standard SourceMod asset folders and compiled plugins are automatically discovered and packaged."""
        self._write_manifest({
            "project": {
                "sourceknight": 0.7,
                "name": "myplugin",
                "output": "/addons/sourcemod/plugins",
                "targets": ["myplugin", "myplugin_admin"],
            }
        })

        # Create compiled plugins and asset directories
        self._create_file("addons/sourcemod/plugins/myplugin.smx", "binary1")
        self._create_file("addons/sourcemod/plugins/myplugin_admin.smx", "binary2")
        self._create_file("addons/sourcemod/translations/myplugin.phrases.txt", "phrases")
        self._create_file("addons/sourcemod/configs/myplugin.cfg", "config")
        self._create_file("cfg/sourcemod/myplugin.cfg", "cvar config")
        self._create_file("sound/myplugin/alert.mp3", "sound data")

        with Context(self.test_dir) as ctx:
            packager = Packager(ctx)
            pkg_dir = packager.package()

        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "addons", "sourcemod", "plugins", "myplugin.smx")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "addons", "sourcemod", "plugins", "myplugin_admin.smx")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "addons", "sourcemod", "translations", "myplugin.phrases.txt")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "addons", "sourcemod", "configs", "myplugin.cfg")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "cfg", "sourcemod", "myplugin.cfg")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "sound", "myplugin", "alert.mp3")))

    def test_src_prefix_and_common_folder_support(self) -> None:
        """Tests projects structured with src/ and common/ directories."""
        self._write_manifest({
            "project": {
                "sourceknight": 0.7,
                "name": "zombie_test",
                "root": "/src",
                "output": "/src/addons/sourcemod/plugins",
                "targets": ["zombiereloaded"],
            }
        })

        self._create_file("src/addons/sourcemod/plugins/zombiereloaded.smx", "zr binary")
        self._create_file("src/addons/sourcemod/translations/zr.phrases.txt", "zr phrases")
        self._create_file("common/cfg/sourcemod/zombiereloaded/zr.cfg", "zr cfg")
        self._create_file("common/models/player/custom.mdl", "model file")

        with Context(self.test_dir) as ctx:
            packager = Packager(ctx)
            pkg_dir = packager.package()

        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "addons", "sourcemod", "plugins", "zombiereloaded.smx")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "addons", "sourcemod", "translations", "zr.phrases.txt")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "cfg", "sourcemod", "zombiereloaded", "zr.cfg")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "models", "player", "custom.mdl")))

    def test_explicit_includes_mapping(self) -> None:
        """Tests explicit include mappings with custom sources and destinations."""
        self._write_manifest({
            "project": {
                "sourceknight": 0.7,
                "name": "explicit_test",
                "output": "/addons/sourcemod/plugins",
                "targets": ["explicit_plugin"],
            },
            "package": {
                "output": "dist/my_package",
                "include": [
                    "configs/custom.json",
                    {"source": "raw_sounds", "dest": "sound/custom"},
                    {"source": "shared_assets", "dest": "."},
                ]
            }
        })

        self._create_file("addons/sourcemod/plugins/explicit_plugin.smx", "plugin binary")
        self._create_file("configs/custom.json", "json config")
        self._create_file("raw_sounds/ping.wav", "audio")
        self._create_file("shared_assets/info.txt", "info")

        with Context(self.test_dir) as ctx:
            packager = Packager(ctx)
            pkg_dir = packager.package()

        self.assertEqual(pkg_dir, os.path.abspath(os.path.join(self.test_dir, "dist", "my_package")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "addons", "sourcemod", "plugins", "explicit_plugin.smx")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "configs", "custom.json")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "sound", "custom", "ping.wav")))
        self.assertTrue(os.path.exists(os.path.join(pkg_dir, "info.txt")))

    def test_archive_creation_zip_and_tar(self) -> None:
        """Tests generating .zip and .tar.gz archives."""
        self._write_manifest({
            "project": {
                "sourceknight": 0.7,
                "name": "archive_test",
                "output": "/plugins",
                "targets": ["test_target"],
            },
            "package": {
                "output": "dist/package",
                "archive": "both",
                "archive_name": "archive_test-1.0.0",
            }
        })

        self._create_file("plugins/test_target.smx", "binary")
        self._create_file("cfg/test.cfg", "cfg")

        with Context(self.test_dir) as ctx:
            packager = Packager(ctx)
            packager.package()

        zip_path = os.path.join(self.test_dir, "dist", "archive_test-1.0.0.zip")
        tar_path = os.path.join(self.test_dir, "dist", "archive_test-1.0.0.tar.gz")

        self.assertTrue(os.path.exists(zip_path))
        self.assertTrue(os.path.exists(tar_path))

        # Check zip contents
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("addons/sourcemod/plugins/test_target.smx", [n.replace("\\", "/") for n in namelist])
            self.assertIn("cfg/test.cfg", [n.replace("\\", "/") for n in namelist])

        # Check tar contents
        with tarfile.open(tar_path, "r:gz") as tf:
            names = tf.getnames()
            self.assertIn("addons/sourcemod/plugins/test_target.smx", [n.replace("\\", "/") for n in names])
            self.assertIn("cfg/test.cfg", [n.replace("\\", "/") for n in names])

    def test_path_traversal_detection(self) -> None:
        """Ensures attempted path traversal in destination raises SkError."""
        self._write_manifest({
            "project": {
                "sourceknight": 0.7,
                "name": "traversal_test",
            },
            "package": {
                "include": [
                    {"source": "cfg", "dest": "../../escape"}
                ]
            }
        })
        self._create_file("cfg/test.cfg", "test")

        with Context(self.test_dir) as ctx:
            packager = Packager(ctx)
            with self.assertRaises(SkError):
                packager.package()

    def test_cli_package_command(self) -> None:
        """Tests invoking Package CLI command."""
        self._write_manifest({
            "project": {
                "sourceknight": 0.7,
                "name": "cli_pkg_test",
                "output": "/plugins",
                "targets": ["test_plugin"],
            }
        })
        self._create_file("plugins/test_plugin.smx", "smx")

        with Context(self.test_dir) as ctx:
            cmd = Package(ctx)
            args = MagicMock()
            args.output = os.path.join(self.test_dir, "custom_dist")
            args.zip = False
            args.tar = False
            args.clean = True
            cmd(args)

        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "custom_dist", "addons", "sourcemod", "plugins", "test_plugin.smx")))

    @patch("sourceknight.commands.build.do_update")
    @patch("sourceknight.commands.build.do_unpack")
    @patch("sourceknight.commands.build.Compile")
    def test_cli_build_with_package_flag(self, mock_compile: MagicMock, mock_unpack: MagicMock, mock_update: MagicMock) -> None:
        """Tests sourceknight build --package executes do_package."""
        self._write_manifest({
            "project": {
                "sourceknight": 0.7,
                "name": "build_pkg_test",
                "output": "/plugins",
                "targets": ["test_plugin"],
            }
        })
        self._create_file("plugins/test_plugin.smx", "smx")

        with Context(self.test_dir) as ctx:
            cmd = Build(ctx)
            args = MagicMock()
            args.force = False
            args.clean = False
            args.package = True
            args.package_output = os.path.join(self.test_dir, "build_out_pkg")
            args.zip = False
            args.tar = False
            cmd(args)

        mock_update.assert_called_once()
        mock_unpack.assert_called_once()
        mock_compile.return_value.assert_called_once()
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "build_out_pkg", "addons", "sourcemod", "plugins", "test_plugin.smx")))
