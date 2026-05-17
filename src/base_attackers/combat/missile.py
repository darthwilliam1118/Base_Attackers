"""Missile — fired straight up or down by a MissileSilo.

``gun08.png`` is a placeholder sprite per the Phase 4 brief.  Its
natural orientation may face +Y; ``_SPRITE_FORWARD_OFFSET_DEG`` lets
us tune the upright pose in one place if needed.
"""

from __future__ import annotations

import arcade

from agf.paths import resource_path

_SPRITE_PATH = "assets/images/PNG/Parts/gun08.png"
_SPRITE_FORWARD_OFFSET_DEG = 0.0


class Missile(arcade.Sprite):
    def __init__(
        self,
        x: float,
        y: float,
        speed: float,
        direction: float,
        scale: float,
    ) -> None:
        """``direction``: +1.0 = upward (floor silos), -1.0 = downward."""
        texture = arcade.load_texture(
            resource_path(_SPRITE_PATH),
            hit_box_algorithm=arcade.hitbox.algo_simple,
        )
        super().__init__(texture, scale=scale)
        self.center_x = x
        self.center_y = y
        self._speed = speed
        self._direction = direction
        self.angle = (0.0 if direction > 0 else 180.0) + _SPRITE_FORWARD_OFFSET_DEG

    def update_missile(self, delta_time: float) -> None:
        self.center_y += self._speed * self._direction * delta_time
