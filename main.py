"""Entry point for Base Attackers."""

import sys
from pathlib import Path

import pyglet

# Pyglet selects its Windows font backend (DirectWrite vs GDI) the first
# time ``pyglet.font`` is imported, reading ``win32_gdi_font`` at that
# moment.  arcade — pulled in transitively by the very first ``agf``
# import — imports ``pyglet.font``, so this option MUST be set before any
# agf/arcade import or DirectWrite locks in and cannot resolve font family
# names that end in a weight word like "Thin" (all HUD text then silently
# falls back to the system font).
if sys.platform == "win32":
    pyglet.options["win32_gdi_font"] = (
        True  # DirectWrite can't find fonts with weight names like "Thin"
    )
    pyglet.options["audio"] = ("xaudio2", "directsound", "openal", "silent")

from agf.paths import set_project_root  # noqa: E402

set_project_root(Path(__file__).parent)

from src.base_attackers.game import GameWindow  # noqa: E402
import arcade  # noqa: E402


def main() -> None:
    GameWindow()
    arcade.run()


if __name__ == "__main__":
    main()
