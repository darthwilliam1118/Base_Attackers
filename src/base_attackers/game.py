"""Main game window for Base Attackers."""

from __future__ import annotations

import arcade
from agf.paths import resource_path
from agf.window import ScrollingGameWindow

from src.base_attackers.game_config import GameConfig
from src.base_attackers.state import GameState, GameStateManager

SCREEN_TITLE = "Base Attackers"

# Single project font — KenVector Future2 Thin
GAME_FONT = "KenVector Future2 Thin"


class GameWindow(ScrollingGameWindow):
    TITLE = SCREEN_TITLE

    def __init__(self) -> None:
        cfg = GameConfig.load()
        super().__init__(cfg, cfg.background, SCREEN_TITLE)

        # arcade.get_fps() returns 0 unless timings are enabled.
        arcade.enable_timings()

        self.music.set_volume(cfg.music_volume)
        # Preload and start the "ending" track — used on the splash, menu,
        # and every between-level screen.
        self.music.load_track("ending")
        self.music.play("ending")

        self._manager = GameStateManager(self, GameState.SPLASH)
        self._manager.transition(GameState.SPLASH)

    def _load_fonts(self) -> None:
        """Load TTFs and force every agf module that references FONT_MAIN
        to resolve to the thin font, so all rendered text uses
        KenVector Future2 Thin."""
        arcade.load_font(resource_path("assets/fonts/kenvector_future2.ttf"))
        arcade.load_font(resource_path("assets/fonts/kenvector_future_thin2.ttf"))

        import agf.ui.text_utils as _tu

        _tu.FONT_MAIN = GAME_FONT
        _tu.FONT_THIN = GAME_FONT

        # Modules that did `from agf.ui.text_utils import FONT_MAIN` cached
        # the name locally — rebind those too.
        import importlib

        for mod_name in (
            "agf.views.splash",
            "agf.views.main_menu",
            "agf.views.game_over",
            "agf.views.level_complete",
            "agf.views.score_entry",
        ):
            try:
                mod = importlib.import_module(mod_name)
            except Exception:
                continue
            if hasattr(mod, "FONT_MAIN"):
                mod.FONT_MAIN = GAME_FONT
            if hasattr(mod, "FONT_THIN"):
                mod.FONT_THIN = GAME_FONT


def main() -> None:
    GameWindow()
    arcade.run()
