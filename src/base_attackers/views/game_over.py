"""GameOverView."""
from __future__ import annotations

from typing import TYPE_CHECKING
from agf.views.game_over import GameOverView as _AGFGameOver

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


class GameOverView(_AGFGameOver):

    def __init__(self, manager: "GameStateManager") -> None:
        self._manager = manager
        super().__init__(on_complete=self._on_complete)

    def get_players(self):
        return self._manager.context.get("players", [])

    def _on_complete(self) -> None:
        from src.base_attackers.state import GameState
        self._manager.transition(GameState.SCORE_ENTRY)
