"""Allow running as python -m base_attackers."""

import sys
from pathlib import Path

import pyglet
from agf.paths import set_project_root

set_project_root(Path(__file__).parents[3])  # src/<pkg>/__main__.py → project root

if sys.platform == "win32":
    pyglet.options["win32_gdi_font"] = (
        True  # DirectWrite can't find fonts with weight names like "Thin"
    )
    pyglet.options["audio"] = ("xaudio2", "directsound", "openal", "silent")

from src.base_attackers.game import main  # noqa: E402

main()
