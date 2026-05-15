"""Main menu for Base Attackers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from agf.views.main_menu import MainMenuViewBase as _AGFMainMenu

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


class MainMenuView(_AGFMainMenu):
    TITLE = "Base Attackers!"

    def __init__(self, manager: "GameStateManager") -> None:
        super().__init__()
        self._manager = manager

    def music_track(self) -> str | None:
        return "ending"

    def on_start_1p(self) -> None:
        # Phase 1: route to terrain testbed instead of GAME_INIT.
        from src.base_attackers.state import GameState

        self._manager.transition(GameState.TERRAIN_TEST)

    def on_start_2p(self) -> None:
        # Phase 1: route to terrain testbed instead of GAME_INIT.
        from src.base_attackers.state import GameState

        self._manager.transition(GameState.TERRAIN_TEST)

    def on_config(self) -> None:
        pass  # add a config view when ready

    def on_exit(self) -> None:
        from src.base_attackers.state import GameState

        self._manager.transition(GameState.EXIT)
