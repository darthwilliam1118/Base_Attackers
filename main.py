"""Entry point for Base Attackers."""

import sys
from pathlib import Path

import pyglet
from agf.paths import set_project_root

set_project_root(Path(__file__).parent)

if sys.platform == "win32":
    pyglet.options["win32_gdi_font"] = (
        True  # DirectWrite can't find fonts with weight names like "Thin"
    )
    pyglet.options["audio"] = ("xaudio2", "directsound", "openal", "silent")

from src.base_attackers.game import GameWindow  # noqa: E402
import arcade  # noqa: E402


def main() -> None:
    GameWindow()
    arcade.run()


if __name__ == "__main__":
    main()
