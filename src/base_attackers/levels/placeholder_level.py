"""PlaceholderLevel — stub level shown until real game logic is added.

Replace this file with your game's level implementation.
See agf.levels.base_level.BaseLevel for the full interface.
"""
from __future__ import annotations

from typing import Any
import arcade
from agf.levels.base_level import BaseLevel
from agf.events import GameEvent


class PlaceholderLevel(BaseLevel):
    """A do-nothing level that never clears.

    Shows a centered message and lets the player press W to win
    or L to lose for testing purposes.
    """

    def __init__(self, window_width: int, window_height: int):
        self._w = window_width
        self._h = window_height
        self._label = arcade.Text(
            "REPLACE THIS WITH YOUR GAME LOGIC\n"
            "W = complete level    L = lose a life",
            x=window_width / 2,
            y=window_height / 2,
            color=arcade.color.WHITE,
            font_size=18,
            anchor_x="center",
            anchor_y="center",
            multiline=True,
            width=window_width - 80,
            align="center",
        )

    @property
    def level_type(self) -> str:
        return "placeholder"

    def setup(self, level_number: int) -> None:
        pass

    def update(self, delta_time: float,
               player_ship: Any) -> list[GameEvent]:
        return []

    def draw(self) -> None:
        self._label.draw()

    def is_cleared(self) -> bool:
        return False

    def apply_player_bullet(self, bullet: Any) -> Any:
        return None

    def consume_pending_hits(self) -> list[tuple[float, float, int]]:
        return []

    def consume_pending_non_lethal_hits(self) -> list[tuple[float, float]]:
        return []

    def get_all_enemy_sprites(self) -> arcade.SpriteList:
        return arcade.SpriteList()

    def get_enemy_bullet_sprite_list(self) -> arcade.SpriteList:
        return arcade.SpriteList()

    def get_powerup_manager(self):
        return None

    def to_snapshot(self) -> dict:
        return {"level_type": "placeholder"}

    @classmethod
    def from_snapshot(cls, snapshot: dict, config: Any,
                      window_width: int,
                      window_height: int) -> "PlaceholderLevel":
        return cls(window_width, window_height)
