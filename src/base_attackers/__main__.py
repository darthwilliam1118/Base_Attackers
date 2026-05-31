"""Allow running as python -m base_attackers."""

import sys
from pathlib import Path

import pyglet

# Must run before any agf/arcade import — see the matching note in main.py.
# ``win32_gdi_font`` is read when ``pyglet.font`` is first imported (which
# arcade does, pulled in by the first agf import), and DirectWrite cannot
# resolve font family names ending in a weight word like "Thin".
if sys.platform == "win32":
    pyglet.options["win32_gdi_font"] = (
        True  # DirectWrite can't find fonts with weight names like "Thin"
    )
    pyglet.options["audio"] = ("xaudio2", "directsound", "openal", "silent")

from agf.paths import set_project_root  # noqa: E402

set_project_root(Path(__file__).parents[3])  # src/<pkg>/__main__.py → project root

from src.base_attackers.game import main  # noqa: E402

main()
