"""Build and verify a complete AstrBot ZIP using an explicit file allowlist."""

import argparse
import ast
import hashlib
import json
import re
import tomllib
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "astrbot_plugin_digital_life_personality"
BASE_RELEASE_FILES = (
    "__init__.py",
    "main.py",
    "settings.py",
    "personality.py",
    "runtime.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "README.md",
    "CHANGELOG.md",
    "docs/INSTALL.md",
    "docs/VALIDATION.md",
    "docs/DESIGN_V0_1.md",
    "docs/ARCHITECTURE.md",
    "docs/ACCEPTANCE.md",
    "docs/PLAN.md",
    "docs/WEBUI.md",
    "docs/FIELD_MAPPING.md",
    "docs/IDENTITY_AUTHORITY.md",
    "CONTRIBUTING.md",
)


class PackageError(ValueError):
    pass


def view_files(root: Path = ROOT) -> tuple[str, ...]:
    """Collect the built view; asset names contain Vite content hashes."""
    folder = root / "views/settings"
    files = sorted(
        path.relative_to(root).as_posix() for path in folder.rglob("*") if path.is_file()
    )
    if "views/settings/index.html" not in files:
        raise PackageError("Build the Vue view before packaging")
    if not any(name.startswith("views/settings/assets/") for name in files):
        raise PackageError("Vue view assets are missing")
    return tuple(files)


def release_files(root: Path = ROOT) -> tuple[str, ...]:
    return BASE_RELEASE_FILES + view_files(root)


def check_payload(payload: dict[str, bytes]) -> str:
    if set(payload) != set(release_files()):
        raise PackageError("Archive must contain exactly the complete release allowlist")
    for name, content in payload.items():
        if not content:
            raise PackageError(f"Empty release file: {name}")
        if name.endswith(".py"):
            compile(content, name, "exec")
    if b"src/main.js" in payload["views/settings/index.html"]:
        raise PackageError("Unbuilt frontend entry leaked into the release")
    view_html = payload["views/settings/index.html"].decode("utf-8")
    for attribute in re.findall(r'(?:src|href)="([^"]+)"', view_html):
        if attribute.startswith("/"):
            raise PackageError("View assets must use relative URLs for the dashboard iframe path")
    metadata = payload["metadata.yaml"].decode("utf-8")
    versions = re.findall(r"^version: ([0-9]+\.[0-9]+\.[0-9]+)$", metadata, re.MULTILINE)
    if len(versions) != 1:
        raise PackageError("Missing or ambiguous metadata version")
    if f"name: {PLUGIN_ID}\n" not in metadata:
        raise PackageError("Unexpected plugin ID")
    version = versions[0]
    tree = ast.parse(payload["runtime.py"].decode("utf-8"))
    runtime_versions = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
    ]
    if runtime_versions != [version]:
        raise PackageError("Runtime version and metadata version differ")
    schema = json.loads(payload["_conf_schema.json"])
    if schema.get("enabled", {}).get("default") is not False:
        raise PackageError("A release must default to disabled")
    if schema.get("allowed_sessions", {}).get("default") != []:
        raise PackageError("Session allowlist must default to empty")
    if schema.get("allowed_bot_ids", {}).get("default") != []:
        raise PackageError("Bot allowlist must default to empty")
    return version


def verify_archive(path: Path) -> str:
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise PackageError("Duplicate archive member")
        payload = {}
        for name in names:
            parts = PurePosixPath(name).parts
            if (
                "\\" in name
                or name.startswith("/")
                or len(parts) < 2
                or parts[0] != PLUGIN_ID
                or ".." in parts
                or archive.getinfo(name).is_dir()
            ):
                raise PackageError("Unexpected archive path")
            payload["/".join(parts[1:])] = archive.read(name)
        if archive.testzip():
            raise PackageError("Archive CRC check failed")
        return check_payload(payload)


def build_archive(root: Path, output: Path) -> Path:
    payload = {}
    for name in release_files(root):
        file_path = root / name
        if not file_path.is_file():
            raise PackageError(f"Missing release file: {name}")
        payload[name] = file_path.read_bytes()
    version = check_payload(payload)
    project = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
    if project["project"]["version"] != version:
        raise PackageError("Project version and metadata version differ")
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"{PLUGIN_ID}-v{version}.zip"
    if target.exists():
        raise PackageError("Output already exists; use a fresh output directory")
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            archive.writestr(f"{PLUGIN_ID}/{name}", content)
    verify_archive(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", "utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, help="Verify an existing complete ZIP")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    if args.verify:
        version = verify_archive(args.verify)
        print(f"Verified complete archive: v{version}")
    else:
        target = build_archive(ROOT, args.output)
        print(f"Built and verified: {target}")
        print(f"SHA-256: {target.with_suffix('.zip.sha256')}")


if __name__ == "__main__":
    main()
