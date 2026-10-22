"""Package readable example plugins as individual release assets. Python 3.12+, standard library only."""

import argparse
from pathlib import Path
import re
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build_examples(source: Path, destination: Path) -> list[Path]:
    """Package only manifests, READMEs and declared modules; never import example code."""
    packages: list[tuple[Path, list[Path]]] = []
    for folder in sorted(source.iterdir()):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name == "__pycache__":
            continue
        manifest = folder / "videoforge-plugin.toml"
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        pid, version, module = (data.get(key) for key in ("id", "version", "module"))
        if pid != folder.name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", folder.name):
            raise ValueError(f"{folder}: id must match its folder name and be a valid plugin id")
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version):
            raise ValueError(f"{folder}: version must be non-empty and safe for an asset filename")
        if not isinstance(module, str) or not module.isidentifier():
            raise ValueError(f"{folder}: module must be a Python module name")
        if (
            not isinstance(data.get("name"), str)
            or not data["name"].strip()
            or type(data.get("api_version")) is not int
            or data["api_version"] < 1
        ):
            raise ValueError(f"{folder}: name and api_version are required for installable ZIPs")
        code = folder / f"{module}.py"
        if code.is_file():
            files = [code]
        else:
            package = folder / module
            if not (package / "__init__.py").is_file():
                raise ValueError(f"{folder}: declared module is missing")
            files = sorted(p for p in package.rglob("*") if p.is_file() and p.suffix == ".py")
        files = [folder / "README.md", manifest, *files]
        # Reject links/junctions and missing files before writing any archives.
        for path in [folder, *files]:
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(source.resolve()):
                raise ValueError(f"{path}: example files must stay inside the examples directory")
            if path != folder and not path.is_file():
                raise ValueError(f"{path}: required example file is missing")
        packages.append((destination / f"VideoForge-plugin-{pid}-{version}.zip", files))
    if not packages:
        raise ValueError(f"No example plugins found in {source}")
    destination.mkdir(parents=True, exist_ok=True)
    assets = []
    for target, files in packages:
        folder = files[0].parent
        temporary = target.with_suffix(".zip.tmp")
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in files:
                    # Avoid host-specific timestamps, file modes and checkout line endings.
                    entry = zipfile.ZipInfo(path.relative_to(folder).as_posix(), (2020, 1, 1, 0, 0, 0))
                    entry.create_system = 3
                    entry.external_attr = 0o100644 << 16
                    archive.writestr(
                        entry, path.read_text(encoding="utf-8").encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED
                    )
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        assets.append(target)
    return assets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "plugin-examples")
    args = parser.parse_args()
    for asset in build_examples(ROOT / "examples" / "plugins", args.output_dir):
        print(asset)


if __name__ == "__main__":
    main()
