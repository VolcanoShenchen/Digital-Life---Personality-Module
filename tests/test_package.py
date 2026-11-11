"""The release must be complete and reject altered or unexpected members."""

import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts import build_plugin
from tests.support import ROOT


class PackageTests(unittest.TestCase):
    def payload(self):
        return {name: (ROOT / name).read_bytes() for name in build_plugin.release_files()}

    def current_version(self):
        return re.search(r'VERSION = "([0-9.]+)"', (ROOT / "runtime.py").read_text("utf-8")).group(
            1
        )

    def test_build_verifies_complete_allowlist_and_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_plugin.build_archive(ROOT, Path(directory))
            self.assertEqual(build_plugin.verify_archive(path), self.current_version())
            with ZipFile(path) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), len(build_plugin.release_files()))
                self.assertTrue(
                    all(name.startswith(build_plugin.PLUGIN_ID + "/") for name in names)
                )
                self.assertTrue(any("/views/settings/assets/" in name for name in names))
                self.assertFalse(any(".git/" in name or "__pycache__" in name for name in names))
            recorded = path.with_suffix(".zip.sha256").read_text("utf-8").split()[0]
            self.assertEqual(recorded, hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(build_plugin.PackageError):
                build_plugin.build_archive(ROOT, Path(directory))

    def test_unbuilt_frontend_entry_is_rejected(self):
        payload = self.payload()
        payload["views/settings/index.html"] = b'<script type="module" src="/src/main.js"></script>'
        with self.assertRaises(build_plugin.PackageError):
            build_plugin.check_payload(payload)

    def test_root_absolute_view_assets_are_rejected(self):
        # AstrBot serves views under a tokenised subpath, so "/assets/..." 404s.
        payload = self.payload()
        payload["views/settings/index.html"] = (
            b'<script type="module" src="/assets/index-abc.js"></script>'
        )
        with self.assertRaises(build_plugin.PackageError):
            build_plugin.check_payload(payload)

    def test_relative_view_assets_are_accepted(self):
        payload = self.payload()
        payload["views/settings/index.html"] = (
            b'<script type="module" src="./assets/index-abc.js"></script>'
            b'<link rel="stylesheet" href="./assets/index-abc.css">'
        )
        self.assertEqual(build_plugin.check_payload(payload), self.current_version())

    def test_incomplete_package_is_rejected(self):
        payload = self.payload()
        del payload["main.py"]
        with self.assertRaises(build_plugin.PackageError):
            build_plugin.check_payload(payload)

    def test_changed_versions_or_enabled_defaults_are_rejected(self):
        payload = self.payload()
        changed = payload.copy()
        changed["runtime.py"] = re.sub(
            rb'VERSION = "[0-9.]+"', b'VERSION = "9.9.9"', changed["runtime.py"]
        )
        with self.assertRaises(build_plugin.PackageError):
            build_plugin.check_payload(changed)
        changed = payload.copy()
        changed["_conf_schema.json"] = changed["_conf_schema.json"].replace(
            b'"default": false', b'"default": true', 1
        )
        with self.assertRaises(build_plugin.PackageError):
            build_plugin.check_payload(changed)

    def test_unexpected_archive_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, member in enumerate(
                ("../secret", "/absolute/main.py", "other/main.py", "root\\main.py")
            ):
                archive_path = Path(directory) / f"bad-{index}.zip"
                with ZipFile(archive_path, "w") as archive:
                    archive.writestr(member, b"unexpected")
                with self.subTest(member=member), self.assertRaises(build_plugin.PackageError):
                    build_plugin.verify_archive(archive_path)

    def test_runtime_configuration_cannot_be_added_to_a_release(self):
        payload = self.payload()
        payload["data/chat.json"] = b"{}"
        with self.assertRaises(build_plugin.PackageError):
            build_plugin.check_payload(payload)


if __name__ == "__main__":
    unittest.main()
