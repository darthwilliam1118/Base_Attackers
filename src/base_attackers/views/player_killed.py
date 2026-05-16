"""PlayerKilledView — brief pause after player death.

No agf base class — self-contained implementation.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional
import arcade
from agf.ui.text_utils import FONT_THIN, centered_text

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager

_DISPLAY_DURATION = 2.0


class PlayerKilledView(arcade.View):

    def __init__(self, manager: "GameStateManager") -> None:
        super().__init__()
        self._manager = manager
        self._elapsed: float = 0.0
        self._label: Optional[arcade.Text] = None

    def on_show_view(self) -> None:
        w, h = self.window.width, self.window.height
        self._label = centered_text(
            "SHIP DESTROYED",
            w,
            h // 2,
            font_size=36,
            color=arcade.color.RED,
            font_name=FONT_THIN,
        )

    def on_update(self, delta_time: float) -> None:
        self.window.star_field.update(delta_time)
        self._elapsed += delta_time
        if self._elapsed >= _DISPLAY_DURATION:
            self._advance()

    def on_draw(self) -> None:
        self.clear()
        self.window.background.draw()
        self.window.star_field.draw()
        if self._label:
            alpha = int(abs(math.sin(self._elapsed * 3)) * 255)
            self._label.color = (255, 60, 60, alpha)
            self._label.draw()

    def on_key_press(self, key: int, modifiers: int) -> None:
        self._advance()

    def _advance(self) -> None:
        from src.base_attackers.state import GameState

        players = self._manager.context.get("players", [])
        idx = self._manager.context.get("active_player_index", 0)
        if players:
            players[idx].lives -= 1
        if not players or players[idx].lives <= 0:
            self._manager.transition(GameState.GAME_OVER)
        else:
            self._manager.transition(GameState.SET_ACTIVE_PLAYER)
