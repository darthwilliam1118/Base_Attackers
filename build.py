"""PyInstaller build script."""
import subprocess
import sys

if __name__ == "__main__":
    subprocess.run(
        [sys.executable, "-m", "PyInstaller",
         "base_attackers.spec", "--noconfirm"],
        check=True,
    )
