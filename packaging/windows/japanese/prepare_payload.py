"""Assemble the licensed native runtime for the single-EXE Japanese package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from public_binary import redact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--fonts", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--crt", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    binary = root / "target/release/photocraft.exe"
    stage = args.work / "payload"
    stage.mkdir()
    public_binary, redactions = redact(binary.read_bytes(), str(Path.home()))
    (stage / "photocraft.exe").write_bytes(public_binary)
    (stage / "photocraft.sha256").write_text(hashlib.sha256(public_binary).hexdigest() + "\n", encoding="utf-8")
    print(f"Anonymized native diagnostic prefixes: {redactions}")
    licenses = stage / "licenses"
    licenses.mkdir()
    for name in ("LICENSE-MIT", "LICENSE-APACHE", "NOTICE", "ATTRIBUTION.md"):
        shutil.copy2(root / name, licenses / name)
    with (licenses / "NOTICE").open("a", encoding="utf-8") as file:
        file.write("\nLocal Japanese edition: completed Japanese UI catalog, familiar image-editing terminology, and single-executable launcher.\n")
        file.write("Upstream: https://github.com/storytold/photocraft, version 0.20.1.\n")
    for path in (root / "assets/fonts").glob("OFL*.txt"):
        shutil.copy2(path, licenses / path.name)
    for directory in (root / "assets", root / "crates/ui-egui/src"):
        for path in directory.rglob("LICENSE*.txt"):
            relative = path.relative_to(root)
            shutil.copy2(path, licenses / ("PROJECT-" + "-".join(relative.parts)))
    for path in (args.fonts / "fonts").rglob("OFL.txt"):
        shutil.copy2(path, licenses / ("OFL-" + path.parent.name + ".txt"))
    shutil.copy2(args.fonts / "ATTRIBUTION.md", licenses / "CRAFT-FONTS-ATTRIBUTION.md")
    for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "concrt140.dll"):
        shutil.copy2(args.crt / name, stage / name)
    metadata = json.loads(args.metadata.read_text(encoding="utf-8-sig"))
    notices = []
    no_license_file = []
    for package in sorted(metadata["packages"], key=lambda p: (p["name"], p["version"])):
        if package.get("source") is None:
            continue
        header = f"{package['name']} {package['version']}\nLicense: {package.get('license') or 'see license text'}\n"
        if package.get("repository"):
            header += package["repository"] + "\n"
        base = Path(package["manifest_path"]).parent
        files = []
        # Git workspaces often keep the license at the repository root.
        for parent in (base, *list(base.parents)[:5]):
            files = [p for p in parent.iterdir() if p.is_file() and p.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT"))]
            if files or parent.name in ("registry", "checkouts"):
                break
        if package.get("license_file"):
            explicit = base / package["license_file"]
            if explicit.is_file() and explicit not in files:
                files.append(explicit)
        if not files:
            no_license_file.append(package["name"])
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(files))
        notices.append("=" * 72 + "\n" + header + "\n" + text + "\n")
    (licenses / "THIRD-PARTY-NOTICES.txt").write_text("\n".join(notices), encoding="utf-8")
    (licenses / "MICROSOFT-RUNTIME-NOTICE.txt").write_text(
        "Microsoft Visual C++ runtime libraries are included app-locally from the licensed Visual Studio Build Tools redistributable directory.\n"
        "Copyright Microsoft Corporation. All rights reserved.\n",
        encoding="utf-8",
    )
    payload = args.work / "photocraft-ja-payload.zip"
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage).as_posix())
    print(f"Payload files: {sum(p.is_file() for p in stage.rglob('*'))}")
    print(f"Payload bytes: {payload.stat().st_size}")
    print(f"Third-party packages: {len(notices)}; packages without standalone license file: {len(no_license_file)}")
    if no_license_file:
        print("SPDX-only entries: " + ", ".join(no_license_file))


if __name__ == "__main__":
    main()
