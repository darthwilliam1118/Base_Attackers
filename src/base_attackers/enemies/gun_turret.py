"""GunTurret — composite terrain-mounted enemy with rotating barrel.

GunTurret is NOT itself an ``arcade.Sprite``.  It owns two sprites
(``base`` and ``barrel``) that ``RunLevelView`` adds to two separate
SpriteLists so barrels render above bases.

Position-on-terrain pattern matches FuelTower: the constructor leaves
``base.center_y`` at 0 (dummy); the caller invokes
``position_on_terrain(surface_y)`` after construction, once
``base.height`` is available from the loaded texture.

Sprite angle convention: empirically, arcade.Sprite.angle rotates
such that ``angle = bearing - aim_angle`` aligns the barrel with the
target.  ``_SPRITE_NATURAL_BEARING_DEG`` is the math-degree bearing
(``atan2`` convention: 0=east, 90=up) at which the sprite's barrel
visually points at angle=0.  ``gun04.png`` ships pointing up, so the
bearing is 90.  If a different ``_BARREL_SPRITE`` is swapped in and
its natural orientation differs, change this one constant.
"""

from __future__ import annotations

import math
import random

import arcade

from agf.paths import resource_path
from src.base_attackers.combat.enemy_bullet import EnemyBullet
from src.base_attackers.game_config import CombatSettings

_BASE_SPRITE = "assets/images/PNG/Parts/turretBase_small.png"
_BARREL_SPRITE = "assets/images/PNG/Parts/gun04.png"
_AIM_THRESHOLD_RAD = math.radians(8.0)
_SPRITE_NATURAL_BEARING_DEG = 90.0  # gun04.png art points up by default


class GunTurret:
    def __init__(
        self,
        world_x: float,
        surface: str,
        cfg: CombatSettings,
        scale: float,
    ) -> None:
        self.surface: str = surface  # "floor" or "ceiling"
        self.cfg: CombatSettings = cfg
        self.hp: int = cfg.turret_hp
        self._fire_cooldown: float = 0.0

        # Base sprite — stationary, will be positioned by position_on_terrain.
        self.base = arcade.Sprite(resource_path(_BASE_SPRITE), scale=scale)
        self.base.center_x = world_x
        self.base.center_y = 0.0

        # Barrel sprite — rotates to aim; caller positions vertically.
        self.barrel = arcade.Sprite(resource_path(_BARREL_SPRITE), scale=scale)
        self.barrel.center_x = world_x
        self.barrel.center_y = 0.0

        # Starting aim — floor turrets point up, ceiling point down.
        self._aim_angle: float = 90.0 if surface == "floor" else 270.0
        self.barrel.angle = _SPRITE_NATURAL_BEARING_DEG - self._aim_angle

        # Vertical offset from base.center_y to barrel.center_y.  Set
        # by position_on_terrain once base.height is known.
        self._barrel_offset_y: float = 0.0

    # ---- properties -----------------------------------------------

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    # ---- placement ------------------------------------------------

    def position_on_terrain(self, surface_y: float) -> None:
        """Position base + barrel after construction.

        Floor: base sits on floor (centre = surface_y + half base),
        barrel sits above base.  Ceiling: mirrored.
        """
        half_base = self.base.height / 2.0
        half_barrel = self.barrel.height / 2.0
        if self.surface == "floor":
            self.base.center_y = surface_y + half_base
            self.base.angle = 180.0  # flip base so its top faces up
            self._barrel_offset_y = half_base + half_barrel + 2.0
        else:
            self.base.center_y = surface_y - half_base
            self.base.angle = 0.0
            self._barrel_offset_y = -(half_base + half_barrel + 2.0)
        self.barrel.center_y = self.base.center_y + self._barrel_offset_y

    # ---- per-frame ------------------------------------------------

    def update(self, ship_x: float, ship_y: float, delta_time: float) -> bool:
        """Rotate the barrel toward the ship and possibly fire.

        Returns True on the frame the turret decides to fire.  Caller
        is responsible for constructing the bullet via fire_bullet().
        """
        if not self.is_alive:
            return False

        # Bearing from barrel to ship (CCW from +X).
        dx = ship_x - self.barrel.center_x
        dy = ship_y - self.barrel.center_y
        target_angle_deg = math.degrees(math.atan2(dy, dx))

        # Rotate toward target at most cfg.turret_rotation_speed deg/s,
        # taking the shortest path around 360°.
        diff = (target_angle_deg - self._aim_angle + 180.0) % 360.0 - 180.0
        max_rot = self.cfg.turret_rotation_speed * delta_time
        if abs(diff) <= max_rot:
            self._aim_angle = target_angle_deg
        else:
            self._aim_angle += math.copysign(max_rot, diff)
        self._aim_angle %= 360.0
        self.barrel.angle = _SPRITE_NATURAL_BEARING_DEG - self._aim_angle

        # Keep barrel centred on the (stationary) base.
        self.barrel.center_x = self.base.center_x
        self.barrel.center_y = self.base.center_y + self._barrel_offset_y

        # Fire check.
        if self._fire_cooldown > 0.0:
            self._fire_cooldown = max(0.0, self._fire_cooldown - delta_time)
            return False
        residual_diff = (target_angle_deg - self._aim_angle + 180.0) % 360.0 - 180.0
        if abs(math.radians(residual_diff)) <= _AIM_THRESHOLD_RAD:
            self._fire_cooldown = self.cfg.turret_fire_cooldown
            return True
        return False

    def fire_bullet(self, speed: float, scale: float) -> EnemyBullet:
        """Build an EnemyBullet at the barrel muzzle with aim jitter."""
        jitter = random.uniform(-self.cfg.turret_aim_jitter, self.cfg.turret_aim_jitter)
        angle_rad = math.radians(self._aim_angle) + jitter
        return EnemyBullet(
            x=self.barrel.center_x,
            y=self.barrel.center_y,
            angle_rad=angle_rad,
            speed=speed,
            scale=scale,
            lifetime=self.cfg.enemy_bullet_lifetime,
        )

    # ---- damage ---------------------------------------------------

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0
