"""Build a single-file Windows executable with PyInstaller."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
ASCII_EXE = DIST / "QimingPPT.exe"
CHINESE_EXE = DIST / "启明PPT.exe"


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "qiming.spec",
    ]
    print("Building 启明 PPT ...")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        print("Build failed.")
        return result.returncode
    if not ASCII_EXE.exists():
        print(f"Expected executable not found: {ASCII_EXE}")
        return 1
    shutil.copy2(ASCII_EXE, CHINESE_EXE)
    for name in ("README.md", "THIRD_PARTY_NOTICES.md", "LICENSE"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, DIST / name)
    start_here = ROOT / "docs" / "先看这里.txt"
    if start_here.exists():
        shutil.copy2(start_here, DIST / "先看这里.txt")
    size = CHINESE_EXE.stat().st_size / 1024 / 1024
    print(f"\nDone: {CHINESE_EXE}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
