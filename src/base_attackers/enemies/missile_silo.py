"""MissileSilo — terrain-mounted enemy that launches missiles on proximity.

Construction safety pattern (same as FuelTower) — caller MUST:

    silo = MissileSilo(world_x=x, surface=..., cfg=..., scale=...)
    floor_y = terrain.floor_y_at(x)
    silo.center_y = floor_y + silo.height / 2.0

The constructor stores ``center_y = 0`` as a placeholder.
"""

from __future__ import annotations

import math

import arcade

from agf.paths import resource_path
from src.base_attackers.game_config import CombatSettings

_SPRITE_PATH = "assets/images/PNG/Parts/engine1.png"


class MissileSilo(arcade.Sprite):
    def __init__(
        self,
        world_x: float,
        surface: str,
        cfg: CombatSettings,
        scale: float,
    ) -> None:
        super().__init__(resource_path(_SPRITE_PATH), scale=scale)
        self.center_x = world_x
        self.center_y = 0.0  # placeholder — caller overwrites
        self.surface: str = surface  # "floor" or "ceiling"
        self.cfg: CombatSettings = cfg
        self.hp: int = cfg.silo_hp
        # Floor silos point up (angle 0), ceiling silos flip 180.
        self.angle = 0.0 if surface == "floor" else 180.0
        self._fire_ready: bool = True

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def check_proximity(self, ship_x: float, ship_y: float) -> bool:
        """Arm-and-fire test.  True if the ship is within trigger range
        AND the silo is ready to fire (one shot until ``reset_fire``).
        """
        if not self._fire_ready:
            return False
        dist = math.hypot(ship_x - self.center_x, ship_y - self.center_y)
        if dist <= self.cfg.missile_proximity_trigger:
            self._fire_ready = False
            return True
        return False

    def reset_fire(self) -> None:
        """Called by RunLevelView when the launched missile leaves the world."""
        self._fire_ready = True
