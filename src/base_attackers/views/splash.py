"""Splash screen for Base Attackers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from agf.views.splash import SplashView as _AGFSplash

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


class SplashView(_AGFSplash):
    TITLE_LINE1 = "Base Attackers!"
    TITLE_LINE2 = ""
    AUTO_ADVANCE = 5.0

    def __init__(self, manager: "GameStateManager") -> None:
        self._manager = manager
        super().__init__(on_complete=self._go_to_main)

    def _preload_tracks(self) -> None:
        self.window.music.load_track("ending")
        self._assets_ready = True

    def on_show_view(self) -> None:
        super().on_show_view()
        self.window.music.play("ending")

    def _go_to_main(self) -> None:
        from src.base_attackers.state import GameState

        self._manager.transition(GameState.MAIN)
