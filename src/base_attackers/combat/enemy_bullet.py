"""EnemyBullet — fired by gun turrets, travels at an arbitrary angle.

Same empirical angle convention as ``GunTurret`` (see that file):
``sprite.angle = NATURAL_BEARING - math.degrees(angle_rad)``, where
``NATURAL_BEARING`` is the math-degree direction the asset visually
points at angle=0.  ``laserRed01.png`` ships pointing up, so the
bearing is 90.  Swap in a horizontally-oriented bullet asset?  Set
the bearing to 0.
"""

from __future__ import annotations

import math

import arcade

from agf.paths import resource_path

_SPRITE_PATH = "assets/images/PNG/Lasers/laserRed01.png"
_SPRITE_NATURAL_BEARING_DEG = (
    0.0  # tuned in playtest — sprite renders correctly facing east
)


class EnemyBullet(arcade.Sprite):
    def __init__(
        self,
        x: float,
        y: float,
        angle_rad: float,
        speed: float,
        scale: float,
    ) -> None:
        texture = arcade.load_texture(
            resource_path(_SPRITE_PATH),
            hit_box_algorithm=arcade.hitbox.algo_simple,
        )
        super().__init__(texture, scale=scale)
        self.center_x = x
        self.center_y = y
        self._vx = math.cos(angle_rad) * speed
        self._vy = math.sin(angle_rad) * speed
        self.angle = _SPRITE_NATURAL_BEARING_DEG - math.degrees(angle_rad)

    def update_bullet(self, delta_time: float) -> None:
        self.center_x += self._vx * delta_time
        self.center_y += self._vy * delta_time
