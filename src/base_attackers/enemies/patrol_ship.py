"""PatrolShip — enemy that flies through the level from right to left.

Spawned off the right edge of the camera view; exits off the left edge
(straight/intercept) or is destroyed on player contact (kamikaze).
Behaviour is selected at spawn time and is immutable for the ship's
lifetime.

NOT terrain-mounted — no two-step Y positioning needed.  Spawns at a
world Y chosen by RunLevelView._spawn_patrol_ship().

Each frame ``update_patrol`` (1) sets velocity from the behaviour, (2)
applies reactive terrain avoidance that biases the ship away from a
floor/ceiling close ahead, (3) ticks the weapon cooldown, (4) moves, and
(5) rotates the sprite to face its direction of travel.  Avoidance is
reactive (not path-planning): it keeps the ship in the open corridor
when possible; a ship that still contacts terrain is exploded by
RunLevelView.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import arcade

from agf.paths import resource_path
from src.base_attackers.game_config import CombatSettings

if TYPE_CHECKING:
    from src.base_attackers.terrain import TerrainBase

# Behaviour names — stored on each PatrolShip at spawn time.
BEHAVIOUR_STRAIGHT = "straight"  # flies straight across at fixed Y
BEHAVIOUR_INTERCEPT = "intercept"  # leads the player's current position
BEHAVIOUR_KAMIKAZE = "kamikaze"  # dives directly at player, no exit

_SPRITE_MAP = {
    BEHAVIOUR_STRAIGHT: "assets/images/PNG/Enemies/enemyBlack2.png",
    BEHAVIOUR_INTERCEPT: "assets/images/PNG/Enemies/enemyBlue3.png",
    BEHAVIOUR_KAMIKAZE: "assets/images/PNG/Enemies/enemyRed1.png",
}

# Kenney enemy sprites are drawn nose-down (south) at angle 0.  The sprite
# is rotated each frame to face its travel heading via
# ``angle = _NATURAL_BEARING_DEG - heading`` (same clockwise-positive
# convention GunTurret uses).  Flip this by 180 if a swapped art asset
# points the opposite way.
_NATURAL_BEARING_DEG = 270.0

# Reactive avoidance: how far ahead (px) to sample the corridor, and the
# clearance (px) kept from floor/ceiling before steering away.
_AVOID_LOOKAHEAD = 90.0
_AVOID_MARGIN = 55.0


class PatrolShip(arcade.Sprite):
    def __init__(
        self,
        world_x: float,
        world_y: float,
        behaviour: str,
        speed: float,
        cfg: CombatSettings,
        scale: float,
    ) -> None:
        super().__init__(
            resource_path(_SPRITE_MAP[behaviour]),
            scale=scale,
            hit_box_algorithm=arcade.hitbox.algo_simple,
        )
        self.center_x = world_x
        self.center_y = world_y
        self.behaviour = behaviour
        self.cfg = cfg
        self.hp: int = cfg.patrol_hp
        self._speed = speed
        # velocity components set each frame by update_patrol()
        self._vx: float = -speed  # starts moving left
        self._vy: float = 0.0
        # Kamikazes don't shoot; others fire on a cooldown.
        self.fires: bool = behaviour != BEHAVIOUR_KAMIKAZE
        self._fire_cooldown: float = cfg.patrol_fire_cooldown
        # Initial facing — left; refreshed every frame from velocity.
        self.angle = (_NATURAL_BEARING_DEG - 180.0) % 360.0

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def try_fire(self) -> bool:
        """Consume the weapon cooldown.  True if a shot fires this frame."""
        if not self.fires or self._fire_cooldown > 0.0:
            return False
        self._fire_cooldown = self.cfg.patrol_fire_cooldown
        return True

    def update_patrol(
        self,
        ship_x: float,
        ship_y: float,
        delta_time: float,
        terrain: "TerrainBase",
    ) -> None:
        """Update velocity (behaviour + avoidance) then apply movement."""
        # 1. Behaviour velocity.
        if self.behaviour == BEHAVIOUR_STRAIGHT:
            # Fixed leftward velocity — no Y adjustment.
            pass

        elif self.behaviour == BEHAVIOUR_INTERCEPT:
            # Steer toward player's current position with a speed cap.
            dx = ship_x - self.center_x
            dy = ship_y - self.center_y
            dist = math.hypot(dx, dy) or 1.0
            self._vx = -(self._speed * abs(dx) / dist)
            self._vy = self._speed * dy / dist * self.cfg.patrol_intercept_lead

        elif self.behaviour == BEHAVIOUR_KAMIKAZE:
            # Always steer directly at player — no exit.
            dx = ship_x - self.center_x
            dy = ship_y - self.center_y
            dist = math.hypot(dx, dy) or 1.0
            self._vx = self._speed * dx / dist
            self._vy = self._speed * dy / dist

        # 2. Reactive terrain avoidance — overrides _vy near a surface.
        self._avoid_terrain(terrain)

        # 3. Weapon cooldown.
        if self._fire_cooldown > 0.0:
            self._fire_cooldown = max(0.0, self._fire_cooldown - delta_time)

        # 4. Move.
        self.center_x += self._vx * delta_time
        self.center_y += self._vy * delta_time

        # 5. Face direction of travel.
        if self._vx or self._vy:
            heading = math.degrees(math.atan2(self._vy, self._vx))
            self.angle = (_NATURAL_BEARING_DEG - heading) % 360.0

    def _avoid_terrain(self, terrain: "TerrainBase") -> None:
        """Bias vertical velocity away from a floor/ceiling close ahead.

        Samples the corridor at the current X and a short lookahead in the
        travel direction; if the ship is within ``_AVOID_MARGIN`` of the
        nearer floor it climbs, if within margin of the ceiling it dives.
        Otherwise the behaviour velocity is left untouched.
        """
        look_x = self.center_x + math.copysign(
            _AVOID_LOOKAHEAD, self._vx if self._vx else -1.0
        )
        floor_y = max(terrain.floor_y_at(self.center_x), terrain.floor_y_at(look_x))
        ceils = [
            c
            for c in (
                terrain.ceiling_y_at(self.center_x),
                terrain.ceiling_y_at(look_x),
            )
            if c is not None
        ]
        if self.center_y - _AVOID_MARGIN <= floor_y:
            self._vy = abs(self._speed)
        elif ceils and self.center_y + _AVOID_MARGIN >= min(ceils):
            self._vy = -abs(self._speed)
