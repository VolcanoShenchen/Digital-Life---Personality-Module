"""The release must be complete and reject altered or unexpected members."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts import build_plugin
from tests.support import ROOT


class PackageTests(unittest.TestCase):
    def test_build_verifies_complete_allowlist_and_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_plugin.build_archive(ROOT, Path(directory))
            self.assertEqual(build_plugin.verify_archive(path), "0.1.0")
            with ZipFile(path) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), len(build_plugin.RELEASE_FILES))
                self.assertTrue(
                    all(name.startswith(build_plugin.PLUGIN_ID + "/") for name in names)
                )
                self.assertFalse(any(".git/" in name or "__pycache__" in name for name in names))
            recorded = path.with_suffix(".zip.sha256").read_text("utf-8").split()[0]
            self.assertEqual(recorded, hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(build_plugin.PackageError):
                build_plugin.build_archive(ROOT, Path(directory))

    def test_incomplete_package_is_rejected(self):
        payload = {name: (ROOT / name).read_bytes() for name in build_plugin.RELEASE_FILES}
        del payload["main.py"]
        with self.assertRaises(build_plugin.PackageError):
            build_plugin.check_payload(payload)

    def test_changed_versions_or_enabled_defaults_are_rejected(self):
        payload = {name: (ROOT / name).read_bytes() for name in build_plugin.RELEASE_FILES}
        changed = payload.copy()
        changed["runtime.py"] = changed["runtime.py"].replace(
            b'VERSION = "0.1.0"', b'VERSION = "9.9.9"'
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
        payload = {name: (ROOT / name).read_bytes() for name in build_plugin.RELEASE_FILES}
        payload["data/chat.json"] = b"{}"
        with self.assertRaises(build_plugin.PackageError):
            build_plugin.check_payload(payload)


if __name__ == "__main__":
    unittest.main()
