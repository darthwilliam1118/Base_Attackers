"""PlayerBullet — rightward-travelling projectile fired by the player ship.

Texture loaded with ``algo_simple`` (bounding-box) hit-box — bullets
are small fast sprites where pixel-perfect collision adds cost with
no gameplay benefit (per CLAUDE.md).
"""

from __future__ import annotations

import arcade

from agf.paths import resource_path

_SPRITE_PATH = "assets/images/PNG/Lasers/laserBlue01_right.png"


class PlayerBullet(arcade.Sprite):
    def __init__(
        self, x: float, y: float, speed: float, scale: float, vy: float = 0.0
    ) -> None:
        texture = arcade.load_texture(
            resource_path(_SPRITE_PATH),
            hit_box_algorithm=arcade.hitbox.algo_simple,
        )
        super().__init__(texture, scale=scale)
        self.center_x = x
        self.center_y = y
        self._speed = speed
        self._vy = vy

    def update_bullet(self, delta_time: float) -> None:
        self.center_x += self._speed * delta_time
        if self._vy:
            self.center_y += self._vy * delta_time
