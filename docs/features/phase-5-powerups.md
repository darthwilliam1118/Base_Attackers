# Feature Brief — Phase 5: World-Space Power-Up Spawner

**Game:** Base Attackers
**Phase:** 5 of 9
**Depends on:** Phase 4 complete — combat working, score tracking in place
**Output:** Six power-up types drifting down from the top of the visible
window in world space, collected on contact, fuel canisters procedurally
spawned replacing hardcoded Phase 3 positions, agf PowerUpSpawner extended
with a world-space mode that is additive and does not affect Space Attackers
**agf changes required:** Yes — world-space spawner mode added to agf first

---

## Goals

1. Extend agf `PowerUpSpawner` with a world-space mode — spawn at world
   coordinates within the camera view, drift downward, cull on floor
   contact or left-edge exit
2. Implement `BAPowerUpManager` in Base Attackers — subclasses agf
   `PowerUpManager`, overrides `create_effect()` for all six types
3. Wire all six power-up types — health, fuel canister, big gun, rapid
   fire, multi-shot, shield — reusing agf effect categories
4. Replace hardcoded `_PHASE3_CANISTER_POSITIONS` with procedural
   spawner — fuel canisters now spawn dynamically
5. Time-based spawn interval keyed to level number — higher levels get
   more power-ups; spawn within current camera view window
6. Power-ups disappear silently on floor terrain contact
7. Pickup SFX and brief HUD flash on collection
8. Commit, run on both platforms, playtest

---

## Step 0 — Before Writing Any Code

Read in order:
1. `docs/architecture-overview.md`
2. `agf/src/agf/powerups/` — read every file in this directory:
   - `manager.py` — `PowerUpManager.create_effect()` raises
     `NotImplementedError` by design; Base Attackers must subclass
   - `spawner.py` — current screen-space spawner; Phase 5 extends this
   - `sprite.py` — `PowerUpSprite` construction and drift logic
   - `effects/` — all five effect category base classes; understand
     contracts before writing concrete effects
3. `agf/src/agf/powerups/effects/` — read each effect category:
   - `stat_modifier.py` — `StatModifierEffect` (rapid fire, big gun)
   - `behavior.py` — `BehaviorEffect` (multi-shot)
   - `overlay.py` — `OverlayEffect` (shield)
   - `instant.py` — `InstantEffect` (health restore, fuel canister)
   - `constraint.py` — `ConstraintEffect` (not used in Phase 5)
4. `src/base_attackers/views/run_level.py` — understand:
   - `_place_fuel_canisters()` at line 581 — this is removed in Phase 5
   - `_check_canister_pickup()` at line 739 — replaced by spawner pickup
   - `on_show_view()` — spawner init goes here
   - `on_update()` line 316 — spawner tick goes here, must respect
     `self._paused` (already guarded by the pause early-return at line 274)
   - `on_draw()` line 333 — power-up SpriteList draw order
   - `_play_sfx()` at line 930 — pickup sound follows this pattern
5. `src/base_attackers/game_config.toml` — `sprite_scale = 0.5`,
   `effects_volume`, `[level_1]` has `world_width` and `world_height`
6. `assets/images/PNG/Power-ups/` — confirmed sprites:
   - `bolt_gold.png` — fuel canister (already used in Phase 3)
   - `bolt_silver.png` — rapid fire
   - `bolt_bronze.png` — big gun
   - `star_gold.png` — multi-shot
   - `powerupBlue_shield.png` — shield
   - `pill_red.png` — health restore
   - `star_silver.png` — spare / future use
   - `star_bronze.png` — spare / future use

Do NOT rely on README files. Read actual source.

---

## Part A — agf Changes (agf VS Code window first)

Read `agf/src/agf/powerups/spawner.py` carefully before writing
anything. The existing spawner drops sprites from the top of the screen
in screen space. The world-space mode is an additive subclass — the
existing class and Space Attackers are completely unaffected.

### A1. Create `agf/src/agf/powerups/world_spawner.py`

```python
"""WorldSpacePowerUpSpawner — spawns power-up sprites at world coordinates.

Unlike the base PowerUpSpawner (which spawns at screen-top in screen
space), this spawner places sprites within the current camera view
window at world coordinates.  Sprites drift downward at a randomised
speed and are culled when they contact the floor terrain or exit the
left edge of the camera view.

This class is intentionally agf-generic — it knows nothing about Base
Attackers terrain, enemies, or game state.  The game passes in:
  - a weight table (type_name -> weight) built per-level
  - a camera_rect callback returning (cam_left, cam_bottom, cam_right, cam_top)
    in world coordinates each frame
  - a floor_y_at(world_x) callback for terrain floor lookup
  - spawn_interval computed externally (level-keyed)

Design notes:
  - Spawning is time-based; spawn_interval is set by the game per level.
  - Sprites spawn at a random world X within the camera view and at
    cam_top + a small offset so they appear to fall from the sky.
  - Sprites drift straight downward at fall_speed (px/s).  No angle
    drift — world-space falling objects read more naturally than the
    angled screen-space drops in Space Attackers.
  - Sprites are culled when center_y <= floor_y_at(center_x) OR when
    center_x < cam_left - cull_margin (scrolled off left edge).
  - ShapeElementList is NOT used anywhere here.
  - SpriteList does NOT use spatial hashing — power-ups move every frame.
"""
from __future__ import annotations

import random
from collections.abc import Callable
from typing import TYPE_CHECKING

import arcade

if TYPE_CHECKING:
    from agf.powerups.sprite import PowerUpSprite


class WorldSpacePowerUpSpawner:
    """Manages timed spawning and lifetime of world-space power-up sprites.

    Parameters
    ----------
    weight_table:
        Dict mapping power-up type name (str) to spawn weight (int).
        Empty dict = no spawns (used for level 1).
    camera_rect:
        Callable returning (cam_left, cam_bottom, cam_right, cam_top)
        in world coordinates.  Called each frame during update.
    floor_y_at:
        Callable(world_x: float) -> float returning the terrain floor Y
        at a given world X.  Used for floor-contact culling.
    spawn_interval:
        Seconds between spawn attempts.  Set by game per level.
    fall_speed_min / fall_speed_max:
        Randomised downward drift speed range (px/s).
    sprite_scale:
        Arcade sprite scale passed to PowerUpSprite.
    cull_margin:
        Extra px past cam_left before a sprite is culled (default 64).
    """

    def __init__(
        self,
        weight_table: dict[str, int],
        camera_rect: Callable[[], tuple[float, float, float, float]],
        floor_y_at: Callable[[float], float],
        spawn_interval: float,
        fall_speed_min: float = 40.0,
        fall_speed_max: float = 100.0,
        sprite_scale: float = 0.5,
        cull_margin: float = 64.0,
    ) -> None:
        self._weights = weight_table
        self._camera_rect = camera_rect
        self._floor_y_at = floor_y_at
        self.spawn_interval: float = spawn_interval
        self._fall_speed_min = fall_speed_min
        self._fall_speed_max = fall_speed_max
        self._sprite_scale = sprite_scale
        self._cull_margin = cull_margin

        self._timer: float = 0.0
        # Start at a random offset so multiple levels don't all spawn at t=0.
        self._timer = random.uniform(0.0, spawn_interval)

        self.sprite_list: arcade.SpriteList = arcade.SpriteList()
        # Parallel list of per-sprite fall speeds (SpriteList has no
        # per-sprite metadata — same pattern as ProceduralStarField in agf).
        self._fall_speeds: list[float] = []
        # Parallel list of type names for pickup identification.
        self._type_names: list[str] = []

    # ---- public API ------------------------------------------------

    def update(self, delta_time: float) -> None:
        """Tick the spawn timer and move/cull active sprites."""
        if not self._weights:
            return

        # Move sprites downward and cull.
        cam_left, _, _, _ = self._camera_rect()
        for sprite, speed in zip(list(self.sprite_list), list(self._fall_speeds)):
            sprite.center_y -= speed * delta_time
            # Cull: hit floor terrain.
            floor_y = self._floor_y_at(sprite.center_x)
            if sprite.center_y <= floor_y:
                self._remove_sprite(sprite)
                continue
            # Cull: scrolled off left edge.
            if sprite.center_x < cam_left - self._cull_margin:
                self._remove_sprite(sprite)

        # Spawn timer.
        self._timer -= delta_time
        if self._timer <= 0.0:
            self._timer = self.spawn_interval
            self._try_spawn()

    def collect(self, sprite: arcade.Sprite) -> str | None:
        """Remove *sprite* from the list and return its type name, or None
        if it is not managed by this spawner.  Called by the game on
        collision with the player ship.
        """
        if sprite not in self.sprite_list:
            return None
        idx = list(self.sprite_list).index(sprite)
        type_name = self._type_names[idx]
        self._remove_sprite(sprite)
        return type_name

    def clear(self) -> None:
        """Remove all active sprites — call on level end or game over."""
        for sprite in list(self.sprite_list):
            sprite.remove_from_sprite_lists()
        self._fall_speeds.clear()
        self._type_names.clear()

    # ---- internals -------------------------------------------------

    def _try_spawn(self) -> None:
        """Pick a type by weight and spawn one sprite within the camera view."""
        type_name = self._weighted_choice()
        if type_name is None:
            return
        cam_left, cam_bottom, cam_right, cam_top = self._camera_rect()
        # Random X within the current camera view.
        spawn_x = random.uniform(cam_left + 32.0, cam_right - 32.0)
        # Spawn just above the top of the camera view.
        spawn_y = cam_top + 16.0
        self._spawn_sprite(type_name, spawn_x, spawn_y)

    def _spawn_sprite(self, type_name: str, x: float, y: float) -> None:
        """Instantiate a PowerUpSprite and add it to the managed list."""
        from agf.powerups.sprite import PowerUpSprite
        sprite = PowerUpSprite(
            type_name=type_name,
            scale=self._sprite_scale,
        )
        sprite.center_x = x
        sprite.center_y = y
        self.sprite_list.append(sprite)
        speed = random.uniform(self._fall_speed_min, self._fall_speed_max)
        self._fall_speeds.append(speed)
        self._type_names.append(type_name)

    def _remove_sprite(self, sprite: arcade.Sprite) -> None:
        """Remove sprite and its parallel-list entries."""
        if sprite not in self.sprite_list:
            return
        idx = list(self.sprite_list).index(sprite)
        sprite.remove_from_sprite_lists()
        if idx < len(self._fall_speeds):
            self._fall_speeds.pop(idx)
        if idx < len(self._type_names):
            self._type_names.pop(idx)

    def _weighted_choice(self) -> str | None:
        """Return a type name sampled by weight, or None if table is empty."""
        if not self._weights:
            return None
        names = list(self._weights.keys())
        weights = list(self._weights.values())
        return random.choices(names, weights=weights, k=1)[0]
```

### A2. Update `PowerUpSprite` to accept `type_name` without a texture path

Read `agf/src/agf/powerups/sprite.py` first. `PowerUpSprite` currently
expects a texture path. The world-space spawner needs to instantiate it
by type name only — the sprite looks up its own texture from a registry.

If `PowerUpSprite` already has a type-name registry, use it directly and
skip this step.

If it does not, add a class-level dict `_TEXTURE_REGISTRY: dict[str, str]`
mapping type names to asset paths, and a `register(type_name, path)`
classmethod. Games call `PowerUpSprite.register(...)` at startup before
any sprites are spawned. The spawner then calls
`PowerUpSprite(type_name=name, scale=scale)` and the sprite loads its
own texture from the registry.

This is an additive change — existing `PowerUpSprite` construction in
Space Attackers is unaffected if the old constructor signature is kept
with a default of `None` for the path parameter.

### A3. Export from agf

Add to `agf/src/agf/powerups/__init__.py`:
```python
from agf.powerups.world_spawner import WorldSpacePowerUpSpawner
```

Add to `agf/src/agf/__init__.py`:
```python
from agf.powerups.world_spawner import WorldSpacePowerUpSpawner
```

### A4. Commit agf

```bash
cd path/to/arcade-game-framework
git add -A
git commit -m "feat: WorldSpacePowerUpSpawner — world-coord power-up spawning"
git push
```

Do NOT tag agf yet — that happens at Phase 9.

### A5. Update Base Attackers agf pin

Update the SHA in `Base_Attackers/pyproject.toml` to the new agf commit,
then `pip install -e ".[dev]"`.

---

## Part B — Config Extensions

### B1. Add power-up config to `game_config.toml`

```toml
[powerups]
fall_speed_min = 40.0
fall_speed_max = 100.0

# Spawn interval per level (seconds). Higher levels = more frequent.
# Level 1: one spawn every 20s. Level 3+: one every 8s.
spawn_interval_level_1 = 20.0
spawn_interval_level_2 = 14.0
spawn_interval_level_3 = 10.0
spawn_interval_default = 8.0   # level 4+

# Effect durations (seconds) for timed effects.
rapid_fire_duration = 8.0
big_gun_duration = 10.0
multi_shot_duration = 8.0
shield_duration = 12.0

# Stat modifier magnitudes.
rapid_fire_cooldown_multiplier = 0.4   # fire_cooldown * this value
big_gun_damage_bonus = 1               # extra damage per shot
```

### B2. Add power-up weight tables per level to `game_config.toml`

Weight tables control which types can spawn and how often. Level 1 has
no power-ups (empty table). Types unlock one per level from level 2.

```toml
[powerups.weights.level_1]
# Empty — no power-ups spawn on level 1.

[powerups.weights.level_2]
fuel_canister = 5
health = 3

[powerups.weights.level_3]
fuel_canister = 5
health = 3
rapid_fire = 2

[powerups.weights.level_4]
fuel_canister = 4
health = 3
rapid_fire = 2
big_gun = 2

[powerups.weights.level_5]
fuel_canister = 4
health = 2
rapid_fire = 2
big_gun = 2
multi_shot = 1
shield = 1

[powerups.weights.default]
fuel_canister = 3
health = 2
rapid_fire = 2
big_gun = 2
multi_shot = 2
shield = 2
```

### B3. Wire into `GameConfig`

Add a `PowerUpSettings` dataclass. The weight tables are
`dict[str, dict[str, int]]` keyed by `"level_N"` and `"default"`.
Add a helper method `weight_table_for_level(level: int) -> dict[str, int]`
that returns the matching table or `"default"` if the level has no
specific table.

Add a helper `spawn_interval_for_level(level: int) -> float` that
returns the configured interval for the given level number, falling
back to `spawn_interval_default`.

---

## Part C — Power-Up Effects (Base Attackers concrete implementations)

Create `src/base_attackers/powerups/` package.

```
src/base_attackers/powerups/
    __init__.py
    effects.py       — all six concrete effect classes
    manager.py       — BAPowerUpManager subclassing agf PowerUpManager
```

### C1. Read agf effect base classes before writing

Understand `StatModifierEffect`, `InstantEffect`, `OverlayEffect`,
`BehaviorEffect` contracts. Each has specific methods to override.
Do not guess — read the source.

### C2. Concrete effect classes (`effects.py`)

```python
"""Base Attackers concrete power-up effects.

Six types:
  HealthRestoreEffect   — InstantEffect: restore 1 HP (capped at MAX_HP)
  FuelCanisterEffect    — InstantEffect: restore fuel_canister_restore fuel
  RapidFireEffect       — StatModifierEffect: reduce fire_cooldown by multiplier
  BigGunEffect          — StatModifierEffect: increase bullet damage
  MultiShotEffect       — BehaviorEffect: fire 3 bullets in a spread
  ShieldEffect          — OverlayEffect: absorb hits, degrade through 3 textures
"""
from __future__ import annotations
# ... imports from agf.powerups.effects ...
```

**HealthRestoreEffect** (InstantEffect):
- `apply(ship)`: `ship.hp = min(ship.MAX_HP, ship.hp + 1)`
- No duration — applied immediately and done

**FuelCanisterEffect** (InstantEffect):
- `apply(ship)`: `ship.add_fuel(cfg.fuel_canister_restore)`
- No duration

**RapidFireEffect** (StatModifierEffect):
- Reduces `_fire_cooldown` rate — store original `player_fire_cooldown`
  on apply, multiply by `rapid_fire_cooldown_multiplier`, restore on
  expire
- Duration: `rapid_fire_duration` seconds
- One StatModifierEffect at a time stacks — multiple RapidFire effects
  stack (per agf PowerUpManager rules)

**BigGunEffect** (StatModifierEffect):
- Adds `big_gun_damage_bonus` to `player_bullet_damage` on apply,
  restores on expire
- Duration: `big_gun_duration` seconds

**MultiShotEffect** (BehaviorEffect):
- Overrides firing — when active, `_try_fire()` fires 3 bullets in a
  spread (-10°, 0°, +10°) instead of 1
- Duration: `multi_shot_duration` seconds
- One BehaviorEffect at a time — new one replaces old (per agf rules)

**ShieldEffect** (OverlayEffect):
- Absorbs hits using the three shield textures already in assets:
  `Effects/shield3.png` (full), `Effects/shield2.png`, `Effects/shield1.png`
- 3 hit points; each hit degrades to next texture; at 0 shield is removed
- Duration cap: `shield_duration` seconds OR 3 hits, whichever comes first
- One OverlayEffect at a time

### C3. BAPowerUpManager (`manager.py`)

```python
"""BAPowerUpManager — Base Attackers power-up manager.

Subclasses agf PowerUpManager and overrides create_effect() to
instantiate the correct concrete effect for each type name.
"""
from __future__ import annotations

from agf.powerups.manager import PowerUpManager
from src.base_attackers.powerups.effects import (
    HealthRestoreEffect,
    FuelCanisterEffect,
    RapidFireEffect,
    BigGunEffect,
    MultiShotEffect,
    ShieldEffect,
)
from src.base_attackers.game_config import PowerUpSettings


class BAPowerUpManager(PowerUpManager):
    def __init__(self, cfg: PowerUpSettings) -> None:
        super().__init__()
        self._cfg = cfg

    def create_effect(self, type_name: str):
        match type_name:
            case "health":
                return HealthRestoreEffect()
            case "fuel_canister":
                return FuelCanisterEffect(self._cfg.fuel_canister_restore)
            case "rapid_fire":
                return RapidFireEffect(
                    duration=self._cfg.rapid_fire_duration,
                    cooldown_multiplier=self._cfg.rapid_fire_cooldown_multiplier,
                )
            case "big_gun":
                return BigGunEffect(
                    duration=self._cfg.big_gun_duration,
                    damage_bonus=self._cfg.big_gun_damage_bonus,
                )
            case "multi_shot":
                return MultiShotEffect(duration=self._cfg.multi_shot_duration)
            case "shield":
                return ShieldEffect(duration=self._cfg.shield_duration)
            case _:
                raise ValueError(f"Unknown power-up type: {type_name!r}")
```

---

## Part D — PowerUpSprite Texture Registry

Register all six textures at game startup in `game.py` or in
`RunLevelView.__init__()` before any sprites are spawned:

```python
from agf.powerups.sprite import PowerUpSprite
from agf.paths import resource_path

_POWERUP_TEXTURES = {
    "health":       "assets/images/PNG/Power-ups/pill_red.png",
    "fuel_canister":"assets/images/PNG/Power-ups/bolt_gold.png",
    "rapid_fire":   "assets/images/PNG/Power-ups/bolt_silver.png",
    "big_gun":      "assets/images/PNG/Power-ups/bolt_bronze.png",
    "multi_shot":   "assets/images/PNG/Power-ups/star_gold.png",
    "shield":       "assets/images/PNG/Power-ups/powerupBlue_shield.png",
}

for type_name, path in _POWERUP_TEXTURES.items():
    PowerUpSprite.register(type_name, resource_path(path))
```

Do this registration once — before `on_show_view()` runs. The right
place is `RunLevelView.__init__()` so it runs before any level starts.

---

## Part E — RunLevelView Integration

### E1. Remove Phase 3 canister code

- Remove `_PHASE3_CANISTER_POSITIONS` constant (line 74)
- Remove `_place_fuel_canisters()` method (line 581)
- Remove the call to `_place_fuel_canisters()` in `on_show_view()` (line 253)
- Remove `_check_canister_pickup()` method (line 739)
- Remove `self._canister_list` SpriteList and its draw call in `on_draw()`
- Remove the call to `_check_canister_pickup()` in `on_update()` (line 314)

### E2. Add spawner and manager to `__init__()`

```python
from agf.powerups.world_spawner import WorldSpacePowerUpSpawner
from src.base_attackers.powerups.manager import BAPowerUpManager

# Power-up manager — tracks active effects on the ship.
self._powerup_manager = BAPowerUpManager(cfg.powerups)

# Spawner — built in on_show_view once terrain and camera are ready.
self._powerup_spawner: WorldSpacePowerUpSpawner | None = None
```

### E3. Build spawner in `on_show_view()`

Add after `_place_gun_turrets()`:

```python
self._powerup_spawner = self._build_powerup_spawner()
```

```python
def _build_powerup_spawner(self) -> WorldSpacePowerUpSpawner:
    assert self._terrain is not None and self._terrain_cfg is not None
    level_num = 1   # Phase 7 passes real level number
    weight_table = self._cfg.powerups.weight_table_for_level(level_num)
    interval = self._cfg.powerups.spawn_interval_for_level(level_num)

    def camera_rect() -> tuple[float, float, float, float]:
        sw = self.window.width
        sh = self.window.height
        cx = self.window.world_camera.position.x
        cy = self.window.world_camera.position.y
        return cx - sw / 2.0, cy - sh / 2.0, cx + sw / 2.0, cy + sh / 2.0

    return WorldSpacePowerUpSpawner(
        weight_table=weight_table,
        camera_rect=camera_rect,
        floor_y_at=self._terrain.floor_y_at,
        spawn_interval=interval,
        fall_speed_min=self._cfg.powerups.fall_speed_min,
        fall_speed_max=self._cfg.powerups.fall_speed_max,
        sprite_scale=self._cfg.sprite_scale,
    )
```

### E4. Spawner tick in `on_update()`

Add after `_check_docking()` (before combat updates), inside the
existing pause guard (pause early-return at line 274 already covers this):

```python
if self._powerup_spawner is not None:
    self._powerup_spawner.update(delta_time)
    self._check_powerup_pickup()
```

### E5. Pickup check

```python
def _check_powerup_pickup(self) -> None:
    if self._powerup_spawner is None:
        return
    hits = arcade.check_for_collision_with_list(
        self._ship, self._powerup_spawner.sprite_list
    )
    for sprite in hits:
        type_name = self._powerup_spawner.collect(sprite)
        if type_name is None:
            continue
        effect = self._powerup_manager.create_effect(type_name)
        self._powerup_manager.apply_effect(effect, self._ship)
        self._on_powerup_collected(type_name)

def _on_powerup_collected(self, type_name: str) -> None:
    """Play pickup SFX and flash HUD label."""
    self._play_sfx(self._sm_player_shoot, self._snd_player_shoot)
    # HUD flash — show type name for 2 seconds.
    self._powerup_flash_label = type_name.replace("_", " ").upper()
    self._powerup_flash_timer = 2.0
```

Add to `__init__()`:
```python
self._powerup_flash_label: str = ""
self._powerup_flash_timer: float = 0.0
```

### E6. Tick flash timer in `on_update()`

Add after pickup check:
```python
if self._powerup_flash_timer > 0.0:
    self._powerup_flash_timer -= delta_time
    if self._powerup_flash_timer <= 0.0:
        self._powerup_flash_label = ""
```

### E7. Tick active effects in `on_update()`

The power-up manager must tick each frame to expire timed effects:

```python
self._powerup_manager.update(delta_time, self._ship)
```

Add this after the flash timer tick.

### E8. Wire active effects into combat

**RapidFireEffect** — affects `_fire_cooldown` interval. The manager
applies the multiplier to `player_fire_cooldown` on the ship or via a
property. Read how agf `StatModifierEffect` communicates the modified
value — apply it in `_try_fire()`:

```python
# In _try_fire(), replace the hardcoded config lookup:
cooldown = self._powerup_manager.get_fire_cooldown(
    self._cfg.combat.player_fire_cooldown
)
# Falls back to cfg value when no RapidFireEffect active.
```

**BigGunEffect** — affects bullet damage in `_check_player_bullet_hits()`:

```python
damage = self._powerup_manager.get_bullet_damage(
    self._cfg.combat.player_bullet_damage
)
```

**MultiShotEffect** — `_try_fire()` checks manager before firing:

```python
if self._powerup_manager.has_behavior_effect("multi_shot"):
    self._fire_multi_shot()
else:
    self._fire_single_shot()
```

```python
def _fire_multi_shot(self) -> None:
    """Fire three bullets in a -10°/0°/+10° spread."""
    import math
    angles = [-10.0, 0.0, 10.0]
    for angle_deg in angles:
        angle_rad = math.radians(angle_deg)
        speed = self._cfg.combat.player_bullet_speed
        bullet = PlayerBullet(
            x=self._ship.center_x + self._ship.width / 2.0,
            y=self._ship.center_y,
            speed=speed * math.cos(angle_rad),
            scale=self._cfg.sprite_scale,
        )
        # Add vertical velocity component for spread.
        bullet._vy = speed * math.sin(angle_rad)  # see note below
        self._bullet_list.append(bullet)
    self._play_sfx(self._sm_player_shoot, self._snd_player_shoot)
```

**Note on multi-shot bullet velocity:** `PlayerBullet` currently only
moves in X. Add `_vy: float = 0.0` to `PlayerBullet` and update
`update_bullet()` to also apply `self.center_y += self._vy * delta_time`.
This is a small additive change to the existing bullet class.

**ShieldEffect** — check `self._powerup_manager.has_overlay_effect("shield")`
in `_damage_player()` before applying damage. If shield is active, absorb
the hit via the effect instead:

```python
def _damage_player(self, amount: int) -> None:
    if self._cfg.god_mode:
        return
    shield = self._powerup_manager.get_overlay_effect("shield")
    if shield is not None:
        absorbed = shield.absorb_hit()   # returns True if shield took the hit
        if absorbed:
            return
    if self._ship.take_damage(amount):
        self._destroy_ship()
        self._play_sfx(self._sm_player_boom, self._snd_player_boom)
```

**HealthRestoreEffect and FuelCanisterEffect** — applied immediately in
`_on_powerup_collected()` via `manager.apply_effect()`. No per-frame
wiring needed.

### E9. Power-up draw in `on_draw()`

Add to the world-camera section, between `_canister_list` (now removed)
and `_silo_list`:

```python
if self._powerup_spawner is not None:
    self._powerup_spawner.sprite_list.draw()
```

Draw shield overlay in world-camera space, centred on ship, after ship
draw:

```python
shield = self._powerup_manager.get_overlay_effect("shield")
if shield is not None and shield.overlay_sprite is not None:
    shield.overlay_sprite.center_x = self._ship.center_x
    shield.overlay_sprite.center_y = self._ship.center_y
    shield.overlay_sprite.draw()
```

### E10. Power-up flash in `_draw_hud()`

Add a `_hud_powerup_flash` Text object in `_build_hud()`:

```python
self._hud_powerup_flash = arcade.Text(
    "",
    sw / 2,
    sh - 20,
    arcade.color.YELLOW,
    font_size=16,
    font_name=FONT_THIN,
    anchor_x="center",
)
```

Update in `_refresh_hud()`:
```python
self._hud_powerup_flash.text = self._powerup_flash_label
```

Draw in `_draw_hud()` alongside other HUD text.

### E11. Spawner cleanup on level end / game over

Add to `_destroy_ship()` and any level-complete transition:
```python
if self._powerup_spawner is not None:
    self._powerup_spawner.clear()
self._powerup_manager.clear_all_effects(self._ship)
```

---

## Part F — CLAUDE.md Updates

After implementing, add to `CLAUDE.md`:

- `WorldSpacePowerUpSpawner` is in `agf.powerups.world_spawner` — additive,
  does not change Space Attackers' `PowerUpSpawner`
- `BAPowerUpManager` is in `src/base_attackers/powerups/manager.py` —
  must subclass agf `PowerUpManager` and override `create_effect()`
- `PowerUpSprite.register(type_name, path)` must be called for each type
  before any sprites are spawned — do this in `RunLevelView.__init__()`
- Spawner `sprite_list` uses NO spatial hashing — power-ups move every frame
- Shield overlay sprite is positioned manually each frame in `on_draw()` —
  it is NOT in a SpriteList
- `_powerup_manager.update(delta_time, ship)` must be called every frame
  to expire timed effects
- `_damage_player()` checks shield before applying damage — this is the
  single gate; do not bypass it
- Multi-shot adds `_vy` to `PlayerBullet` — update `update_bullet()` to
  apply vertical drift or spread shots won't work
- Spawner is cleared on death and level complete — do not forget this
  or sprites persist into GAME_OVER

---

## Commit Sequence

```bash
# agf repo
git commit -m "feat: WorldSpacePowerUpSpawner for world-coord power-up drops"
git commit -m "feat: PowerUpSprite type-name registry and register() classmethod"

# Base Attackers
git commit -m "chore: update agf pin to include WorldSpacePowerUpSpawner"
git commit -m "feat: PowerUpSettings config dataclass and TOML weight tables"
git commit -m "feat: concrete power-up effects — health, fuel, rapid fire, big gun, multi-shot, shield"
git commit -m "feat: BAPowerUpManager wiring create_effect() for all six types"
git commit -m "feat: RunLevelView spawner init, tick, pickup, and effect wiring"
git commit -m "feat: shield overlay draw and multi-shot firing mode"
git commit -m "feat: power-up HUD flash label"
git commit -m "chore: remove Phase 3 hardcoded canister placement"
git commit -m "chore: update CLAUDE.md with Phase 5 power-up patterns"
```

---

## Playtest Checklist

**Spawning**
- [ ] Level 1: zero power-ups spawn (empty weight table)
- [ ] Temporarily set level to 2 in config: fuel canisters and health
      pills appear, drift downward from top of camera view
- [ ] Sprites appear at random X positions within the visible window
- [ ] Drift speed varies between sprites — not all falling at same rate
- [ ] Sprite disappears silently when it reaches the floor terrain
- [ ] Sprite disappears when it scrolls off the left edge of the camera
- [ ] Spawn interval feels right — not too frequent, not too sparse

**Collection**
- [ ] Flying through a sprite collects it — sprite disappears immediately
- [ ] HUD flash shows power-up name for ~2 seconds then clears
- [ ] Pickup SFX plays on collection
- [ ] Collecting fuel canister adds fuel — gauge visibly increases
- [ ] Collecting health when at full HP does not overflow above MAX_HP

**Effects**
- [ ] Rapid fire: fire cooldown visibly faster while active, returns to
      normal on expiry
- [ ] Big gun: enemies take more damage per shot while active
- [ ] Multi-shot: three bullets fire in a spread — visible fan pattern
- [ ] Shield: shield sprite visible around ship; takes 3 hits before
      breaking; degrades through shield3 → shield2 → shield1 textures
- [ ] Shield: enemy hit absorbed (no HP loss) while shield is active
- [ ] All timed effects expire correctly — no permanent stat changes

**Integration**
- [ ] Pausing (P key) freezes power-up spawner and drifting sprites
- [ ] Game over clears all active power-up sprites from the world
- [ ] Power-ups do not interfere with terrain collision or docking

**Performance**
- [ ] No frame spikes when sprites are added or removed
- [ ] Stable 60fps with several active power-up sprites on screen

---

## User Actions Required (Summary)

1. **Read agf `PowerUpSprite`** before writing Part A2 — the registry
   pattern depends on how the existing class is structured. If it already
   supports type-name lookup, skip A2 entirely.
2. **Read agf effect base classes** before writing Part C — do not
   guess at method signatures; the contracts are defined in agf source.
3. **Verify weight table TOML parsing** — nested TOML tables
   (`[powerups.weights.level_1]`) may need special handling in
   `GameConfig.load()` depending on how other nested tables are parsed.
   Check existing patterns in `GameConfig` first.
4. **Tune spawn intervals** during playtest — the configured values are
   starting points; adjust until the frequency feels right for level 1
5. **Run on both Windows and Ubuntu** — confirm shield textures and
   sprite rotation render correctly on both platforms
6. **Report back to Claude.ai** before Phase 6:
   - Whether `PowerUpSprite` already had a type-name registry or needed one
   - Final tuned spawn intervals and weight table values
   - Any agf effect category contracts that differed from expectations
   - How `StatModifierEffect` communicates modified values — this affects
     how `_try_fire()` reads the rapid fire cooldown
