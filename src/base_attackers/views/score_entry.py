"""ScoreEntryView."""
from __future__ import annotations

from typing import TYPE_CHECKING
from agf.views.score_entry import ScoreEntryView as _AGFScoreEntry

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


class ScoreEntryView(_AGFScoreEntry):

    def __init__(self, manager: "GameStateManager") -> None:
        self._manager = manager
        super().__init__(on_complete=self._on_complete)

    def get_high_score_table(self):
        from agf.high_scores import HighScoreTable, scores_path
        return HighScoreTable.load(scores_path())

    def get_all_players(self):
        return self._manager.context.get("players", [])

    def _on_complete(self) -> None:
        from src.base_attackers.state import GameState
        self._manager.transition(GameState.MAIN)
