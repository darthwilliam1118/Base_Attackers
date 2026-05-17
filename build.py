"""One-command build script: cleans previous output then runs PyInstaller."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def clean() -> None:
    for folder in ("dist", "build"):
        target = ROOT / folder
        if target.exists():
            shutil.rmtree(target)
            print(f"Removed {target}")


def build() -> None:
    spec = ROOT / "base_attackers.spec"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(spec),
            "--distpath",
            str(ROOT / "dist"),
            "--noconfirm",
        ],
        check=False,
    )
    if result.returncode != 0:
        print("\nBuild FAILED.")
        sys.exit(result.returncode)

    exe = ROOT / "dist" / "base_attackers.exe"
    if exe.exists():
        print(f"\nBuild succeeded: {exe}")
    else:
        print("\nBuild finished but exe not found — check PyInstaller output above.")


if __name__ == "__main__":
    clean()
    build()
