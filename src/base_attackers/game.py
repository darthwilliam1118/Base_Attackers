"""Main game window for Base Attackers."""
from __future__ import annotations

import arcade
from agf.window import GameWindowBase

from src.base_attackers.game_config import GameConfig
from src.base_attackers.state import GameState, GameStateManager

SCREEN_TITLE = "Base Attackers"


class GameWindow(GameWindowBase):
    TITLE = SCREEN_TITLE

    def __init__(self) -> None:
        cfg = GameConfig.load()
        super().__init__(cfg, cfg.background, SCREEN_TITLE)

        # Fonts — add your TTF files to assets/fonts/ and load here
        # arcade.load_font(resource_path("assets/fonts/your_font.ttf"))

        self.music.set_volume(cfg.music_volume)

        self._manager = GameStateManager(self, GameState.SPLASH)
        self._manager.transition(GameState.SPLASH)


def main() -> None:
    GameWindow()
    arcade.run()
