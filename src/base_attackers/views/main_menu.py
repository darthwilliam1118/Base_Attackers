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
        from src.base_attackers.state import GameState

        cfg = self._manager.context.get("config")
        self._manager.transition(GameState.GAME_INIT, num_players=1, config=cfg)

    def on_start_2p(self) -> None:
        from src.base_attackers.state import GameState

        cfg = self._manager.context.get("config")
        self._manager.transition(GameState.GAME_INIT, num_players=2, config=cfg)

    def on_config(self) -> None:
        pass  # add a config view when ready

    def on_exit(self) -> None:
        from src.base_attackers.state import GameState

        self._manager.transition(GameState.EXIT)
