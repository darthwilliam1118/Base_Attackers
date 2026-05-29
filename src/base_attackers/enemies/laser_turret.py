"""LaserTurret — composite terrain-mounted enemy that fires an
instantaneous laser beam.

State machine:
  IDLE      — waiting; rotates barrel toward player at slow speed.
  TELEGRAPH — proximity triggered; dim warning beam drawn for
              ``laser_telegraph_duration`` seconds.
  FIRING    — full beam drawn for ``laser_beam_duration`` seconds;
              damage applied on the frame the state enters FIRING.
  COOLDOWN  — reloading; barrel still tracks player.

The beam itself is NOT a sprite — it is drawn by RunLevelView as an
immediate-mode line (arcade.draw_line) in world-camera space.  This is
acceptable because it is a purely ephemeral visual that lasts < 0.2s;
no SpriteList churn occurs.

Position-on-terrain pattern: same two-step construct + position_on_terrain
as GunTurret — caller sets positions once base.height is known.
"""

from __future__ import annotations

import math

import arcade

from agf.paths import resource_path
from src.base_attackers.game_config import CombatSettings

_BASE_SPRITE = "assets/images/PNG/Parts/turretBase_big.png"
_BARREL_SPRITE = "assets/images/PNG/Parts/gun09.png"
_SPRITE_NATURAL_BEARING_DEG = 90.0  # gun09.png points up at angle=0

_STATE_IDLE = "idle"
_STATE_TELEGRAPH = "telegraph"
_STATE_FIRING = "firing"
_STATE_COOLDOWN = "cooldown"


class LaserTurret:
    def __init__(
        self,
        world_x: float,
        surface: str,
        cfg: CombatSettings,
        scale: float,
    ) -> None:
        self.surface = surface  # "floor" or "ceiling"
        self.cfg = cfg
        self.hp: int = cfg.laser_turret_hp
        self._state: str = _STATE_IDLE
        self._state_timer: float = 0.0
        self._aim_angle: float = 90.0 if surface == "floor" else 270.0
        self._fire_cooldown: float = 0.0
        self._damage_dealt: bool = False  # reset each FIRING entry

        self.base = arcade.Sprite(resource_path(_BASE_SPRITE), scale=scale)
        self.barrel = arcade.Sprite(resource_path(_BARREL_SPRITE), scale=scale)
        self.base.center_x = world_x
        self.barrel.center_x = world_x
        self.base.center_y = 0.0
        self.barrel.center_y = 0.0
        self.barrel.angle = _SPRITE_NATURAL_BEARING_DEG - self._aim_angle
        self._barrel_offset_y: float = 0.0

    # ---- properties -----------------------------------------------

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def is_telegraphing(self) -> bool:
        return self._state == _STATE_TELEGRAPH

    @property
    def is_firing(self) -> bool:
        return self._state == _STATE_FIRING

    # ---- damage ---------------------------------------------------

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    # ---- placement ------------------------------------------------

    def position_on_terrain(self, surface_y: float) -> None:
        """Same pattern as GunTurret — call after construction."""
        half_base = self.base.height / 2.0
        half_barrel = self.barrel.height / 2.0
        if self.surface == "floor":
            self.base.center_y = surface_y + half_base
            self.base.angle = 180.0
            self._barrel_offset_y = half_base + half_barrel + 2.0
        else:
            self.base.center_y = surface_y - half_base
            self.base.angle = 0.0
            self._barrel_offset_y = -(half_base + half_barrel + 2.0)
        self.barrel.center_y = self.base.center_y + self._barrel_offset_y

    # ---- beam geometry --------------------------------------------

    def beam_end(self, beam_length: float = 800.0) -> tuple[float, float]:
        """World-space endpoint of the beam from barrel tip."""
        rad = math.radians(self._aim_angle)
        tip_x = self.barrel.center_x
        tip_y = self.barrel.center_y
        return (
            tip_x + math.cos(rad) * beam_length,
            tip_y + math.sin(rad) * beam_length,
        )

    # ---- per-frame ------------------------------------------------

    def update(self, ship_x: float, ship_y: float, delta_time: float) -> str:
        """Tick state machine. Returns current state name so RunLevelView
        knows when to draw beams and apply damage.
        """
        if not self.is_alive:
            return _STATE_IDLE

        # Rotate barrel toward player (always, even while telegraphing).
        dx = ship_x - self.barrel.center_x
        dy = ship_y - self.barrel.center_y
        target = math.degrees(math.atan2(dy, dx))
        diff = (target - self._aim_angle + 180.0) % 360.0 - 180.0
        rot_speed = self.cfg.turret_rotation_speed * 0.5  # slower than gun turret
        max_rot = rot_speed * delta_time
        self._aim_angle += math.copysign(min(abs(diff), max_rot), diff)
        self._aim_angle %= 360.0
        self.barrel.angle = _SPRITE_NATURAL_BEARING_DEG - self._aim_angle
        self.barrel.center_x = self.base.center_x
        self.barrel.center_y = self.base.center_y + self._barrel_offset_y

        # State transitions.
        if self._state == _STATE_IDLE:
            if self._fire_cooldown > 0.0:
                self._fire_cooldown = max(0.0, self._fire_cooldown - delta_time)
            else:
                dist = math.hypot(dx, dy)
                if dist <= self.cfg.laser_proximity_trigger:
                    self._state = _STATE_TELEGRAPH
                    self._state_timer = self.cfg.laser_telegraph_duration
                    self._damage_dealt = False

        elif self._state == _STATE_TELEGRAPH:
            self._state_timer -= delta_time
            if self._state_timer <= 0.0:
                self._state = _STATE_FIRING
                self._state_timer = self.cfg.laser_beam_duration

        elif self._state == _STATE_FIRING:
            self._state_timer -= delta_time
            if self._state_timer <= 0.0:
                self._state = _STATE_COOLDOWN
                self._fire_cooldown = self.cfg.laser_turret_fire_cooldown

        elif self._state == _STATE_COOLDOWN:
            # Cooldown counts down via _fire_cooldown in IDLE state.
            self._state = _STATE_IDLE

        return self._state
