"""BaseBoss — large stationary boss enemy with multiple gun hardpoints.

Composite object (like ``GunTurret`` / ``LaserTurret``): NOT itself an
``arcade.Sprite``.  Owns a ``body`` sprite and ``hardpoints`` (a list of
``GunTurret`` instances).  ``RunLevelView`` owns the SpriteLists and the
collision/draw wiring:
- the body goes into ``_boss_body_list``,
- the hardpoint base/barrel sprites go into dedicated
  ``_boss_hp_base_list`` / ``_boss_hp_barrel_list`` (NOT the shared
  ``_turret_*_list`` — boss hardpoints are updated/fired by the boss, not
  by ``_update_turrets``, and resolved by a dedicated collision pass).

Placement is the two-step construct + position pattern: the body sprite
height is only known after the texture loads, so the caller builds the
boss then calls ``place(center_y)`` once ``body.height`` is available.

Hardpoints fire on the boss cadence via the ``_BossCombatSettings`` shim,
which overrides only ``turret_fire_cooldown`` so the standard
``GunTurret`` is reused unchanged.
"""

from __future__ import annotations

import math

import arcade

from agf.paths import resource_path
from src.base_attackers.combat.enemy_bullet import EnemyBullet
from src.base_attackers.enemies.gun_turret import GunTurret
from src.base_attackers.game_config import CombatSettings

_BODY_SPRITE = "assets/images/PNG/Enemies/boss_body.png"
_BOSS_BULLET_PATH = "assets/images/PNG/Lasers/boss_shot1.png"
# boss_shot1.png renders facing east at angle 0 (same convention as
# EnemyBullet's laserRed01).  Flip this if a swapped asset points elsewhere.
_BULLET_NATURAL_BEARING_DEG = 0.0


class _BossCombatSettings:
    """Thin wrapper over ``CombatSettings`` that overrides only
    ``turret_fire_cooldown`` so boss hardpoints fire on the boss cadence
    without modifying ``GunTurret`` or ``CombatSettings``.  Every other
    attribute access delegates to the wrapped settings.
    """

    def __init__(self, base: CombatSettings) -> None:
        self._base = base

    def __getattr__(self, name: str):
        if name == "turret_fire_cooldown":
            return self._base.boss_fire_cooldown
        return getattr(self._base, name)


class BossBullet(EnemyBullet):
    """Boss-fired bullet — identical motion/expiry to ``EnemyBullet`` but
    uses the dedicated ``boss_shot1.png`` sprite.  Goes into
    ``_enemy_bullet_list`` so the existing enemy-bullet collision, move,
    and cull all handle it for free.
    """

    def __init__(
        self,
        x: float,
        y: float,
        angle_rad: float,
        speed: float,
        scale: float,
        lifetime: float = 3.0,
    ) -> None:
        # Bypass EnemyBullet.__init__ (it hardcodes its own texture) and
        # load the boss bullet sprite instead.
        arcade.Sprite.__init__(
            self,
            arcade.load_texture(
                resource_path(_BOSS_BULLET_PATH),
                hit_box_algorithm=arcade.hitbox.algo_simple,
            ),
            scale=scale,
        )
        self.center_x = x
        self.center_y = y
        self._vx = math.cos(angle_rad) * speed
        self._vy = math.sin(angle_rad) * speed
        self.angle = _BULLET_NATURAL_BEARING_DEG - math.degrees(angle_rad)
        self._lifetime = lifetime
        self._age = 0.0


class BaseBoss:
    def __init__(
        self,
        world_x: float,
        level_num: int,
        cfg: CombatSettings,
        sprite_scale: float,
    ) -> None:
        self.cfg = cfg
        self.level_num = level_num

        # HP scales with level.
        self.max_hp: int = cfg.boss_hp_base + (level_num - 1) * cfg.boss_hp_per_level
        self.hp: int = self.max_hp

        # Body sprite — large, centred in the boss zone.  center_y is a
        # placeholder until place() runs (body.height known after load).
        boss_scale = sprite_scale * cfg.boss_scale_factor
        self.body = arcade.Sprite(resource_path(_BODY_SPRITE), scale=boss_scale)
        self.body.center_x = world_x
        self.body.center_y = 0.0

        self.hardpoints: list[GunTurret] = []
        self._sprite_scale = sprite_scale

    # ---- properties -----------------------------------------------

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def hp_fraction(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    # ---- damage ---------------------------------------------------

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if the boss is destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    # ---- placement ------------------------------------------------

    def place(self, center_y: float) -> None:
        """Set the body's vertical position and attach the hardpoints.

        Call after construction once ``body.height`` is available::

            boss = BaseBoss(...)
            boss.place(corridor_center_y)
        """
        self.body.center_y = center_y
        self._attach_hardpoints()

    def _attach_hardpoints(self) -> None:
        """Create ``GunTurret`` hardpoints positioned around the body.

        Offsets are relative to the body centre so the turrets read as
        part of the boss.  ``hw*0.4`` / ``hh*0.5`` multipliers are
        geometric starting points — tune for the art.  Hardpoints float in
        space, so positions are set directly rather than via
        ``position_on_terrain``.
        """
        cfg = self.cfg
        hw = self.body.width / 2.0
        hh = self.body.height / 2.0
        cx = self.body.center_x
        cy = self.body.center_y

        boss_cfg = _BossCombatSettings(cfg)  # boss fire cadence for hardpoints

        count = min(cfg.boss_hardpoint_count, 4)
        offsets: list[tuple[float, float, str]] = []
        if count >= 1:
            offsets.append((0.0, hh * 0.5, "floor"))  # top
        if count >= 2:
            offsets.append((-hw * 0.4, 0.0, "floor"))  # left
        if count >= 3:
            offsets.append((hw * 0.4, 0.0, "floor"))  # right
        if count >= 4:
            offsets.append((0.0, -hh * 0.5, "ceiling"))  # bottom

        for ox, oy, surface in offsets:
            turret = GunTurret(
                world_x=cx + ox,
                surface=surface,
                cfg=boss_cfg,  # type: ignore[arg-type]
                scale=self._sprite_scale,
            )
            half_base = turret.base.height / 2.0
            half_barrel = turret.barrel.height / 2.0
            turret.base.center_x = cx + ox
            turret.base.center_y = cy + oy
            turret.barrel.center_x = cx + ox
            if surface == "floor":
                turret.base.angle = 180.0
                turret._barrel_offset_y = half_base + half_barrel + 2.0
            else:
                turret.base.angle = 0.0
                turret._barrel_offset_y = -(half_base + half_barrel + 2.0)
            turret.barrel.center_y = turret.base.center_y + turret._barrel_offset_y
            self.hardpoints.append(turret)

    # ---- per-frame ------------------------------------------------

    def update(
        self, ship_x: float, ship_y: float, delta_time: float
    ) -> list[BossBullet]:
        """Tick every live hardpoint and return the ``BossBullet``s fired
        this frame.  The body is stationary — no movement update.
        """
        bullets: list[BossBullet] = []
        for hp in self.hardpoints:
            if not hp.is_alive:
                continue
            if hp.update(ship_x, ship_y, delta_time):
                angle_rad = math.radians(hp._aim_angle)
                bullets.append(
                    BossBullet(
                        x=hp.barrel.center_x,
                        y=hp.barrel.center_y,
                        angle_rad=angle_rad,
                        speed=self.cfg.boss_bullet_speed,
                        scale=self._sprite_scale,
                        lifetime=self.cfg.enemy_bullet_lifetime,
                    )
                )
        return bullets
