# Feature Brief — Phase 4: Weapons & Basic Enemies

**Game:** Base Attackers
**Phase:** 4 of 9
**Depends on:** Phase 3 complete — fuel system, docking, HUD bars working
**Output:** Player can shoot, missile silos launch missiles, composite gun
turrets aim and fire at the player, enemy spawn pressure while docked
wired to real enemies, `god_mode` damage bypass, score tracking stub
**agf changes required:** None — all combat logic is game-specific

---

## Goals

1. Player bullet firing — SPACE fires when not docked, bullet travels
   right, SoundManager throttled SFX
2. `MissileSilo` enemy — mounted on floor or ceiling terrain, proximity
   trigger, fires straight up or down, `engine1.png` body,
   `gun08.png` missile sprite
3. `GunTurret` enemy — composite sprite (base + rotating barrel),
   `turretBase_small.png` base, `gun07.png` barrel,
   aims at player, fires bullets, floor and ceiling variants
4. Enemy bullets and missiles collide with player — damage, `god_mode`
   bypass, `_destroy_ship()` at 0 HP
5. Player bullets collide with enemies — damage, explosion, score
6. Wire `_on_dock_pressure_spawn()` — spawns a `GunTurret` patrol
   bullet wave while docked
7. Score display in HUD stub (no persistence yet — Phase 7)
8. Commit, run on both platforms, playtest

---

## Step 0 — Before Writing Any Code

Read in order:
1. `docs/architecture-overview.md`
2. `src/base_attackers/views/run_level.py` — full file. Understand:
   - `on_update()` structure and where to insert enemy update calls
   - `on_draw()` draw order — enemies slot between terrain and ship
   - `on_key_press()` — SPACE gate at line 263 (`is_docked` check exists)
   - `_destroy_ship()` — enemy hits must call this same method
   - `_on_dock_pressure_spawn()` at line 539 — Phase 4 fills this in
   - `_apply_position_bounds()` — enemy bullets also need world-bound culling
3. `src/base_attackers/ships/player_ship.py` — `control_enabled`,
   `take_damage()`, `is_alive`, `collides_with_terrain()`
4. `src/base_attackers/terrain_features/fuel_tower.py` — construction
   pattern (dummy y then adjust) used for enemy placement too
5. `src/base_attackers/game_config.toml` — `sprite_scale = 0.5`,
   `god_mode = false`, effects_volume present
6. `assets/images/PNG/Parts/` — confirmed sprites:
   - `engine1.png` — missile silo body
   - `gun08.png` — missile sprite (placeholder)
   - `turretBase_small.png` — gun turret base
   - `gun00.png` through `gun10.png` — barrel options; pick one per
     turret tier (suggestion: `gun04.png` for tier 1, `gun09.png` for
     tier 2 in later phases)
7. `assets/images/PNG/Lasers/laserBlue01_right.png` — player bullet
8. `assets/images/PNG/Lasers/laserRed01.png` — enemy bullet (upward)
   and `laserRed01_right.png` for horizontal turret shots
9. `agf/src/agf/sound_manager.py` — SoundManager API for throttled SFX
10. `agf/src/agf/sprites/explosion.py` — ExplosionSprite constructor
    signature (already used in `_destroy_ship()`)
11. Use the following sounds for firing: (from space_attackers run_level.py)
we haven't implemented power-ups or extra lives yet, but use these sounds for them when later implemented.
```
_SND_ENEMY_KILLED = "assets/sounds/explosionCrunch_000.wav"
_SND_PLAYER_KILLED = "assets/sounds/explosionCrunch_004.wav"
_SND_ENEMY_SHOOT = "assets/sounds/laserLarge_000.wav"
_SND_PLAYER_SHOOT = "assets/sounds/laserSmall_000.wav"
_SND_POWERUP_PICKUP = "assets/sounds/laserSmall_001.wav"
_SND_EXTRA_LIFE = "assets/sounds/extraLife.wav"
```
Do NOT rely on README files. Read actual source.

---

## Part A — Config Extensions

### A1. Add combat config to `game_config.toml`

```toml
[combat]
player_bullet_speed = 600.0      # px/s rightward
player_fire_cooldown = 0.25      # seconds between shots
player_bullet_damage = 1         # damage per player bullet hit

enemy_bullet_speed = 250.0       # px/s (turret shots)
missile_speed = 200.0            # px/s (straight up or down)
missile_proximity_trigger = 180.0 # px — silo fires when ship within this range
turret_fire_cooldown = 2.0       # seconds between turret shots
turret_aim_jitter = 0.15         # radians added to aim angle (randomness)
turret_rotation_speed = 90.0     # degrees/sec barrel rotation speed

silo_hp = 2
turret_hp = 3
bullet_cull_margin = 64.0        # px outside world bounds before culling
```

### A2. Wire into `GameConfig`

Add a `CombatSettings` dataclass loaded from `[combat]`. Add
`self.combat: CombatSettings` to `GameConfig`. Follow the same pattern
as `ShipSettings` and `FuelTowerSettings`.

---

## Part B — Player Bullet

Create `src/base_attackers/combat/player_bullet.py`.

```
src/base_attackers/combat/
    __init__.py
    player_bullet.py
    enemy_bullet.py
    missile.py
```

### B1. PlayerBullet class

```python
"""PlayerBullet — rightward-travelling projectile fired by the player ship."""
from __future__ import annotations

import arcade
from agf.paths import resource_path


class PlayerBullet(arcade.Sprite):
    SPRITE_PATH = "assets/images/PNG/Lasers/laserBlue01_right.png"

    def __init__(self, x: float, y: float, speed: float, scale: float) -> None:
        super().__init__(
            resource_path(self.SPRITE_PATH),
            scale=scale,
            hit_box_algorithm=arcade.hitbox.algo_simple,
        )
        self.center_x = x
        self.center_y = y
        self._speed = speed

    def update_bullet(self, delta_time: float) -> None:
        self.center_x += self._speed * delta_time
```

- `algo_simple` bounding-box hitbox — pixel-perfect is overkill for a
  small fast projectile (per CLAUDE.md)
- No `SpriteList.update()` — bullets have their own `update_bullet()`
  called explicitly from `RunLevelView`

### B2. Firing logic in `RunLevelView`

Add to `on_key_press()`, after the existing SPACE dock check:

```python
if key == arcade.key.SPACE and not self._ship.is_docked:
    self._try_fire()
```

Add `_try_fire()` method:

```python
def _try_fire(self) -> None:
    """Fire a player bullet if control is enabled and cooldown has elapsed."""
    if not self._ship.control_enabled:
        return
    if self._fire_cooldown > 0.0:
        return
    bullet = PlayerBullet(
        x=self._ship.center_x + self._ship.width / 2.0,
        y=self._ship.center_y,
        speed=self._cfg.combat.player_bullet_speed,
        scale=self._cfg.sprite_scale,
    )
    self._bullet_list.append(bullet)
    self._fire_cooldown = self._cfg.combat.player_fire_cooldown
    self._sound_manager.play("player_shoot")
```

Add to `__init__()`:
```python
self._bullet_list = arcade.SpriteList()   # player bullets
self._fire_cooldown: float = 0.0
```

Tick cooldown in `on_update()` before the death-timer early return:
```python
if self._fire_cooldown > 0.0:
    self._fire_cooldown = max(0.0, self._fire_cooldown - delta_time)
```

### B3. Bullet update and culling in `on_update()`

Add after `_check_canister_pickup()`:

```python
self._update_player_bullets(delta_time)
```

```python
def _update_player_bullets(self, delta_time: float) -> None:
    assert self._terrain_cfg is not None
    cull = self._cfg.combat.bullet_cull_margin
    right_limit = self._terrain_cfg.world_width + cull
    for bullet in list(self._bullet_list):
        bullet.update_bullet(delta_time)
        if bullet.center_x > right_limit:
            bullet.remove_from_sprite_lists()
```

---

## Part C — MissileSilo Enemy

Create `src/base_attackers/enemies/missile_silo.py`.

```
src/base_attackers/enemies/
    __init__.py
    missile_silo.py
    gun_turret.py
```

### C1. Missile sprite (`combat/missile.py`)

```python
"""Missile — travels straight up or down from a silo."""
from __future__ import annotations

import arcade
from agf.paths import resource_path


class Missile(arcade.Sprite):
    SPRITE_PATH = "assets/images/PNG/Parts/gun08.png"

    def __init__(
        self, x: float, y: float, speed: float, direction: float, scale: float
    ) -> None:
        """direction: +1.0 = upward, -1.0 = downward."""
        super().__init__(
            resource_path(self.SPRITE_PATH),
            scale=scale,
            hit_box_algorithm=arcade.hitbox.algo_simple,
        )
        self.center_x = x
        self.center_y = y
        self._speed = speed
        self._direction = direction
        # Rotate sprite to face travel direction.
        self.angle = 0.0 if direction > 0 else 180.0

    def update_missile(self, delta_time: float) -> None:
        self.center_y += self._speed * self._direction * delta_time
```

### C2. MissileSilo class

```python
"""MissileSilo — terrain-mounted enemy that launches missiles on proximity."""
from __future__ import annotations

import arcade
from agf.paths import resource_path
from src.base_attackers.game_config import CombatSettings


class MissileSilo(arcade.Sprite):
    SPRITE_PATH = "assets/images/PNG/Parts/engine1.png"

    def __init__(
        self,
        world_x: float,
        surface: str,       # "floor" or "ceiling"
        cfg: CombatSettings,
        scale: float,
    ) -> None:
        super().__init__(resource_path(self.SPRITE_PATH), scale=scale)
        self.center_x = world_x
        self.center_y = 0.0    # caller sets after construction (same pattern as FuelTower)
        self.surface = surface
        self.cfg = cfg
        self.hp: int = cfg.silo_hp
        # Floor silos point up (angle 0), ceiling silos flip 180.
        self.angle = 0.0 if surface == "floor" else 180.0
        self._fire_ready: bool = True   # resets after each launch

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def check_proximity(self, ship_x: float, ship_y: float) -> bool:
        """True if ship is within trigger range AND silo is ready to fire."""
        if not self._fire_ready:
            return False
        import math
        dist = math.hypot(ship_x - self.center_x, ship_y - self.center_y)
        if dist <= self.cfg.missile_proximity_trigger:
            self._fire_ready = False
            return True
        return False

    def reset_fire(self) -> None:
        """Called after missile has left the screen — silo can fire again."""
        self._fire_ready = True
```

### C3. MissileSilo placement in `RunLevelView`

Same two-step pattern as `FuelTower`. For Phase 4, hardcode positions:

```python
_PHASE4_SILO_POSITIONS = [
    (1200.0, "floor"),
    (2800.0, "floor"),
    (4000.0, "floor"),
]
```

```python
def _place_missile_silos(self) -> None:
    assert self._terrain is not None
    self._silo_list = arcade.SpriteList()
    self._silos: list[MissileSilo] = []
    for x, surface in _PHASE4_SILO_POSITIONS:
        silo = MissileSilo(
            world_x=x,
            surface=surface,
            cfg=self._cfg.combat,
            scale=self._cfg.sprite_scale,
        )
        if surface == "floor":
            floor_y = self._terrain.floor_y_at(x)
            silo.center_y = floor_y + silo.height / 2.0
        else:
            ceil_y = self._terrain.ceiling_y_at(x)
            if ceil_y is None:
                continue    # no ceiling at this position — skip
            silo.center_y = ceil_y - silo.height / 2.0
        self._silo_list.append(silo)
        self._silos.append(silo)
```

Call `_place_missile_silos()` from `on_show_view()` after
`_place_fuel_towers()`.

### C4. Missile SpriteList and update

Add to `__init__()`:
```python
self._missile_list = arcade.SpriteList()
```

Add `_update_missiles()` called from `on_update()`:

```python
def _update_missiles(self, delta_time: float) -> None:
    assert self._terrain_cfg is not None
    cull = self._cfg.combat.bullet_cull_margin
    top_limit = self._terrain_cfg.world_height + cull
    bottom_limit = -cull

    # Check proximity — fire new missiles.
    for silo in self._silos:
        if not silo.is_alive:
            continue
        if silo.check_proximity(self._ship.center_x, self._ship.center_y):
            direction = -1.0 if silo.surface == "ceiling" else 1.0
            missile = Missile(
                x=silo.center_x,
                y=silo.center_y + (silo.height / 2.0) * direction,
                speed=self._cfg.combat.missile_speed,
                direction=direction,
                scale=self._cfg.sprite_scale,
            )
            self._missile_list.append(missile)
            self._sound_manager.play("missile_launch")

    # Move and cull missiles.
    for missile in list(self._missile_list):
        missile.update_missile(delta_time)
        if missile.center_y > top_limit or missile.center_y < bottom_limit:
            missile.remove_from_sprite_lists()
            # Find owning silo and reset so it can fire again.
            for silo in self._silos:
                if not silo._fire_ready and abs(silo.center_x - missile.center_x) < 10.0:
                    silo.reset_fire()
```

---

## Part D — GunTurret Enemy (Composite Sprite)

Create `src/base_attackers/enemies/gun_turret.py`.

### D1. Enemy bullet (`combat/enemy_bullet.py`)

```python
"""EnemyBullet — fired by gun turrets, travels at an angle toward player."""
from __future__ import annotations

import math
import arcade
from agf.paths import resource_path


class EnemyBullet(arcade.Sprite):
    SPRITE_PATH = "assets/images/PNG/Lasers/laserRed01.png"

    def __init__(
        self, x: float, y: float, angle_rad: float, speed: float, scale: float
    ) -> None:
        super().__init__(
            resource_path(self.SPRITE_PATH),
            scale=scale,
            hit_box_algorithm=arcade.hitbox.algo_simple,
        )
        self.center_x = x
        self.center_y = y
        self._vx = math.cos(angle_rad) * speed
        self._vy = math.sin(angle_rad) * speed
        self.angle = math.degrees(angle_rad)

    def update_bullet(self, delta_time: float) -> None:
        self.center_x += self._vx * delta_time
        self.center_y += self._vy * delta_time
```

### D2. GunTurret class

The turret is a **composite** of two sprites: a stationary base and a
rotating barrel. Both are separate `arcade.Sprite` objects managed
together. `GunTurret` is NOT itself an `arcade.Sprite` — it owns two
sprites and exposes them to `RunLevelView` for SpriteList management.

```python
"""GunTurret — composite terrain-mounted enemy.

Two sprites: a stationary base (turretBase_small.png) and a rotating
barrel (gun04.png) that tracks the player.  The barrel rotates toward
the ship at turret_rotation_speed deg/s and fires an EnemyBullet when
the aim angle is within a threshold of the true bearing.

Floor turrets have base.angle=180 (gun points up), ceiling turrets
have base.angle=0 (gun points down).  Sprite origin (angle=0) is the
"natural" orientation of the asset — rotate 180 for floor mounting so
the barrel points upward into the corridor.
"""
from __future__ import annotations

import math
import arcade
from agf.paths import resource_path
from src.base_attackers.game_config import CombatSettings


_BASE_SPRITE = "assets/images/PNG/Parts/turretBase_small.png"
_BARREL_SPRITE = "assets/images/PNG/Parts/gun04.png"
_AIM_THRESHOLD_RAD = math.radians(8.0)   # must be within 8° to fire


class GunTurret:
    """Composite gun turret — owns a base sprite and a barrel sprite."""

    def __init__(
        self,
        world_x: float,
        surface: str,       # "floor" or "ceiling"
        cfg: CombatSettings,
        scale: float,
    ) -> None:
        self.surface = surface
        self.cfg = cfg
        self.hp: int = cfg.turret_hp
        self._fire_cooldown: float = 0.0

        # Base sprite — stationary, flipped for surface.
        self.base = arcade.Sprite(resource_path(_BASE_SPRITE), scale=scale)
        self.base.center_x = world_x
        self.base.center_y = 0.0    # caller sets after construction

        # Barrel sprite — rotates to aim, centred on base top (floor) or
        # base bottom (ceiling).
        self.barrel = arcade.Sprite(resource_path(_BARREL_SPRITE), scale=scale)
        self.barrel.center_x = world_x

        # Starting angle: floor turrets point up (90°), ceiling point down (270°).
        self._aim_angle: float = 90.0 if surface == "floor" else 270.0
        self.barrel.angle = self._aim_angle

        # Floor: base sits on floor, barrel sits above base.
        # Ceiling: base hangs from ceiling, barrel sits below base.
        # _barrel_offset_y is set by caller once base.height is known.
        self._barrel_offset_y: float = 0.0

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def position_on_terrain(self, surface_y: float) -> None:
        """Set base and barrel world positions once base.height is known.

        Call after construction:
            turret.base is loaded, so base.height is available.
            surface_y is floor_y (floor) or ceiling_y (ceiling).
        """
        half_base = self.base.height / 2.0
        half_barrel = self.barrel.height / 2.0
        if self.surface == "floor":
            self.base.center_y = surface_y + half_base
            self.base.angle = 180.0     # flip so base top faces up
            self._barrel_offset_y = half_base + half_barrel + 2.0
        else:
            self.base.center_y = surface_y - half_base
            self.base.angle = 0.0
            self._barrel_offset_y = -(half_base + half_barrel + 2.0)
        self.barrel.center_y = self.base.center_y + self._barrel_offset_y

    def update(self, ship_x: float, ship_y: float, delta_time: float) -> bool:
        """Rotate barrel toward ship. Returns True when the turret fires.

        Caller creates and launches the EnemyBullet on True.
        """
        if not self.is_alive:
            return False

        # Bearing to ship.
        dx = ship_x - self.barrel.center_x
        dy = ship_y - self.barrel.center_y
        target_angle_deg = math.degrees(math.atan2(dy, dx))

        # Rotate toward target at rotation_speed deg/s.
        diff = (target_angle_deg - self._aim_angle + 180.0) % 360.0 - 180.0
        max_rot = self.cfg.turret_rotation_speed * delta_time
        if abs(diff) <= max_rot:
            self._aim_angle = target_angle_deg
        else:
            self._aim_angle += math.copysign(max_rot, diff)
        self._aim_angle %= 360.0
        self.barrel.angle = self._aim_angle

        # Keep barrel centred on base (base never moves).
        self.barrel.center_x = self.base.center_x
        self.barrel.center_y = self.base.center_y + self._barrel_offset_y

        # Fire check.
        if self._fire_cooldown > 0.0:
            self._fire_cooldown -= delta_time
            return False
        angle_diff_rad = abs(
            math.radians(
                (target_angle_deg - self._aim_angle + 180.0) % 360.0 - 180.0
            )
        )
        if angle_diff_rad <= _AIM_THRESHOLD_RAD:
            self._fire_cooldown = self.cfg.turret_fire_cooldown
            return True
        return False

    def fire_bullet(self, speed: float, scale: float) -> "EnemyBullet":
        """Construct and return the bullet — caller adds to SpriteList."""
        from src.base_attackers.combat.enemy_bullet import EnemyBullet
        import math
        angle_rad = math.radians(self._aim_angle)
        jitter = (
            __import__("random").uniform(
                -self.cfg.turret_aim_jitter, self.cfg.turret_aim_jitter
            )
        )
        return EnemyBullet(
            x=self.barrel.center_x,
            y=self.barrel.center_y,
            angle_rad=angle_rad + jitter,
            speed=speed,
            scale=scale,
        )
```

### D3. GunTurret placement in `RunLevelView`

```python
_PHASE4_TURRET_POSITIONS = [
    (600.0,  "floor"),
    (1800.0, "floor"),
    (3400.0, "floor"),
    (5200.0, "floor"),
]
```

```python
def _place_gun_turrets(self) -> None:
    assert self._terrain is not None
    # Two SpriteLists — one for bases, one for barrels.
    # Kept separate so barrels draw on top of bases.
    self._turret_base_list = arcade.SpriteList()
    self._turret_barrel_list = arcade.SpriteList()
    self._turrets: list[GunTurret] = []

    for x, surface in _PHASE4_TURRET_POSITIONS:
        turret = GunTurret(
            world_x=x,
            surface=surface,
            cfg=self._cfg.combat,
            scale=self._cfg.sprite_scale,
        )
        if surface == "floor":
            surface_y = self._terrain.floor_y_at(x)
        else:
            surface_y = self._terrain.ceiling_y_at(x)
            if surface_y is None:
                continue
        turret.position_on_terrain(surface_y)
        self._turret_base_list.append(turret.base)
        self._turret_barrel_list.append(turret.barrel)
        self._turrets.append(turret)
```

Call `_place_gun_turrets()` from `on_show_view()`.

### D4. Enemy bullet SpriteList and turret update

Add to `__init__()`:
```python
self._enemy_bullet_list = arcade.SpriteList()
```

Add `_update_turrets()` called from `on_update()`:

```python
def _update_turrets(self, delta_time: float) -> None:
    assert self._terrain_cfg is not None
    cull = self._cfg.combat.bullet_cull_margin
    world_w = self._terrain_cfg.world_width
    world_h = self._terrain_cfg.world_height

    for turret in self._turrets:
        if not turret.is_alive:
            continue
        fired = turret.update(
            self._ship.center_x, self._ship.center_y, delta_time
        )
        if fired:
            bullet = turret.fire_bullet(
                self._cfg.combat.enemy_bullet_speed,
                self._cfg.sprite_scale,
            )
            self._enemy_bullet_list.append(bullet)
            self._sound_manager.play("enemy_shoot")

    # Move and cull enemy bullets.
    for bullet in list(self._enemy_bullet_list):
        bullet.update_bullet(delta_time)
        if (
            bullet.center_x < -cull
            or bullet.center_x > world_w + cull
            or bullet.center_y < -cull
            or bullet.center_y > world_h + cull
        ):
            bullet.remove_from_sprite_lists()
```

---

## Part E — Collision Detection

Add `_check_combat_collisions()` called from `on_update()` after all
movement updates. Split into subsections for clarity.

### E1. Player bullets vs enemies

Check every frame — must feel responsive.

```python
def _check_player_bullet_hits(self) -> None:
    # vs missile silos
    for bullet in list(self._bullet_list):
        hits = arcade.check_for_collision_with_list(bullet, self._silo_list)
        for silo in hits:
            bullet.remove_from_sprite_lists()
            if silo.take_damage(self._cfg.combat.player_bullet_damage):
                self._on_enemy_destroyed(silo)
            break   # one bullet hits one target

    # vs turret bases (hitting the base damages the turret)
    for bullet in list(self._bullet_list):
        if not bullet.sprite_lists:
            continue   # already consumed
        hits = arcade.check_for_collision_with_list(
            bullet, self._turret_base_list
        )
        for base_sprite in hits:
            bullet.remove_from_sprite_lists()
            # Find the owning GunTurret by base sprite identity.
            turret = next(
                (t for t in self._turrets if t.base is base_sprite), None
            )
            if turret and turret.take_damage(self._cfg.combat.player_bullet_damage):
                self._on_turret_destroyed(turret)
            break
```

### E2. Enemy projectiles vs player

Check every 2 frames for performance — offset from player bullet checks.

```python
def _check_enemy_hits(self) -> None:
    if not self._ship.is_alive:
        return
    # Missiles vs player
    hits = arcade.check_for_collision_with_list(self._ship, self._missile_list)
    for missile in hits:
        missile.remove_from_sprite_lists()
        self._damage_player(1)
        if not self._ship.is_alive:
            return

    # Enemy bullets vs player
    hits = arcade.check_for_collision_with_list(
        self._ship, self._enemy_bullet_list
    )
    for bullet in hits:
        bullet.remove_from_sprite_lists()
        self._damage_player(1)
        if not self._ship.is_alive:
            return
```

### E3. Collision frame stagger

```python
def _check_combat_collisions(self) -> None:
    self._check_player_bullet_hits()   # every frame
    if self._collision_frame % 2 == 0:
        self._check_enemy_hits()       # every other frame
    self._collision_frame += 1
```

Add to `__init__()`:
```python
self._collision_frame: int = 0
```

### E4. Damage and god_mode gate

```python
def _damage_player(self, amount: int) -> None:
    """Apply damage to the ship, respecting god_mode."""
    if self._cfg.game.god_mode:
        return
    if self._ship.take_damage(amount):
        self._destroy_ship()   # reuse existing sequence
```

### E5. Enemy destroyed callbacks

```python
def _on_enemy_destroyed(self, enemy_sprite: arcade.Sprite) -> None:
    """Spawn explosion, remove sprite, add score."""
    from agf.sprites.explosion import ExplosionSprite
    explosion = ExplosionSprite(
        x=enemy_sprite.center_x,
        y=enemy_sprite.center_y,
        scale=max(1.0, self._cfg.sprite_scale * 2.0),
    )
    self._explosion_list.append(explosion)
    enemy_sprite.remove_from_sprite_lists()
    self._score += 100
    self._refresh_hud()

def _on_turret_destroyed(self, turret: GunTurret) -> None:
    """Remove both turret sprites and spawn explosion."""
    from agf.sprites.explosion import ExplosionSprite
    explosion = ExplosionSprite(
        x=turret.base.center_x,
        y=turret.base.center_y,
        scale=max(1.0, self._cfg.sprite_scale * 2.0),
    )
    self._explosion_list.append(explosion)
    turret.base.remove_from_sprite_lists()
    turret.barrel.remove_from_sprite_lists()
    self._score += 150
    self._refresh_hud()
```

Add to `__init__()`:
```python
self._score: int = 0
```

---

## Part F — Dock Pressure Spawn Hook

Wire `_on_dock_pressure_spawn()` to spawn enemy bullets from offscreen
right, aimed at the ship's current position. This simulates a wave of
enemies responding to the player lingering at a tower. Phase 6 replaces
this with real patrol ships.

```python
def _on_dock_pressure_spawn(self) -> None:
    """Spawn a wave of enemy bullets from off-screen right while docked."""
    import random
    from src.base_attackers.combat.enemy_bullet import EnemyBullet
    import math
    assert self._terrain_cfg is not None
    spawn_x = self.window.world_camera.position.x + self.window.width / 2.0 + 50.0
    for _ in range(3):
        spawn_y = self._ship.center_y + random.uniform(-80.0, 80.0)
        dx = self._ship.center_x - spawn_x
        dy = self._ship.center_y - spawn_y
        angle = math.atan2(dy, dx)
        bullet = EnemyBullet(
            x=spawn_x,
            y=spawn_y,
            angle_rad=angle,
            speed=self._cfg.combat.enemy_bullet_speed,
            scale=self._cfg.sprite_scale,
        )
        self._enemy_bullet_list.append(bullet)
    log.info("dock pressure: spawned 3 enemy bullets from right edge")
```

---

## Part G — Sound Setup

### G1. SoundManager in `RunLevelView`

Add to `__init__()`:
```python
from agf.sound_manager import SoundManager
self._sound_manager = SoundManager(self._cfg.effects_volume)
self._sound_manager.load("player_shoot", resource_path("assets/sounds/laser_shoot.wav"), max_concurrent=3)
self._sound_manager.load("enemy_shoot",  resource_path("assets/sounds/enemy_shoot.wav"),  max_concurrent=2)
self._sound_manager.load("missile_launch", resource_path("assets/sounds/missile.wav"),    max_concurrent=2)
self._sound_manager.load("explosion",    resource_path("assets/sounds/explosion.wav"),    max_concurrent=4)
```

**User action required** — confirm actual SFX filenames in
`assets/sounds/`. Use whatever sound files are present; rename the keys
above to match. If a sound is missing, use a different existing one as
a placeholder.

### G2. Play explosion sound in destroy callbacks

In `_on_enemy_destroyed()` and `_on_turret_destroyed()`, add:
```python
self._sound_manager.play("explosion")
```

In `_destroy_ship()`, add:
```python
self._sound_manager.play("explosion")
```

---

## Part H — HUD Score Addition

### H1. Add score Text to `_build_hud()`

```python
sw = self.window.width
self._hud_score = arcade.Text(
    "SCORE  0",
    sw - 200,
    sh - 20,
    font_name=FONT_THIN,
    font_size=14,
    color=arcade.color.WHITE,
)
```

### H2. Update in `_refresh_hud()`

```python
self._hud_score.text = f"SCORE  {self._score}"
```

### H3. Draw in `_draw_hud()`

```python
if self._hud_score:
    self._hud_score.draw()
```

---

## Part I — `on_draw()` Draw Order

Update `on_draw()` to include all new SpriteLists. Order matters —
draw terrain first, enemies above terrain, bullets above enemies, ship
above bullets, explosions on top:

```python
def on_draw(self) -> None:
    self.clear()
    self.window.use_world_camera()
    if self._terrain is not None:
        self._terrain.draw()
    self._tower_list.draw()
    self._canister_list.draw()
    self._silo_list.draw()
    self._turret_base_list.draw()
    self._turret_barrel_list.draw()   # barrels above bases
    self._missile_list.draw()
    self._enemy_bullet_list.draw()
    self._bullet_list.draw()          # player bullets above enemy bullets
    self._ship_list.draw()
    self._scratch_list.draw()
    self._explosion_list.draw()       # always on top

    self.window.use_gui_camera()
    self._draw_hud()
```

---

## Part J — `on_update()` Full Order

The complete update sequence for Phase 4. Order matters for correctness:

```python
def on_update(self, delta_time: float) -> None:
    delta_time = min(delta_time, 1 / 15)
    self._last_delta = delta_time

    # Cooldowns
    if self._dock_cooldown > 0.0:
        self._dock_cooldown = max(0.0, self._dock_cooldown - delta_time)
    if self._fire_cooldown > 0.0:
        self._fire_cooldown = max(0.0, self._fire_cooldown - delta_time)

    # Death sequence
    if self._death_timer > 0.0:
        self._death_timer -= delta_time
        self._explosion_list.update(delta_time)
        if self._death_timer <= 0.0:
            from src.base_attackers.state import GameState
            self._manager.transition(GameState.GAME_OVER)
        return

    # Ship movement
    self._update_ship(delta_time)
    self._ship.drain_fuel(delta_time)
    if self._ship.fuel_empty and not self._ship.is_docked:
        self._apply_fuel_gravity(delta_time)
        if self._death_timer > 0.0:
            return

    # Camera + terrain chunks
    self._update_camera()
    cam_left = self.window.world_camera.position.x - self.window.width / 2.0
    self._terrain.update(cam_left)

    # Docking + collectibles
    self._check_docking()
    self._check_canister_pickup()

    # Enemy updates
    self._update_missiles(delta_time)
    self._update_turrets(delta_time)
    self._update_player_bullets(delta_time)

    # Collision detection
    self._check_combat_collisions()

    # Visuals
    self._explosion_list.update(delta_time)
    self._ship.update_scratch_overlay()
    self._tick_dock_blink(delta_time)
    self._refresh_hud()
```

---

## Part K — CLAUDE.md Updates

After implementing, add to `CLAUDE.md`:

- `GunTurret` is NOT an `arcade.Sprite` — it owns `base` and `barrel`
  sprites separately. Two SpriteLists: `_turret_base_list` and
  `_turret_barrel_list`. Barrels draw on top of bases.
- `turret.position_on_terrain(surface_y)` must be called after
  construction — sets both sprite positions. Same two-step pattern as
  `FuelTower`.
- Enemy collision checks staggered: player bullets every frame,
  enemy projectiles every 2 frames (`_collision_frame % 2`).
- `_damage_player()` is the single gate for all enemy damage —
  respects `god_mode`, calls `_destroy_ship()` at 0 HP.
- `_destroy_ship()` guards against double-trigger (`_death_timer > 0`).
  All damage paths must use `_damage_player()`, not `ship.take_damage()`
  directly.
- `_on_dock_pressure_spawn()` spawns off-screen bullet wave in Phase 4.
  Phase 6 replaces with patrol ships.
- Score is tracked in `self._score` — no persistence yet (Phase 7).
- `god_mode = true` in `game_config.toml` disables all enemy damage for
  combat tuning sessions.

---

## Commit Sequence

```bash
git commit -m "feat: CombatSettings config dataclass and game_config.toml entries"
git commit -m "feat: PlayerBullet, EnemyBullet, Missile combat sprites"
git commit -m "feat: MissileSilo enemy with proximity trigger"
git commit -m "feat: GunTurret composite enemy with rotating barrel"
git commit -m "feat: RunLevelView enemy placement and update loops"
git commit -m "feat: combat collision detection with god_mode gate"
git commit -m "feat: dock pressure spawn hook wired to enemy bullets"
git commit -m "feat: score tracking and HUD score display"
git commit -m "chore: update CLAUDE.md with Phase 4 combat patterns"
```

---

## Playtest Checklist

**Player shooting**
- [ ] SPACE fires a bullet when not docked
- [ ] SPACE undocks (not fires) when docked
- [ ] Fire cooldown prevents bullet spam — rate feels right
- [ ] Bullet travels rightward and disappears at world edge
- [ ] Bullet SFX plays and is throttled (no crackling with rapid fire)

**Missile silos**
- [ ] Three silos visible on terrain at correct floor positions
- [ ] Flying near a silo triggers a missile launch
- [ ] Missile travels straight up and disappears at world top
- [ ] Silo resets and can fire again after missile exits
- [ ] Player bullet hitting a silo damages it — two hits destroy it
- [ ] Destroyed silo plays explosion and is removed

**Gun turrets**
- [ ] Four turrets visible — base flush on terrain, barrel above base
- [ ] Barrel rotates to track player — smooth, not instant
- [ ] Turret fires when barrel is aimed within threshold
- [ ] Enemy bullet travels toward where ship was when fired
- [ ] Jitter makes shots slightly imprecise — not always dead-on
- [ ] Player bullet hitting base damages turret — three hits destroy it
- [ ] Destroyed turret removes both sprites, plays explosion

**Collision and damage**
- [ ] Enemy bullet hitting ship reduces HP by 1
- [ ] Missile hitting ship reduces HP by 1
- [ ] Ship at 0 HP triggers destruction sequence (same as terrain hit)
- [ ] `god_mode = true` in config — damage never applied, can test combat
      freely
- [ ] `god_mode = false` — damage works correctly

**Dock pressure**
- [ ] Docking at a tower — after `spawn_pressure_interval` seconds,
      enemy bullets appear from right side of screen
- [ ] Pressure bullets travel toward ship position
- [ ] Log message confirms hook is firing

**Score**
- [ ] Score increments on silo destroy (100)
- [ ] Score increments on turret destroy (150)
- [ ] Score displays correctly in top-right HUD

**Performance**
- [ ] Stable 60fps with all enemies active and bullets on screen
- [ ] No stutter when chunks load/unload at camera edges

---

## User Actions Required (Summary)

1. **Confirm SFX filenames** in `assets/sounds/` and update the
   `SoundManager.load()` calls in Part G to match actual filenames
2. **Select barrel sprite** — brief uses `gun04.png`; look at the
   `gun00`–`gun10` options and pick whichever looks best as a gun barrel
   at `sprite_scale=0.5`. Update `_BARREL_SPRITE` in `gun_turret.py`
3. **Tune combat config** during playtest:
   - `missile_proximity_trigger` — how close before silo fires?
   - `turret_fire_cooldown` — how often do turrets shoot?
   - `turret_rotation_speed` — how fast does the barrel track?
   - `turret_aim_jitter` — how inaccurate are turret shots?
4. **Run on both Windows and Ubuntu** — confirm sprite rotation renders
   correctly on both (barrel angle arithmetic is the most likely
   cross-platform difference)
5. **Report back to Claude.ai** before Phase 5:
   - Final tuned combat config values
   - Whether the composite turret approach looked good or needs adjustment
   - Whether ceiling-mounted enemies are needed in Phase 4 or can wait
   - Any collision edge cases observed
