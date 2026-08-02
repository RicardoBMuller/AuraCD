from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text)
    if count == 0:
        raise RuntimeError(f"Padrão não encontrado em {path}: {pattern}")
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    version = (sys.argv[1] if len(sys.argv) > 1 else "2.6.0").strip().lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Use uma versão no formato X.Y.Z, por exemplo 2.6.0")

    major, minor, patch = (int(item) for item in version.split("."))
    replace(ROOT / "app.py", r'APP_VERSION = "[^"]+"', f'APP_VERSION = "{version}"')

    version_file = ROOT / "packaging" / "version_info.txt"
    text = version_file.read_text(encoding="utf-8")
    text = re.sub(r"filevers=\([^)]*\)", f"filevers=({major}, {minor}, {patch}, 0)", text)
    text = re.sub(r"prodvers=\([^)]*\)", f"prodvers=({major}, {minor}, {patch}, 0)", text)
    text = re.sub(r"StringStruct\('FileVersion', '[^']+'\)", f"StringStruct('FileVersion', '{version}')", text)
    text = re.sub(r"StringStruct\('ProductVersion', '[^']+'\)", f"StringStruct('ProductVersion', '{version}')", text)
    version_file.write_text(text, encoding="utf-8")

    print(f"Versão preparada: {version}")


if __name__ == "__main__":
    main()
