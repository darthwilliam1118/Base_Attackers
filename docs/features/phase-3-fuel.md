# Feature Brief — Phase 3: Fuel System & Fuel Towers

**Game:** Base Attackers
**Phase:** 3 of 9
**Depends on:** Phase 2 complete — ship flying, camera tracking, terrain
collision working
**Output:** Depleting fuel gauge, fuel-empty death spiral, fuel towers
that the player can land on to refuel, enemy spawn pressure while docked,
full HP/damage visual system with scratch overlays
**agf changes required:** None — fuel is entirely game-specific

---

## Goals

1. Activate and wire the fuel system — gauge depletes over time, HUD
   shows a real bar not a placeholder
2. Implement fuel-empty state — weapons off, control off, gravity takes
   over, terrain contact = instant death
3. Implement `FuelTower` — a ground or ceiling fixture the ship can dock
   on from above (or below for ceiling-mounted), with snap hysteresis,
   fuel transfer rate, and tower depletion
4. Implement enemy spawn pressure while docked (simple version — increased
   spawn rate placeholder; actual enemies arrive Phase 4, but the spawner
   hook must exist)
5. Implement HP damage visual system — scratch overlays on ship at 2/3
   and 1/3 HP, ship destroyed at 0 HP with explosion
6. Wire fuel canister power-up (world-space collectible, instant partial
   refuel on contact)
7. Commit, run on both platforms, playtest

---

## Step 0 — Before Writing Any Code

Read in order:
1. `docs/architecture-overview.md`
2. `src/base_attackers/ships/player_ship.py` — current HP and state
3. `src/base_attackers/views/run_level.py` — full current state; understand
   `_update_ship()`, `_on_terrain_collision()`, `_update_camera()`,
   and how the ship SpriteList is managed
4. `src/base_attackers/game_config.toml` — `[ship]` section has `gravity`,
   `hp`, `hit_radius`; `[level_1]` has terrain params
5. `agf/src/agf/sprites/` — check what `ExplosionSprite` expects so the
   ship destruction sequence uses it correctly
6. `assets/images/PNG/Parts/` — sprite filenames confirmed:
   - `fuel-tower.png` — custom fuel tower sprite (128×64 px, tall and
     narrow so it protrudes clearly above the terrain surface)
   - `scratch1.png`, `scratch2.png`, `scratch3.png` — ship damage overlays
7. `assets/images/PNG/Power-ups/bolt_gold.png` — fuel canister sprite

Do NOT rely on README files. Read actual source.

---

## Part A — Config Extensions

### A1. Add fuel config to `game_config.toml` `[ship]` section

```toml
[ship]
accel = 400.0
friction = 0.25
max_speed_x = 350.0
max_speed_y = 300.0
hp = 3
hit_radius = 16.0
gravity = 0
fuel_capacity = 100.0
fuel_drain_rate = 4.0        # units per second during normal flight
fuel_gravity = 150.0         # px/s² downward when fuel empty
fuel_canister_restore = 25.0 # fuel units restored by one canister pickup
```

### A2. Add fuel tower config to `game_config.toml`

```toml
[fuel_tower]
transfer_rate = 20.0         # fuel units per second transferred to ship
snap_distance = 40.0         # px — ship snaps to dock when within this range
tower_capacity = 60.0        # max fuel a single tower holds
spawn_pressure_interval = 3.0 # seconds between pressure spawns while docked
                               # (no-op until Phase 4 enemies exist)
```

### A3. Wire new fields into `GameConfig`

Add `fuel_capacity`, `fuel_drain_rate`, `fuel_gravity`, `fuel_canister_restore`
to the ship config dataclass. Add a `FuelTowerConfig` dataclass for the
`[fuel_tower]` section. Both loaded in `GameConfig.load()`.

---

## Part B — PlayerShip Extensions

### B1. Add fuel state to `PlayerShip`

```python
class PlayerShip(arcade.Sprite, MomentumShipMixin):

    def __init__(self, momentum_config: MomentumConfig, ship_cfg: ShipConfig) -> None:
        ...
        # Fuel state
        self.fuel: float = ship_cfg.fuel_capacity
        self.fuel_capacity: float = ship_cfg.fuel_capacity
        self.fuel_drain_rate: float = ship_cfg.fuel_drain_rate
        self.fuel_gravity: float = ship_cfg.fuel_gravity

        # Dock state
        self.is_docked: bool = False
        self.dock_tower: FuelTower | None = None   # TYPE_CHECKING guard

        # Damage overlays — loaded lazily, set after construction
        self._scratch_textures: list[arcade.Texture] = []
        self._scratch_sprite: arcade.Sprite | None = None

    @property
    def fuel_empty(self) -> bool:
        return self.fuel <= 0.0

    @property
    def control_enabled(self) -> bool:
        """Input and weapons disabled when fuel is empty or docked."""
        return not self.fuel_empty

    def drain_fuel(self, delta_time: float) -> None:
        """Deplete fuel during normal flight. No-op when docked."""
        if not self.is_docked:
            self.fuel = max(0.0, self.fuel - self.fuel_drain_rate * delta_time)

    def add_fuel(self, amount: float) -> None:
        self.fuel = min(self.fuel_capacity, self.fuel + amount)
```

### B2. Scratch overlay system

The scratch sprites are screen-space overlays drawn on top of the ship
in world-camera space, centred on the ship each frame.

```python
def load_scratch_textures(self) -> None:
    """Call once after construction, before first draw."""
    from agf.paths import resource_path
    base = "assets/images/PNG/Parts/"
    self._scratch_textures = [
        arcade.load_texture(resource_path(base + "scratch1.png")),
        arcade.load_texture(resource_path(base + "scratch2.png")),
        arcade.load_texture(resource_path(base + "scratch3.png")),
    ]
    self._scratch_sprite = arcade.Sprite(scale=self.scale)

def update_scratch_overlay(self) -> None:
    """Select scratch texture based on HP fraction. Call each frame."""
    if self._scratch_sprite is None or not self._scratch_textures:
        return
    hp_frac = self.hp / self.MAX_HP
    if hp_frac > 0.66:
        self._scratch_sprite.visible = False
    elif hp_frac > 0.33:
        self._scratch_sprite.texture = self._scratch_textures[0]  # scratch1
        self._scratch_sprite.visible = True
    else:
        self._scratch_sprite.texture = self._scratch_textures[2]  # scratch3
        self._scratch_sprite.visible = True
    # Keep centred on ship
    if self._scratch_sprite.visible:
        self._scratch_sprite.center_x = self.center_x
        self._scratch_sprite.center_y = self.center_y

def draw_scratch(self) -> None:
    """Draw scratch overlay. Call after ship SpriteList.draw()."""
    if self._scratch_sprite and self._scratch_sprite.visible:
        self._scratch_sprite.draw()
```

### B3. Gravity when fuel empty

`apply_momentum()` in `MomentumShipMixin` is unchanged — gravity is
applied by `RunLevelView._update_ship()` on top of the momentum delta,
only when `ship.fuel_empty` is True. See Part D.

---

## Part C — FuelTower

Create `src/base_attackers/terrain_features/fuel_tower.py`.

```
src/base_attackers/terrain_features/
    __init__.py
    fuel_tower.py
```

### C1. FuelTower class

```python
"""FuelTower — a refuelling station mounted on floor or ceiling terrain.

The ship docks by approaching from the correct side (above for floor
towers, below for ceiling towers). When within snap_distance, RunLevelView
snaps the ship onto the dock point and sets ship.is_docked = True.
Fuel transfers at transfer_rate until the tower is empty or the ship
undocks.
"""
from __future__ import annotations

from dataclasses import dataclass
import arcade
from agf.paths import resource_path


@dataclass
class FuelTowerConfig:
    transfer_rate: float
    snap_distance: float
    tower_capacity: float
    spawn_pressure_interval: float


class FuelTower(arcade.Sprite):
    """Stationary fuel tower placed on terrain surface.

    `surface` is "floor" (tower sits on floor, ship docks from above)
    or "ceiling" (tower hangs from ceiling, ship docks from below).
    `dock_y` is the world Y where the ship's center snaps to when docked.
    """

    SPRITE_PATH = "assets/images/PNG/Parts/fuel-tower.png"
    # Asset is 128×64 px — tall and narrow, designed to protrude above terrain.
    # Do NOT use sprite_scale from game config for this sprite — towers have
    # their own scale so they read clearly against the landscape. Default 1.0
    # gives a 128px tall tower at full resolution; adjust via config if needed.

    def __init__(
        self,
        world_x: float,
        world_y: float,
        surface: str,          # "floor" or "ceiling"
        cfg: FuelTowerConfig,
        scale: float = 1.0,   # towers use their own scale, not sprite_scale
    ) -> None:
        super().__init__(resource_path(self.SPRITE_PATH), scale=scale)
        # At scale=1.0, tower is 128px tall × 64px wide in world space.
        # center_y is set by the caller after construction using tower.height,
        # so the base sits flush with the terrain surface and the tower
        # protrudes upward into the corridor. See placement note in C2.
        self.center_x = world_x
        self.center_y = world_y
        self.surface = surface
        self.cfg = cfg
        self.fuel_remaining: float = cfg.tower_capacity
        self._pressure_timer: float = 0.0

        # Dock point: ship centre snaps here when docked.
        half_h = self.height / 2.0
        if surface == "floor":
            self.dock_y = world_y + half_h + 8.0   # just above tower top
        else:
            self.dock_y = world_y - half_h - 8.0   # just below tower bottom

    @property
    def has_fuel(self) -> bool:
        return self.fuel_remaining > 0.0

    @property
    def is_depleted(self) -> bool:
        return self.fuel_remaining <= 0.0

    def update_transfer(self, ship, delta_time: float) -> float:
        """Transfer fuel to ship. Returns amount actually transferred."""
        if self.fuel_remaining <= 0.0:
            return 0.0
        amount = min(
            self.cfg.transfer_rate * delta_time,
            self.fuel_remaining,
            ship.fuel_capacity - ship.fuel,
        )
        self.fuel_remaining -= amount
        ship.add_fuel(amount)
        return amount

    def update_pressure(self, delta_time: float) -> bool:
        """Tick pressure timer. Returns True when a spawn event should fire."""
        self._pressure_timer += delta_time
        if self._pressure_timer >= self.cfg.spawn_pressure_interval:
            self._pressure_timer = 0.0
            return True
        return False

    def snap_distance_to(self, ship_x: float, ship_y: float) -> float:
        """Horizontal + vertical distance from ship to this tower's dock point."""
        import math
        return math.hypot(ship_x - self.center_x, ship_y - self.dock_y)
```

### C2. FuelTower placement

Tower placement is handled by `RunLevelView` at level start. For Phase 3,
place towers at hardcoded world X positions so they are predictable for
playtesting. Phase 7 (level structure) will move placement into level
config.

Place **3 towers** for level 1 testing:
```python
_PHASE3_TOWER_POSITIONS = [800.0, 2400.0, 4400.0]  # world X positions
```

**Positioning rules for `fuel-tower.png` (128×64 px at scale 1.0):**

The tower must sit with its base flush on the terrain floor surface and
protrude upward into the flying corridor. Since `arcade.Sprite` centers
the texture on `center_y`, the base of the tower is at
`center_y - height/2`. To place the base at `floor_y`:

```python
center_y = floor_y + tower.height / 2.0
```

The dock point (where the ship's center snaps to) should be just above
the tower top with a small clearance gap:

```python
dock_y = center_y + tower.height / 2.0 + 12.0
```

The 12px clearance ensures the ship sprite sits visually above the tower
rather than overlapping it. Adjust if it looks wrong during playtest.

**Do not pass `sprite_scale` from GameConfig to `FuelTower`.** Towers
use `scale=1.0` by default so the 128px asset fills meaningful vertical
space in the 720px world. If the tower looks too large or too small
after playtesting, add a dedicated `tower_scale` key to `[fuel_tower]`
config and adjust there — do not tie it to the enemy/ship scale.

```python
def _place_fuel_towers(self) -> None:
    self._tower_list = arcade.SpriteList()
    self._towers: list[FuelTower] = []
    for x in _PHASE3_TOWER_POSITIONS:
        # Construct at origin first so .height is available
        tower = FuelTower(
            world_x=x,
            world_y=0.0,          # placeholder — corrected below
            surface="floor",
            cfg=self._cfg.fuel_tower,
            scale=1.0,
        )
        floor_y = self._terrain.floor_y_at(x)
        tower.center_y = floor_y + tower.height / 2.0
        tower.dock_y   = tower.center_y + tower.height / 2.0 + 12.0
        self._tower_list.append(tower)
        self._towers.append(tower)
```

---

## Part D — RunLevelView Extensions

### D1. Fuel drain in `on_update()`

Add to the update loop after `_update_ship()`:

```python
# Drain fuel during normal flight
if not self._ship.is_docked:
    self._ship.drain_fuel(delta_time)

# Check fuel-empty state
if self._ship.fuel_empty and not self._ship.is_docked:
    self._apply_fuel_gravity(delta_time)
```

### D2. Fuel gravity

```python
def _apply_fuel_gravity(self, delta_time: float) -> None:
    """When fuel is empty: disable control, apply gravity downward."""
    # velocity_y decreases (downward) each frame
    self._ship.velocity_y -= self._cfg.ship.fuel_gravity * delta_time
    # velocity_x decays via friction only — ship drifts forward
    decay = self._cfg.ship.friction ** delta_time
    self._ship.velocity_x *= decay

    new_x = self._ship.center_x + self._ship.velocity_x * delta_time
    new_y = self._ship.center_y + self._ship.velocity_y * delta_time

    # Terrain contact while fuel-empty = instant death regardless of HP
    if self._terrain.point_in_terrain(new_x, new_y):
        self._on_terrain_collision()
        return

    self._ship.center_x = new_x
    self._ship.center_y = new_y
```

Note: `_update_ship()` must check `ship.control_enabled` before reading
input. When `control_enabled` is False, skip input entirely and return
`(0.0, 0.0)` — `_apply_fuel_gravity()` handles movement instead.

### D3. Docking logic

Add `_check_docking()` called each frame from `on_update()`:

```python
def _check_docking(self) -> None:
    """Snap ship to nearest tower if within snap distance and approaching."""
    if self._ship.is_docked:
        self._handle_docked()
        return
    if self._ship.fuel_empty:
        return  # cannot dock during death spiral

    for tower in self._towers:
        if tower.is_depleted:
            continue
        dist = tower.snap_distance_to(self._ship.center_x, self._ship.center_y)
        if dist <= self._cfg.fuel_tower.snap_distance:
            self._dock_to(tower)
            return

def _dock_to(self, tower: FuelTower) -> None:
    self._ship.is_docked = True
    self._ship.dock_tower = tower
    # Snap ship position to dock point
    self._ship.center_x = tower.center_x
    self._ship.center_y = tower.dock_y
    # Kill velocity on dock
    self._ship.velocity_x = 0.0
    self._ship.velocity_y = 0.0

def _handle_docked(self) -> None:
    """Called each frame while ship is docked."""
    tower = self._ship.dock_tower
    if tower is None:
        self._ship.is_docked = False
        return

    # Transfer fuel
    tower.update_transfer(self._ship, self._last_delta)

    # Undock conditions: SPACE pressed, tower depleted, or ship destroyed
    if self._undock_requested or tower.is_depleted or not self._ship.is_alive:
        self._ship.is_docked = False
        self._ship.dock_tower = None
        self._undock_requested = False
        return

    # Spawn pressure tick — no-op until Phase 4 enemies exist
    if tower.update_pressure(self._last_delta):
        self._on_dock_pressure_spawn()

def _on_dock_pressure_spawn(self) -> None:
    """Called on each pressure tick while ship is docked. Phase 4 wires in
    actual enemy spawning. Phase 3: log only."""
    pass  # TODO Phase 4: trigger enemy spawn
```

Store `delta_time` as `self._last_delta` at the top of `on_update()` so
`_handle_docked()` can access it without threading it through every call.

### D4. Undock input

In `on_key_press()`:
```python
if key == arcade.key.SPACE:
    if self._ship.is_docked:
        self._undock_requested = True
```

SPACE undocks the ship. This key will also be the fire key in Phase 4 —
the distinction is handled by `self._ship.is_docked`. If docked, SPACE
undocks; if not docked, SPACE fires (Phase 4).

### D5. Fuel canister collectible

Fuel canisters are `arcade.Sprite` objects placed in world space.
Phase 3 places them at hardcoded positions (same approach as towers —
Phase 7 moves to level config):

```python
_PHASE3_CANISTER_POSITIONS = [1600.0, 3200.0, 5000.0]  # world X

def _place_fuel_canisters(self) -> None:
    self._canister_list = arcade.SpriteList()
    for x in _PHASE3_CANISTER_POSITIONS:
        floor_y = self._terrain.floor_y_at(x)
        canister = arcade.Sprite(
            resource_path("assets/images/PNG/Power-ups/bolt_gold.png"),
            scale=self._cfg.game.sprite_scale,
        )
        canister.center_x = x
        canister.center_y = floor_y + 80.0  # float above floor
        self._canister_list.append(canister)
```

Collision check in `on_update()` using `arcade.check_for_collision_with_list()`:

```python
def _check_canister_pickup(self) -> None:
    hit = arcade.check_for_collision_with_list(self._ship, self._canister_list)
    for canister in hit:
        self._ship.add_fuel(self._cfg.ship.fuel_canister_restore)
        canister.remove_from_sprite_lists()
```

### D6. Update `_update_ship()` to respect `control_enabled`

```python
def _update_ship(self, delta_time: float) -> None:
    if not self._ship.control_enabled or self._ship.is_docked:
        return  # gravity or docked — movement handled elsewhere

    # ... existing input + momentum code unchanged ...
```

### D7. Ship destruction sequence

When `ship.hp <= 0` (from damage — terrain collision is already instant
death in Phase 2), trigger a brief explosion before transitioning:

```python
def _destroy_ship(self) -> None:
    """Play explosion at ship position then transition to GAME_OVER."""
    from agf.sprites.explosion import ExplosionSprite
    explosion = ExplosionSprite(
        center_x=self._ship.center_x,
        center_y=self._ship.center_y,
    )
    self._explosion_list.append(explosion)
    self._ship.visible = False
    self._ship.is_docked = False
    # Schedule transition after explosion duration (max 2s per CLAUDE.md)
    self._death_timer = 1.5

def on_update(self, delta_time: float) -> None:
    # At top of update loop:
    if self._death_timer > 0.0:
        self._death_timer -= delta_time
        self._explosion_list.update(delta_time)
        if self._death_timer <= 0.0:
            from src.base_attackers.state import GameState
            self._manager.transition(GameState.GAME_OVER)
        return   # skip all other updates during death sequence
    ...
```

---

## Part E — HUD Extensions

Replace the Phase 2 placeholder HUD with real gauges.

### E1. Fuel gauge bar

Draw as a filled rectangle in GUI camera space. Two rectangles — background
(dark) and foreground (coloured, width proportional to fuel fraction):

```python
def _draw_fuel_gauge(self) -> None:
    BAR_X, BAR_Y = 20.0, 40.0    # screen space bottom-left of bar
    BAR_W, BAR_H = 200.0, 16.0
    fuel_frac = self._ship.fuel / self._ship.fuel_capacity
    # Background
    arcade.draw_lrbt_rectangle_filled(
        BAR_X, BAR_X + BAR_W, BAR_Y, BAR_Y + BAR_H,
        (60, 60, 60, 200)
    )
    # Foreground — colour shifts red when low
    color = (255, 80, 80) if fuel_frac < 0.25 else (80, 200, 255)
    arcade.draw_lrbt_rectangle_filled(
        BAR_X, BAR_X + BAR_W * fuel_frac, BAR_Y, BAR_Y + BAR_H,
        color
    )
```

Call `_draw_fuel_gauge()` inside `on_draw()` after `use_gui_camera()`.
Also update `_hud_fuel_label` text:
```python
self._hud_fuel_label.text = f"FUEL  {self._ship.fuel:.0f}"
```

### E2. HP bar

Similar pattern alongside the fuel bar:

```python
def _draw_hp_bar(self) -> None:
    BAR_X, BAR_Y = 20.0, 64.0
    BAR_W, BAR_H = 120.0, 16.0
    hp_frac = self._ship.hp / self._ship.MAX_HP
    arcade.draw_lrbt_rectangle_filled(
        BAR_X, BAR_X + BAR_W, BAR_Y, BAR_Y + BAR_H,
        (60, 60, 60, 200)
    )
    arcade.draw_lrbt_rectangle_filled(
        BAR_X, BAR_X + BAR_W * hp_frac, BAR_Y, BAR_Y + BAR_H,
        (80, 220, 80)
    )
```

### E3. Tower fuel indicator

When ship is docked, draw the tower's remaining fuel as a small bar
above the fuel gauge:

```python
if self._ship.is_docked and self._ship.dock_tower:
    tower = self._ship.dock_tower
    t_frac = tower.fuel_remaining / tower.cfg.tower_capacity
    # Draw small orange bar labelled "TOWER"
```

### E4. Docked indicator

When ship is docked, draw a blinking "DOCKED" text in the HUD.
Use a timer to toggle visibility every 0.4 seconds:

```python
self._dock_blink_timer += delta_time
if self._dock_blink_timer >= 0.4:
    self._dock_blink_timer = 0.0
    self._dock_blink_visible = not self._dock_blink_visible
self._hud_docked.visible = self._ship.is_docked and self._dock_blink_visible
```

---

## Part F — on_draw() Full Structure

```python
def on_draw(self) -> None:
    self.clear()

    self.window.use_world_camera()
    self._terrain.draw()
    self._tower_list.draw()
    self._canister_list.draw()
    self._ship_list.draw()          # ship sprite
    self._ship.draw_scratch()       # scratch overlay, centred on ship
    self._explosion_list.draw()

    self.window.use_gui_camera()
    self._draw_fuel_gauge()
    self._draw_hp_bar()
    self._hud_fps.draw()
    self._hud_world_x.draw()
    self._hud_hp.draw()
    self._hud_fuel_label.draw()
    self._hud_docked.draw()
    if self._ship.is_docked and self._ship.dock_tower:
        self._draw_tower_gauge()
```

---

## Part G — CLAUDE.md Updates

After implementing, add to `CLAUDE.md`:

- `FuelTower` lives in `src/base_attackers/terrain_features/fuel_tower.py`
- `fuel-tower.png` is 128×64 px — do NOT scale with `sprite_scale`; towers
  use `scale=1.0` so they protrude visibly above terrain. Add a dedicated
  `tower_scale` to `[fuel_tower]` config if size needs adjusting.
- Tower `center_y` is set after construction: `floor_y + tower.height / 2`.
  Dock point is `center_y + tower.height / 2 + 12`. This puts the ship
  clearly above the tower top when docked.
- Docking: ship snaps when within `snap_distance` of `tower.dock_y`;
  SPACE undocks (same key will fire in Phase 4 — check `is_docked` first)
- `ship.control_enabled` is the gate for input and weapons — check this
  before processing any player action
- `_death_timer` pattern: set to > 0 at ship death, skip all updates,
  tick down, transition when reaches 0. Max 1.5s.
- Fuel gauge and HP bar are drawn with `arcade.draw_lrbt_rectangle_filled()`
  in GUI camera space — not sprites, not ShapeElementList
- `_on_dock_pressure_spawn()` is a Phase 4 hook — leave it as `pass`,
  do not remove it
- Tower positions are hardcoded in Phase 3 — Phase 7 moves to level config
- Canister positions are hardcoded in Phase 3 — Phase 5 replaces with
  world-space power-up spawner

---

## Commit Sequence

```bash
git commit -m "feat: add fuel config fields to GameConfig and game_config.toml"
git commit -m "feat: PlayerShip fuel state, drain, add_fuel, scratch overlays"
git commit -m "feat: FuelTower with snap docking and fuel transfer"
git commit -m "feat: RunLevelView fuel drain, gravity, docking logic"
git commit -m "feat: fuel canister collectibles placed in world space"
git commit -m "feat: HUD fuel gauge, HP bar, docked indicator"
git commit -m "feat: ship destruction sequence with explosion and death timer"
git commit -m "chore: update CLAUDE.md with Phase 3 patterns"
```

All commits via terminal — not VS Code UI.

---

## Playtest Checklist

**Fuel system**
- [ ] Fuel gauge visible in HUD and depletes smoothly during flight
- [ ] Gauge colour shifts to red below 25% fuel
- [ ] Fuel reaching zero disables ship input immediately
- [ ] Ship coasts forward then begins falling when fuel hits zero
- [ ] Gravity accumulates — fall accelerates over time, not instant drop
- [ ] Terrain contact during fuel-empty = instant death + explosion
- [ ] Death timer plays explosion for ~1.5s before GAME_OVER transition

**Docking**
- [ ] All three towers visible on terrain at correct floor positions
- [ ] Approaching a tower from above — ship snaps cleanly onto dock point
- [ ] "DOCKED" indicator blinks in HUD while docked
- [ ] Tower fuel gauge appears in HUD while docked
- [ ] Fuel transfers from tower to ship — both gauges update in real time
- [ ] Tower reaching zero fuel stops transfer — ship can undock freely
- [ ] SPACE undocks ship — ship does not fire while docked (Phase 4 check)
- [ ] Ship is vulnerable while docked — taking damage (manually test via
      god_mode = false and future enemy hits) reduces HP
- [ ] Pressure spawn hook fires (check console log) every
      `spawn_pressure_interval` seconds while docked

**Canisters**
- [ ] Three canisters visible floating above floor at correct positions
- [ ] Flying through canister adds `fuel_canister_restore` fuel instantly
- [ ] Canister disappears on pickup
- [ ] Picking up canister when fuel is full does not overflow past capacity

**HP and damage**
- [ ] At 2/3 HP: scratch1 overlay visible on ship
- [ ] At 1/3 HP: scratch3 overlay visible on ship
- [ ] Scratch overlay tracks ship position correctly when moving
- [ ] Ship at 0 HP: explosion plays, ship disappears, GAME_OVER after timer

**HUD**
- [ ] Fuel gauge and HP bar render in screen space — do not scroll with camera
- [ ] All text uses KenVector Future2 Thin — verify on Ubuntu particularly

**Feel — tune config until satisfying**
- [ ] `fuel_drain_rate` — does fuel pressure feel real without being
      punishing on level 1?
- [ ] `fuel_gravity` — does the death spiral feel dramatic but fair?
      (Too fast = unfair; too slow = not scary)
- [ ] `transfer_rate` — does docking feel rewarding? Should take 3-5
      seconds to fill from near-empty to full on a fresh tower.
- [ ] `snap_distance` — does the snap feel helpful or too grabby?

---

## User Actions Required (Summary)

1. **Check `turretBase_big.png`** looks reasonable as a fuel tower at
   `sprite_scale = 0.5` — if it looks wrong, source a better placeholder
   and update `FuelTower.SPRITE_PATH`
2. **Tune fuel config values** during playtest — note final values for
   Phase 4 brief
3. **Run on both Windows and Ubuntu** — confirm scratch overlays and
   gauge bars render correctly on both
4. **Report back to Claude.ai** before Phase 4:
   - Final fuel config values that feel right
   - Whether ceiling-mounted towers are needed for level variety or
     floor-only is sufficient for now
   - Any docking feel issues (snap too aggressive, dock point wrong height)
   - Confirm `_on_dock_pressure_spawn()` logs firing correctly so Phase 4
     can wire real enemies into it
