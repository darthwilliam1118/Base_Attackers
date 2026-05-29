# Feature Brief — Phase 6: Patrol Ships & Laser Turrets

**Game:** Base Attackers
**Phase:** 6 of 9
**Depends on:** Phase 5 complete — power-up spawner and effects working
**Output:** Patrol ships that spawn from off-screen and fly through the
level with varied behaviours, laser turrets that telegraph and fire an
instantaneous beam, dock-pressure hook wired to real patrol ship spawns,
ceiling-mounted enemy variants for all enemy types
**agf changes required:** None — all new logic is game-specific

---

## Goals

1. `PatrolShip` enemy — spawns off-screen right, selects a behaviour at
   spawn time (straight pass, intercept, kamikaze), flies through, exits
   or dies
2. Three patrol behaviours weighted by level difficulty
3. Wire `_on_dock_pressure_spawn()` — replace bullet wave with patrol
   ship spawn
4. `LaserTurret` enemy — composite like `GunTurret` (base + barrel),
   proximity trigger, telegraph beam, instantaneous damage line
5. Ceiling-mounted variants for `MissileSilo`, `GunTurret`, and
   `LaserTurret` — place some in Phase 6 test positions
6. Collision: patrol ships vs player bullets (destroyed), patrol ships
   vs player ship (ram damage)
7. Score values for new enemy types
8. Commit, run on both platforms, playtest

---

## Step 0 — Before Writing Any Code

Read in order:
1. `docs/architecture-overview.md`
2. `src/base_attackers/views/run_level.py` — full current state. Key
   sections to understand:
   - `__init__()` — all SpriteList declarations; new lists follow same
     pattern
   - `on_update()` — patrol ship update goes after `_check_docking()`
     and before `_update_missiles()`
   - `on_draw()` — patrol ships render between terrain and `_silo_list`
   - `_on_dock_pressure_spawn()` — replace bullet wave with patrol spawn
   - `_damage_player()` — patrol ship ram damage routes through this;
     shield absorption already handled there
   - `_on_enemy_destroyed()` and `_on_turret_destroyed()` — new destroy
     callbacks follow these exact patterns
3. `src/base_attackers/enemies/gun_turret.py` — `GunTurret` composite
   pattern; `LaserTurret` follows the same two-sprite approach
4. `src/base_attackers/enemies/missile_silo.py` — ceiling placement
   pattern already works; verify `_place_missile_silos()` handles
   ceiling surface correctly (it does — check line 609 in Phase 4 brief)
5. `src/base_attackers/game_config.toml` — `sprite_scale = 0.5`,
   `god_mode` flag, `[combat]` section for new config keys
6. `assets/images/PNG/Enemies/` — confirmed sprites available:
   - `enemyBlack1.png` through `enemyBlack5.png` — patrol ship variants
   - `enemyRed1.png` through `enemyRed5.png` — alternate patrol ships
   - `enemyBlue1.png` through `enemyBlue5.png` - alternate patrol ships
   - Pick one per behaviour tier; suggestion:
     - Straight pass: `enemyBlack2.png` (small, fast-looking)
     - Intercept: `enemyBlue3.png` (medium)
     - Kamikaze: `enemyRed1.png` (aggressive colour)
7. `assets/images/PNG/Parts/` — laser turret parts:
   - Base: `turretBase_big.png` (bigger than gun turret base)
   - Barrel: `gun09.png` (longer barrel than gun turret)
8. `agf/src/agf/sprites/explosion.py` — `ExplosionSprite` constructor
   signature (already used in `_on_enemy_destroyed`)

Do NOT rely on README files. Read actual source.

---

## Part A — Config Extensions

### A1. Add patrol ship and laser turret config to `game_config.toml`

```toml
[combat]
# ... existing keys unchanged ...

# Patrol ships
patrol_hp = 2
patrol_speed_min = 150.0        # px/s — straight pass
patrol_speed_max = 280.0        # px/s — kamikaze
patrol_intercept_lead = 0.6     # fraction of ship velocity added to aim
patrol_ram_damage = 1           # HP lost when patrol ship contacts player
patrol_spawn_margin = 60.0      # px off right edge of camera on spawn

# Laser turrets
laser_turret_hp = 4
laser_turret_fire_cooldown = 3.5
laser_telegraph_duration = 0.6  # seconds warning beam is visible
laser_beam_duration = 0.12      # seconds full beam is visible
laser_beam_damage = 1           # HP per beam hit
laser_beam_width = 3.0          # px line width for draw call
laser_beam_color = [255, 60, 60, 220]   # RGBA
laser_telegraph_color = [255, 180, 60, 120]   # RGBA dim orange
laser_proximity_trigger = 260.0  # px — turret activates when ship is within
```

### A2. Wire into `GameConfig`

Add new fields to `CombatSettings` dataclass and parse them in
`GameConfig.load()`. Follow the exact same pattern as existing
`CombatSettings` fields — no new dataclass needed.

---

## Part B — PatrolShip Enemy

Create `src/base_attackers/enemies/patrol_ship.py`.

### B1. Behaviour constants

```python
# Behaviour names — stored on each PatrolShip at spawn time.
BEHAVIOUR_STRAIGHT   = "straight"    # flies straight across at fixed Y
BEHAVIOUR_INTERCEPT  = "intercept"   # leads the player's current position
BEHAVIOUR_KAMIKAZE   = "kamikaze"    # dives directly at player, no exit
```

### B2. PatrolShip class

```python
"""PatrolShip — enemy that flies through the level from right to left.

Spawned off the right edge of the camera view; exits off the left edge
(straight/intercept) or is destroyed on player contact (kamikaze).
Behaviour is selected at spawn time and is immutable for the ship's
lifetime.

NOT terrain-mounted — no two-step Y positioning needed.  Spawns at a
world Y chosen by RunLevelView._spawn_patrol_ship().
"""
from __future__ import annotations

import math
import arcade
from agf.paths import resource_path
from src.base_attackers.game_config import CombatSettings

_SPRITE_MAP = {
    BEHAVIOUR_STRAIGHT:  "assets/images/PNG/Enemies/enemyBlack2.png",
    BEHAVIOUR_INTERCEPT: "assets/images/PNG/Enemies/enemyBlack3.png",
    BEHAVIOUR_KAMIKAZE:  "assets/images/PNG/Enemies/enemyRed1.png",
}

# Patrol ships face left — flip horizontally so nose points left.
_FACE_LEFT_ANGLE = 180.0


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
        self._vx: float = -speed   # starts moving left
        self._vy: float = 0.0
        self.angle = _FACE_LEFT_ANGLE

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int = 1) -> bool:
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def update_patrol(
        self, ship_x: float, ship_y: float, delta_time: float
    ) -> None:
        """Update velocity based on behaviour then apply movement."""
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

        self.center_x += self._vx * delta_time
        self.center_y += self._vy * delta_time
```

### B3. Cull conditions (in `RunLevelView._update_patrol_ships()`)

- Straight / intercept: cull when `center_x < cam_left - cull_margin`
- Kamikaze: only destroyed by player collision or player bullets — never
  exits off-screen (will eventually hit terrain and that's fine; just
  cull if it goes below `0` or above `world_height`)
- All: cull if `center_x > world_width + cull_margin` (somehow drifted
  right — edge case)

---

## Part C — Patrol Ship Spawning in RunLevelView

### C1. SpriteList declaration in `__init__()`

```python
self._patrol_list = arcade.SpriteList()   # PatrolShip sprites
self._patrols: list[PatrolShip] = []
```

### C2. Spawn helper

```python
def _spawn_patrol_ship(self, behaviour: str | None = None) -> None:
    """Spawn one patrol ship off the right edge of the camera view.

    Y position is randomised within the visible corridor at the spawn X,
    clamped above floor_y and below ceiling_y (or world_height).
    """
    import random
    assert self._terrain is not None and self._terrain_cfg is not None

    cfg = self._cfg.combat
    sw = self.window.width
    spawn_x = (
        self.window.world_camera.position.x
        + sw / 2.0
        + cfg.patrol_spawn_margin
    )

    # Pick behaviour — weighted by level.
    if behaviour is None:
        behaviour = self._pick_patrol_behaviour()

    # Y: random position in the open corridor at spawn_x.
    floor_y = self._terrain.floor_y_at(spawn_x)
    ceil_y  = self._terrain.ceiling_y_at(spawn_x)
    y_min   = floor_y + 30.0
    y_max   = ceil_y - 30.0 if ceil_y is not None else self._terrain_cfg.world_height - 30.0
    if y_min >= y_max:
        y_min = floor_y + 10.0
        y_max = y_min + 40.0
    spawn_y = random.uniform(y_min, y_max)

    # Speed varies by behaviour.
    if behaviour == BEHAVIOUR_KAMIKAZE:
        speed = random.uniform(
            cfg.patrol_speed_max * 0.8, cfg.patrol_speed_max
        )
    elif behaviour == BEHAVIOUR_INTERCEPT:
        speed = random.uniform(
            cfg.patrol_speed_min * 1.2, cfg.patrol_speed_max * 0.8
        )
    else:
        speed = random.uniform(cfg.patrol_speed_min, cfg.patrol_speed_max * 0.6)

    ship = PatrolShip(
        world_x=spawn_x,
        world_y=spawn_y,
        behaviour=behaviour,
        speed=speed,
        cfg=cfg,
        scale=self._cfg.sprite_scale,
    )
    self._patrol_list.append(ship)
    self._patrols.append(ship)

def _pick_patrol_behaviour(self) -> str:
    """Weight behaviours by level — higher levels get more kamikazes."""
    import random
    level = self._level_num
    weights = {
        BEHAVIOUR_STRAIGHT:  max(1, 5 - level),
        BEHAVIOUR_INTERCEPT: 3,
        BEHAVIOUR_KAMIKAZE:  min(5, level),
    }
    names   = list(weights.keys())
    wts     = list(weights.values())
    return random.choices(names, weights=wts, k=1)[0]
```

### C3. Update loop in `_update_patrol_ships()`

```python
def _update_patrol_ships(self, delta_time: float) -> None:
    assert self._terrain_cfg is not None
    cull  = self._cfg.combat.bullet_cull_margin
    cam_left = self.window.world_camera.position.x - self.window.width / 2.0
    world_w  = self._terrain_cfg.world_width
    world_h  = self._terrain_cfg.world_height

    for ship in list(self._patrols):
        if not ship.is_alive:
            continue
        ship.update_patrol(
            self._ship.center_x, self._ship.center_y, delta_time
        )
        # Cull off-screen.
        if ship.center_x < cam_left - cull:
            ship.remove_from_sprite_lists()
            self._patrols.remove(ship)
        elif ship.center_x > world_w + cull:
            ship.remove_from_sprite_lists()
            self._patrols.remove(ship)
        elif ship.center_y < -cull or ship.center_y > world_h + cull:
            ship.remove_from_sprite_lists()
            self._patrols.remove(ship)
```

### C4. Wire into `on_update()`

Add after `_check_docking()` and before `_update_missiles()`:

```python
self._update_patrol_ships(delta_time)
```

### C5. Wire into `on_draw()`

Add after `_tower_list.draw()` and before `_silo_list.draw()`:

```python
self._patrol_list.draw()
```

### C6. Replace `_on_dock_pressure_spawn()`

Replace the current bullet-wave implementation entirely:

```python
def _on_dock_pressure_spawn(self) -> None:
    """Spawn a patrol ship from the right when player lingers at a tower."""
    self._spawn_patrol_ship(behaviour=BEHAVIOUR_INTERCEPT)
    log.info("dock pressure: spawned intercept patrol ship")
```

---

## Part D — LaserTurret Enemy

Create `src/base_attackers/enemies/laser_turret.py`.

### D1. LaserTurret class

`LaserTurret` is a composite enemy like `GunTurret` — NOT itself an
`arcade.Sprite`. It owns a `base` sprite and a `barrel` sprite, plus
manages its own telegraph/fire state machine.

```python
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

_BASE_SPRITE   = "assets/images/PNG/Parts/turretBase_big.png"
_BARREL_SPRITE = "assets/images/PNG/Parts/gun09.png"
_SPRITE_NATURAL_BEARING_DEG = 90.0   # gun09.png points up at angle=0

_STATE_IDLE      = "idle"
_STATE_TELEGRAPH = "telegraph"
_STATE_FIRING    = "firing"
_STATE_COOLDOWN  = "cooldown"


class LaserTurret:
    def __init__(
        self,
        world_x: float,
        surface: str,
        cfg: CombatSettings,
        scale: float,
    ) -> None:
        self.surface = surface
        self.cfg = cfg
        self.hp: int = cfg.laser_turret_hp
        self._state: str = _STATE_IDLE
        self._state_timer: float = 0.0
        self._aim_angle: float = 90.0 if surface == "floor" else 270.0
        self._fire_cooldown: float = 0.0
        self._damage_dealt: bool = False   # reset each FIRING entry

        self.base   = arcade.Sprite(resource_path(_BASE_SPRITE),   scale=scale)
        self.barrel = arcade.Sprite(resource_path(_BARREL_SPRITE), scale=scale)
        self.base.center_x   = world_x
        self.barrel.center_x = world_x
        self.base.center_y   = 0.0
        self.barrel.center_y = 0.0
        self._barrel_offset_y: float = 0.0

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def is_telegraphing(self) -> bool:
        return self._state == _STATE_TELEGRAPH

    @property
    def is_firing(self) -> bool:
        return self._state == _STATE_FIRING

    def take_damage(self, amount: int = 1) -> bool:
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def position_on_terrain(self, surface_y: float) -> None:
        """Same pattern as GunTurret — call after construction."""
        half_base   = self.base.height   / 2.0
        half_barrel = self.barrel.height / 2.0
        if self.surface == "floor":
            self.base.center_y   = surface_y + half_base
            self.base.angle      = 180.0
            self._barrel_offset_y = half_base + half_barrel + 2.0
        else:
            self.base.center_y   = surface_y - half_base
            self.base.angle      = 0.0
            self._barrel_offset_y = -(half_base + half_barrel + 2.0)
        self.barrel.center_y = self.base.center_y + self._barrel_offset_y

    def beam_end(self, beam_length: float = 800.0) -> tuple[float, float]:
        """World-space endpoint of the beam from barrel tip."""
        rad = math.radians(self._aim_angle)
        tip_x = self.barrel.center_x
        tip_y = self.barrel.center_y
        return tip_x + math.cos(rad) * beam_length, tip_y + math.sin(rad) * beam_length

    def update(
        self, ship_x: float, ship_y: float, delta_time: float
    ) -> str:
        """Tick state machine. Returns current state name so RunLevelView
        knows when to draw beams and apply damage.
        """
        if not self.is_alive:
            return _STATE_IDLE

        # Rotate barrel toward player (always, even while telegraphing).
        dx = ship_x - self.barrel.center_x
        dy = ship_y - self.barrel.center_y
        target = math.degrees(math.atan2(dy, dx))
        diff    = (target - self._aim_angle + 180.0) % 360.0 - 180.0
        rot_speed = self.cfg.turret_rotation_speed * 0.5   # slower than gun turret
        max_rot = rot_speed * delta_time
        self._aim_angle += math.copysign(min(abs(diff), max_rot), diff)
        self._aim_angle %= 360.0
        self.barrel.angle = _SPRITE_NATURAL_BEARING_DEG - self._aim_angle
        self.barrel.center_x = self.base.center_x
        self.barrel.center_y = self.base.center_y + self._barrel_offset_y

        # State transitions.
        if self._state == _STATE_IDLE:
            if self._fire_cooldown > 0.0:
                self._fire_cooldown -= delta_time
            else:
                dist = math.hypot(dx, dy)
                if dist <= self.cfg.laser_proximity_trigger:
                    self._state       = _STATE_TELEGRAPH
                    self._state_timer = self.cfg.laser_telegraph_duration
                    self._damage_dealt = False

        elif self._state == _STATE_TELEGRAPH:
            self._state_timer -= delta_time
            if self._state_timer <= 0.0:
                self._state       = _STATE_FIRING
                self._state_timer = self.cfg.laser_beam_duration

        elif self._state == _STATE_FIRING:
            self._state_timer -= delta_time
            if self._state_timer <= 0.0:
                self._state       = _STATE_COOLDOWN
                self._fire_cooldown = self.cfg.laser_turret_fire_cooldown

        elif self._state == _STATE_COOLDOWN:
            # Cooldown handled by _fire_cooldown in IDLE state; transition.
            self._state = _STATE_IDLE

        return self._state
```

### D2. LaserTurret placement in `RunLevelView`

```python
_PHASE6_LASER_POSITIONS: list[tuple[float, str]] = [
    (1000.0, "floor"),
    (3000.0, "floor"),
    (5000.0, "floor"),
]
```

```python
def _place_laser_turrets(self) -> None:
    assert self._terrain is not None
    self._laser_base_list   = arcade.SpriteList()
    self._laser_barrel_list = arcade.SpriteList()
    self._laser_turrets: list[LaserTurret] = []

    for x, surface in _PHASE6_LASER_POSITIONS:
        surface_y = (
            self._terrain.floor_y_at(x)
            if surface == "floor"
            else self._terrain.ceiling_y_at(x)
        )
        if surface_y is None:
            continue
        lt = LaserTurret(
            world_x=x,
            surface=surface,
            cfg=self._cfg.combat,
            scale=self._cfg.sprite_scale,
        )
        lt.position_on_terrain(surface_y)
        self._laser_base_list.append(lt.base)
        self._laser_barrel_list.append(lt.barrel)
        self._laser_turrets.append(lt)
```

Call `_place_laser_turrets()` from `on_show_view()` after
`_place_gun_turrets()`.

Also add to `__init__()`:
```python
self._laser_base_list   = arcade.SpriteList()
self._laser_barrel_list = arcade.SpriteList()
self._laser_turrets: list[LaserTurret] = []
```

### D3. Laser update and damage in `_update_laser_turrets()`

```python
def _update_laser_turrets(self, delta_time: float) -> None:
    for lt in self._laser_turrets:
        if not lt.is_alive:
            continue
        state = lt.update(
            self._ship.center_x, self._ship.center_y, delta_time
        )
        # Apply damage on the first frame of FIRING state.
        if state == "firing" and not lt._damage_dealt:
            lt._damage_dealt = True
            # Line-segment vs ship: check if ship center is within
            # laser_beam_width / 2 px of the beam line.
            if self._ship_in_laser_beam(lt):
                self._damage_player(self._cfg.combat.laser_beam_damage)
```

```python
def _ship_in_laser_beam(self, lt: LaserTurret) -> bool:
    """True if the ship center is within beam_width/2 of the laser line."""
    import math
    x0, y0 = lt.barrel.center_x, lt.barrel.center_y
    x1, y1 = lt.beam_end()
    px, py = self._ship.center_x, self._ship.center_y
    # Perpendicular distance from point to line segment.
    dx, dy = x1 - x0, y1 - y0
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return False
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length_sq))
    closest_x = x0 + t * dx
    closest_y = y0 + t * dy
    dist = math.hypot(px - closest_x, py - closest_y)
    half_w = (self._cfg.combat.laser_beam_width / 2.0) + self._ship.width / 4.0
    return dist <= half_w
```

Wire into `on_update()` after `_update_turrets()`:
```python
self._update_laser_turrets(delta_time)
```

### D4. Laser beam drawing in `on_draw()`

Beams are immediate-mode lines drawn in world-camera space — NOT sprites,
NOT ShapeElementList. They are ephemeral (< 0.7s total) so no SpriteList
churn occurs. Add after `_laser_barrel_list.draw()`:

```python
self._draw_laser_beams()
```

```python
def _draw_laser_beams(self) -> None:
    cfg = self._cfg.combat
    for lt in self._laser_turrets:
        if not lt.is_alive:
            continue
        if lt.is_telegraphing:
            color = tuple(cfg.laser_telegraph_color)
            width = max(1, int(cfg.laser_beam_width * 0.5))
        elif lt.is_firing:
            color = tuple(cfg.laser_beam_color)
            width = int(cfg.laser_beam_width)
        else:
            continue
        end_x, end_y = lt.beam_end()
        arcade.draw_line(
            lt.barrel.center_x, lt.barrel.center_y,
            end_x, end_y,
            color, width,
        )
```

---

## Part E — Collision Updates

### E1. Player bullets vs patrol ships

Add to `_check_player_bullet_hits()` after turret base check:

```python
# vs patrol ships
for bullet in list(self._bullet_list):
    if not bullet.sprite_lists:
        continue
    hits = arcade.check_for_collision_with_list(bullet, self._patrol_list)
    if hits:
        bullet.remove_from_sprite_lists()
        patrol = hits[0]
        assert isinstance(patrol, PatrolShip)
        if patrol.take_damage(self._cfg.combat.player_bullet_damage):
            self._on_patrol_destroyed(patrol)

# vs laser turret bases
for bullet in list(self._bullet_list):
    if not bullet.sprite_lists:
        continue
    hits = arcade.check_for_collision_with_list(bullet, self._laser_base_list)
    if hits:
        bullet.remove_from_sprite_lists()
        base_sprite = hits[0]
        lt = next((t for t in self._laser_turrets if t.base is base_sprite), None)
        if lt is not None and lt.take_damage(self._cfg.combat.player_bullet_damage):
            self._on_laser_turret_destroyed(lt)
```

### E2. Patrol ships vs player (ram damage)

Add to `_check_enemy_hits()`:

```python
# Patrol ship ram
patrol_hits = arcade.check_for_collision_with_list(
    self._ship, self._patrol_list
)
for patrol in patrol_hits:
    assert isinstance(patrol, PatrolShip)
    patrol.remove_from_sprite_lists()
    if patrol in self._patrols:
        self._patrols.remove(patrol)
    self._damage_player(self._cfg.combat.patrol_ram_damage)
    if self._death_timer > 0.0:
        return
```

### E3. Destroy callbacks

```python
def _on_patrol_destroyed(self, patrol: PatrolShip) -> None:
    from agf.sprites.explosion import ExplosionSprite
    self._explosion_list.append(ExplosionSprite(
        x=patrol.center_x, y=patrol.center_y,
        scale=max(1.0, self._cfg.sprite_scale * 2.0),
    ))
    patrol.remove_from_sprite_lists()
    if patrol in self._patrols:
        self._patrols.remove(patrol)
    self._score += 200
    self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)

def _on_laser_turret_destroyed(self, lt: LaserTurret) -> None:
    from agf.sprites.explosion import ExplosionSprite
    self._explosion_list.append(ExplosionSprite(
        x=lt.base.center_x, y=lt.base.center_y,
        scale=max(1.0, self._cfg.sprite_scale * 2.0),
    ))
    lt.base.remove_from_sprite_lists()
    lt.barrel.remove_from_sprite_lists()
    self._score += 250
    self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)
```

---

## Part F — Ceiling Variants for Existing Enemies

### F1. Add ceiling positions to Phase 4 hardcoded lists

Update `_PHASE4_SILO_POSITIONS` and `_PHASE4_TURRET_POSITIONS` to include
some ceiling-mounted variants. This requires `ceiling_present = true` in
`[level_1]` config, OR use a separate level config for testing.

**Easiest approach for Phase 6:** add a `[level_2]` section to
`game_config.toml` with `ceiling_present = true` and slightly harder
terrain params, then set `starting_level = 2` temporarily for testing
ceiling enemies. Revert to `starting_level = 1` after testing.

```toml
[level_2]
world_width = 6400
world_height = 720
terrain_amplitude = 110.0
terrain_frequency = 0.009
terrain_half_width = 240.0
ceiling_present = true
terrain_renderer = "polygon"
terrain_seed = 0
```

Add ceiling positions to the hardcoded lists:
```python
_PHASE4_SILO_POSITIONS: list[tuple[float, str]] = [
    (1200.0, "floor"),
    (2800.0, "floor"),
    (4000.0, "floor"),
    (2000.0, "ceiling"),   # Phase 6 addition
    (4800.0, "ceiling"),   # Phase 6 addition
]
```

Existing placement code already handles ceiling correctly — no changes
needed to `_place_missile_silos()` or `_place_gun_turrets()`.

---

## Part G — on_draw() Full Updated Order

```python
def on_draw(self) -> None:
    self.clear()
    self.window.use_world_camera()
    if self._powerup_spawner is not None:
        self._powerup_spawner.sprite_list.draw()   # behind terrain
    if self._terrain is not None:
        self._terrain.draw()
    self._tower_list.draw()
    self._patrol_list.draw()                       # Phase 6 addition
    self._silo_list.draw()
    self._turret_base_list.draw()
    self._turret_barrel_list.draw()
    self._laser_base_list.draw()                   # Phase 6 addition
    self._laser_barrel_list.draw()                 # Phase 6 addition
    self._draw_laser_beams()                       # Phase 6 addition
    self._missile_list.draw()
    self._enemy_bullet_list.draw()
    self._bullet_list.draw()
    self._ship_list.draw()
    self._scratch_list.draw()
    if self._shield_sprite_ref is not None:
        self._shield_sprite_ref.center_x = self._ship.center_x
        self._shield_sprite_ref.center_y = self._ship.center_y
    self._overlay_list.draw()
    self._explosion_list.draw()

    self.window.use_gui_camera()
    self._draw_hud()
    if self._paused:
        self._pause_overlay_list.draw()
        if self._paused_text is not None:
            self._paused_text.draw()
```

---

## Part H — CLAUDE.md Updates

After implementing, add to `CLAUDE.md`:

- `PatrolShip` is a single `arcade.Sprite` (not composite); lives in
  `_patrol_list` and `_patrols`. Culled when off left/right/top/bottom
  world edges.
- `LaserTurret` is composite like `GunTurret` — two SpriteLists
  (`_laser_base_list`, `_laser_barrel_list`). `position_on_terrain()`
  must be called after construction.
- Laser beam is drawn with `arcade.draw_line()` in world-camera space —
  NOT a sprite, NOT ShapeElementList. Acceptable because beam is < 0.7s
  total duration; no per-frame allocation.
- `_damage_dealt` flag on `LaserTurret` prevents multiple damage
  applications during the FIRING state window. Reset on each
  TELEGRAPH→FIRING transition.
- `_on_dock_pressure_spawn()` now spawns an intercept patrol ship
  (not a bullet wave). Phase 9 may tune behaviour weighting.
- Ceiling enemies require `ceiling_present = true` in level config —
  placement code skips `ceiling_y_at()` returns of `None` silently.
- Score values: silo=100, turret=150, patrol=200, laser turret=250.

---

## Commit Sequence

```bash
git commit -m "feat: PatrolShip enemy with straight/intercept/kamikaze behaviours"
git commit -m "feat: RunLevelView patrol ship spawning, update, cull, collision"
git commit -m "feat: dock pressure hook replaced with patrol ship spawn"
git commit -m "feat: LaserTurret composite enemy with telegraph/fire state machine"
git commit -m "feat: laser turret placement, update, beam draw, damage"
git commit -m "feat: ceiling-mounted enemy positions and level_2 config"
git commit -m "feat: player bullet vs patrol and laser turret collision"
git commit -m "chore: update CLAUDE.md with Phase 6 enemy patterns"
```

---

## Playtest Checklist

**Patrol ships**
- [ ] Patrol ships spawn from right edge of camera view
- [ ] Straight behaviour: flies left at constant Y, exits off left edge
- [ ] Intercept behaviour: steers toward player position, exits left
- [ ] Kamikaze behaviour: always dives toward player, does not exit
- [ ] Player bullet destroys patrol ship — explosion, score +200
- [ ] Patrol ship contacting player deals `patrol_ram_damage` HP
- [ ] Shield absorbs patrol ship ram (routes through `_damage_player`)
- [ ] Docking at tower spawns an intercept patrol after pressure interval

**Laser turrets**
- [ ] Three laser turrets visible on terrain at correct positions
- [ ] Approaching within `laser_proximity_trigger` px triggers telegraph
- [ ] Telegraph: dim orange beam visible for `laser_telegraph_duration` s
- [ ] After telegraph: bright red beam flashes for `laser_beam_duration` s
- [ ] Being in the beam path on firing frame applies damage
- [ ] Beam can be dodged by moving during telegraph phase
- [ ] Player bullet hitting base damages turret — four hits destroy it
- [ ] Destroyed laser turret removes both sprites, plays explosion

**Ceiling enemies (level 2 config)**
- [ ] Switch to `starting_level = 2` in config
- [ ] Ceiling silos visible hanging from ceiling — missile fires downward
- [ ] Ceiling gun turrets visible — barrel aims downward at player
- [ ] Ceiling laser turrets fire downward beam

**Combined**
- [ ] Stable 60fps with all new enemies active simultaneously
- [ ] No visual glitches when patrol ships overlap terrain or other enemies

---

## User Actions Required (Summary)

1. **Select patrol ship sprites** — brief suggests `enemyBlack2.png`,
   `enemyBlack3.png`, `enemyRed1.png`. Look at the available Enemies
   sprites and pick whichever looks best for each behaviour. Update
   `_SPRITE_MAP` in `patrol_ship.py`.
2. **Verify laser beam colors** — `laser_beam_color` and
   `laser_telegraph_color` are RGBA arrays in TOML. Confirm TOML parser
   handles list values in `CombatSettings` — may need to parse as list
   and convert to tuple. If TOML list parsing is awkward, hardcode colors
   as constants in `laser_turret.py` instead.
3. **Tune patrol ship feel** during playtest:
   - `patrol_speed_min` / `patrol_speed_max` — are speeds challenging?
   - `patrol_intercept_lead` — does intercept feel fair or cheap?
   - `patrol_spawn_margin` — do ships spawn far enough off-screen?
4. **Tune laser telegraph timing** — `laser_telegraph_duration` should
   feel like a fair warning; `laser_beam_duration` should feel brief
   and punishing.
5. **Run on both Windows and Ubuntu** — confirm laser beam draw calls
   render correctly on both (immediate-mode draw calls are the most
   likely cross-platform difference in this phase).
6. **Report back to Claude.ai** before Phase 7:
   - Final tuned combat config values
   - Which patrol behaviours feel fun vs frustrating
   - Whether ceiling enemies feel right or need positional adjustment
   - Laser beam damage feel — too forgiving or too punishing?
