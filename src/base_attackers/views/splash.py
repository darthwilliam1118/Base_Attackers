"""Splash screen for Base Attackers."""
from __future__ import annotations

from typing import TYPE_CHECKING
from agf.views.splash import SplashView as _AGFSplash

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


class SplashView(_AGFSplash):
    TITLE_LINE1 = "Base Attackers"
    AUTO_ADVANCE = 5.0

    def __init__(self, manager: "GameStateManager") -> None:
        self._manager = manager
        super().__init__(on_complete=self._go_to_main)

    def _preload_tracks(self) -> None:
        # Load music tracks here, e.g.:
        # self.window.music.load_track("menu")
        # self.window.music.load_track("level_1")
        self._assets_ready = True  # remove this line once tracks added

    def _go_to_main(self) -> None:
        from src.base_attackers.state import GameState
        self._manager.transition(GameState.MAIN)
