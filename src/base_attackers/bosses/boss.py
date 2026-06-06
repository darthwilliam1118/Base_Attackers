"""BaseBoss — large boss enemy with destructible weapon hardpoints.

Composite object (NOT itself an ``arcade.Sprite``).  Owns a ``body``
sprite and ``hardpoints`` (a list of ``BossGun`` — single fixed weapon
sprites, no base, no rotation).  ``RunLevelView`` owns the SpriteLists and
the collision/draw wiring:
- the body goes into ``_boss_body_list``,
- each weapon sprite goes into ``_boss_gun_list`` (drawn ABOVE the body,
  and ABOVE the enemy-bullet list so boss bullets emerge from under it).

A boss is fully described by a ``BossSettings`` (one ``[boss.<key>]`` TOML
section, selected per level via ``[level_N] boss = "<key>"``): body sprite,
scale, HP, fire cadence, oscillation, and a list of ``BossWeapon`` mounts.
Each mount's offset is the weapon sprite's top-left pixel relative to the
body's top-left (native px, may be negative), converted here to a
world-space centre.  Weapons scale with the body and bob with it.
``"cannon"`` mounts fire bullets aimed at the player (the sprite never
rotates); ``"laser"`` mounts run a telegraph→beam machine driven by
``RunLevelView`` (the beam is aimed at the player, locked at firing).

Placement is the two-step construct + position pattern: the body sprite
height is only known after the texture loads, so the caller builds the
boss then calls ``place(center_y)`` once ``body.height`` is available.
"""

from __future__ import annotations

import math

import arcade

from agf.paths import resource_path
from src.base_attackers.combat.enemy_bullet import EnemyBullet
from src.base_attackers.game_config import BossSettings

_BOSS_BULLET_PATH = "assets/images/PNG/Lasers/boss_shot1.png"
# boss_shot1.png renders facing east at angle 0 (same convention as
# EnemyBullet's laserRed01).  Flip this if a swapped asset points elsewhere.
_BULLET_NATURAL_BEARING_DEG = 0.0


class BossGun:
    """A single fixed boss weapon mount — one sprite, no base, no rotation.
    Destructible (its own HP / explosion / score).

    ``weapon_type == "cannon"`` fires bullets aimed by the boss at the
    player (`update` cadence).  ``weapon_type == "laser"`` runs a
    telegraph→firing→cooldown beam machine driven by ``RunLevelView``
    (which holds the laser timings); the ``laser_*`` attributes below hold
    that per-mount state.
    """

    def __init__(
        self,
        texture: arcade.Texture,
        scale: float,
        hp: int,
        fire_period: float,
        weapon_type: str = "cannon",
        initial_cooldown: float = 0.0,
    ) -> None:
        self.sprite = arcade.Sprite(texture, scale=scale)
        self.hp = hp
        self.weapon_type = weapon_type
        self._fire_period = fire_period
        self._fire_cooldown = initial_cooldown

        # Laser-mount state (used only when weapon_type == "laser").
        self.laser_state: str = "idle"  # idle | telegraph | firing | cooldown
        self.laser_timer: float = 0.0
        self.laser_cooldown: float = initial_cooldown  # reuse the stagger
        self.laser_aim: float = math.pi  # radians; default facing left
        self.laser_damage_dealt: bool = False

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def center_x(self) -> float:
        return self.sprite.center_x

    @property
    def center_y(self) -> float:
        return self.sprite.center_y

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if the gun is destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def update(self, delta_time: float) -> bool:
        """Tick the cannon fire cooldown; return True on the frame it is
        ready to fire (the boss builds the player-aimed bullet)."""
        self._fire_cooldown -= delta_time
        if self._fire_cooldown <= 0.0:
            self._fire_cooldown = self._fire_period
            return True
        return False

    def laser_beam_end(self, length: float) -> tuple[float, float]:
        """World-space endpoint of the laser beam from the gun centre along
        ``laser_aim``."""
        return (
            self.center_x + math.cos(self.laser_aim) * length,
            self.center_y + math.sin(self.laser_aim) * length,
        )


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
        settings: BossSettings,
        sprite_scale: float,
    ) -> None:
        self.settings = settings
        self.level_num = level_num

        # HP scales with level.
        self.max_hp: int = settings.hp_base + (level_num - 1) * settings.hp_per_level
        self.hp: int = self.max_hp

        # Body sprite — large, centred in the boss zone.  center_y is a
        # placeholder until place() runs (body.height known after load).
        boss_scale = sprite_scale * settings.scale_factor
        self.body = arcade.Sprite(resource_path(settings.body_sprite), scale=boss_scale)
        self.body.center_x = world_x
        self.body.center_y = 0.0

        self.hardpoints: list[BossGun] = []
        self._sprite_scale = sprite_scale
        self._boss_scale = boss_scale  # guns share the body scale

        # Vertical bob (set via set_oscillation after placement).  A zero
        # amplitude keeps the boss stationary (levels with no vertical room).
        self._osc_center: float = 0.0
        self._osc_amplitude: float = 0.0
        self._osc_speed: float = 0.0
        self._osc_phase: float = 0.0

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
        """Create one ``BossGun`` per ``settings.weapons`` entry.

        Each weapon's offset is its sprite's top-left pixel relative to the
        body's top-left (native px, may be negative).  Converted here to a
        world-space centre (the body renders at ``_boss_scale``, y is up,
        sprites are centre-anchored; each weapon scales with the body and
        uses its own sprite dimensions).  Cannon cooldowns are staggered so
        the guns don't all fire on the same frame.
        """
        scale = self._boss_scale
        # Body top-left in world space (y up).
        body_left = self.body.center_x - self.body.width / 2.0
        body_top = self.body.center_y + self.body.height / 2.0

        weapons = self.settings.weapons
        count = max(1, len(weapons))
        for i, weapon in enumerate(weapons):
            tex = arcade.load_texture(
                resource_path(weapon.sprite),
                hit_box_algorithm=arcade.hitbox.algo_simple,
            )
            gun = BossGun(
                texture=tex,
                scale=scale,
                hp=weapon.hp,
                fire_period=self.settings.fire_cooldown,
                weapon_type=weapon.weapon_type,
                # Stagger so the guns alternate rather than fire in unison.
                initial_cooldown=self.settings.fire_cooldown * (i + 1) / count,
            )
            gw = gun.sprite.width
            gh = gun.sprite.height
            gun.sprite.center_x = body_left + weapon.offset_x * scale + gw / 2.0
            gun.sprite.center_y = body_top - weapon.offset_y * scale - gh / 2.0
            self.hardpoints.append(gun)

    def set_oscillation(self, amplitude: float, speed: float) -> None:
        """Enable a slow vertical sine bob around the current body Y.

        ``amplitude`` (px) and ``speed`` (rad/s) come from the caller, which
        has already clamped the amplitude to the vertical room available in
        the corridor.  An amplitude of 0 leaves the boss stationary.  Call
        after ``place()`` so ``body.center_y`` is the bob centre.
        """
        self._osc_center = self.body.center_y
        self._osc_amplitude = max(0.0, amplitude)
        self._osc_speed = speed
        self._osc_phase = 0.0

    def _apply_oscillation(self, delta_time: float) -> None:
        """Advance the bob and shift the body + every gun sprite by the same
        delta so the whole boss moves rigidly (destroyed guns, removed from
        their SpriteList, are skipped harmlessly).
        """
        if self._osc_amplitude <= 0.0:
            return
        self._osc_phase += delta_time * self._osc_speed
        target_y = self._osc_center + self._osc_amplitude * math.sin(self._osc_phase)
        dy = target_y - self.body.center_y
        if dy == 0.0:
            return
        self.body.center_y = target_y
        for hp in self.hardpoints:
            hp.sprite.center_y += dy

    # ---- per-frame ------------------------------------------------

    def update(
        self,
        ship_x: float,
        ship_y: float,
        delta_time: float,
        can_fire: bool = True,
    ) -> list[BossBullet]:
        """Move the body (slow vertical bob) then tick the cannon mounts,
        returning the player-aimed ``BossBullet``s fired this frame.

        Cannon cooldowns advance every frame, but a bullet is only emitted
        when ``can_fire`` (the view passes False while the boss is still
        off-screen, scrolling in).  Laser mounts are NOT handled here —
        ``RunLevelView._update_boss_lasers`` drives their telegraph/beam
        machine (it holds the laser timings).
        """
        self._apply_oscillation(delta_time)
        bullets: list[BossBullet] = []
        for hp in self.hardpoints:
            if not hp.is_alive or hp.weapon_type != "cannon":
                continue
            ready = hp.update(delta_time)
            if ready and can_fire:
                # Fixed gun — aim the shot at the player's current position.
                angle_rad = math.atan2(ship_y - hp.center_y, ship_x - hp.center_x)
                bullets.append(
                    BossBullet(
                        x=hp.center_x,
                        y=hp.center_y,
                        angle_rad=angle_rad,
                        speed=self.settings.bullet_speed,
                        scale=self._sprite_scale,
                    )
                )
        return bullets
