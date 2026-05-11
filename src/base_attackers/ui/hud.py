"""HUD for Base Attackers."""
from __future__ import annotations

from typing import Optional
import arcade
from agf.ui.hud_base import HUDBase
from agf.ui.text_utils import FONT_THIN


class HUD(HUDBase):

    def __init__(self, window_width: int, window_height: int,
                 num_players: int = 1):
        super().__init__(window_width, window_height)
        self._num_players = num_players
        self._score_text: Optional[arcade.Text] = None
        self._lives_text: Optional[arcade.Text] = None
        self._level_text: Optional[arcade.Text] = None
        self._last_score = -1
        self._last_lives = -1
        self._last_level = -1
        self._build()

    def _build(self) -> None:
        w, h = self.window_width, self.window_height
        y = h - 24
        self._score_text = arcade.Text(
            "SCORE: 0", 16, y,
            arcade.color.WHITE, 16,
            font_name=FONT_THIN, anchor_y="center",
        )
        self._lives_text = arcade.Text(
            "LIVES: 3", w - 16, y,
            arcade.color.WHITE, 16,
            font_name=FONT_THIN,
            anchor_x="right", anchor_y="center",
        )
        self._level_text = arcade.Text(
            "LEVEL: 1", w / 2, y,
            arcade.color.WHITE, 16,
            font_name=FONT_THIN,
            anchor_x="center", anchor_y="center",
        )

    def update(self, players: list, active_idx: int,
               level: int) -> None:
        if not players:
            return
        p = players[active_idx]
        if p.score != self._last_score:
            self._last_score = p.score
            if self._score_text:
                self._score_text.text = f"SCORE: {p.score}"
        if p.lives != self._last_lives:
            self._last_lives = p.lives
            if self._lives_text:
                self._lives_text.text = f"LIVES: {p.lives}"
        if level != self._last_level:
            self._last_level = level
            if self._level_text:
                self._level_text.text = f"LEVEL: {level}"

    def draw(self) -> None:
        if self._score_text:
            self._score_text.draw()
        if self._lives_text:
            self._lives_text.draw()
        if self._level_text:
            self._level_text.draw()
