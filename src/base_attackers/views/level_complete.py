"""LevelCompleteView."""

from __future__ import annotations

from typing import TYPE_CHECKING
from agf.views.level_complete import LevelCompleteView as _AGFLevelComplete

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


class LevelCompleteView(_AGFLevelComplete):

    def __init__(self, manager: "GameStateManager") -> None:
        self._manager = manager
        super().__init__(on_complete=self._on_complete)

    def build_bonus_text(self) -> str:
        return ""

    def build_player_rows(self) -> list[str]:
        players = self._manager.context.get("players", [])
        idx = self._manager.context.get("active_player_index", 0)
        if not players:
            return []
        p = players[idx]
        return [f"P{p.player_num}  {p.score}"]

    def _on_complete(self) -> None:
        from src.base_attackers.state import GameState

        players = self._manager.context.get("players", [])
        idx = self._manager.context.get("active_player_index", 0)
        if players:
            players[idx].current_level += 1
            players[idx].level_snapshot = None
        self._manager.transition(GameState.SET_ACTIVE_PLAYER)
