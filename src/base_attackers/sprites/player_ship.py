"""Placeholder player ship sprite.

Replace with your game's actual player ship implementation.
"""
from __future__ import annotations

import arcade


class PlayerShip(arcade.Sprite):
    """Simple placeholder ship — a colored rectangle.

    Replace with a real sprite loaded from assets/images/.
    """

    def __init__(self, window_width: int, window_height: int,
                 scale: float = 1.0):
        super().__init__()
        # Placeholder texture — replace with arcade.load_texture(...)
        self.texture = arcade.make_soft_circle_texture(
            40, arcade.color.CYAN
        )
        self.scale = scale
        self._window_width = window_width
        self._window_height = window_height

        # Spawn at centre bottom
        self.center_x = window_width / 2
        self.center_y = 60

        self.hit_points: int = 100
        self.max_hit_points: int = 100

    def is_invincible(self) -> bool:
        return False

    def take_damage(self, amount: int) -> bool:
        self.hit_points = max(0, self.hit_points - amount)
        return self.hit_points <= 0

    def apply_movement(self, keys_held: set[int],
                       delta_time: float) -> None:
        speed = 300.0
        if arcade.key.LEFT in keys_held or arcade.key.A in keys_held:
            self.center_x -= speed * delta_time
        if arcade.key.RIGHT in keys_held or arcade.key.D in keys_held:
            self.center_x += speed * delta_time
        # Clamp to window
        half = self.width / 2
        self.center_x = max(half,
                            min(self._window_width - half, self.center_x))

    def update(self, delta_time: float = 1 / 60) -> None:
        pass
