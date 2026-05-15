# Feature Brief — Phase 2: Ship in the World

**Game:** Base Attackers
**Phase:** 2 of 9
**Depends on:** Phase 1 complete, both terrain renderers working
**Output:** Player ship flying through terrain with momentum physics,
deadzone camera tracking, terrain collision, and a minimal HUD stub.
The game launches directly into a playable level view (not the terrain
testbed). Terrain renderer is selected per-level via config.
**agf changes required:** Yes — `MomentumShipMixin` added to agf first

---

## Goals

1. Add `MomentumShipMixin` to agf — generalised momentum/friction physics
2. Implement `PlayerShip` using the mixin
3. Implement `RunLevelView` — the main gameplay view replacing `TerrainTestView`
   as the launch target
4. Wire deadzone camera tracking with monotonic X clamp
5. Terrain collision — ship vs floor and ceiling, death on contact
6. Minimal HUD stub — fuel gauge placeholder, HP bar placeholder, FPS,
   world X position (enough to verify GUI camera is working correctly)
7. Level config drives terrain renderer choice (tile vs polygon per level)
8. Commit, run on Windows and Ubuntu, playtest

---

## Step 0 — Before Writing Any Code

Read in order:
1. `docs/architecture-overview.md`
2. `src/base_attackers/terrain/terrain_base.py` — know `TerrainBase`,
   `CorridorSlice`, `TerrainConfig`, `generate_corridor_profile()`
3. `src/base_attackers/terrain/tile_terrain.py` — constructor signature,
   especially the `screen_width` parameter
4. `src/base_attackers/terrain/polygon_terrain.py` — same
5. `src/base_attackers/views/terrain_test.py` — how `world_camera.position`
   is set and how `use_world_camera()` / `use_gui_camera()` are called;
   Phase 2 must follow the same pattern exactly
6. `src/base_attackers/game.py` — font name is `"KenVector Future2 Thin"`,
   not `"KenVector Future Thin"`. Use `GAME_FONT` constant or import from
   `agf.ui.text_utils` (which game.py rebinds at startup)
7. `src/base_attackers/game_config.toml` — `[ship]` section already has
   accel, friction, max_speed_x, max_speed_y. `[level_1]` has terrain params.
8. `agf/src/agf/window.py` — `ScrollingGameWindow` interface

Do NOT rely on README files. Read actual source.

---

## Part A — agf Changes (agf VS Code window first)

### A1. Add `MomentumShipMixin` to `agf/src/agf/ships/momentum.py`

Create the file. This mixin is intentionally generic — no Base Attackers
specific logic, no fuel, no weapons. Just physics.

```python
"""MomentumShipMixin — reusable momentum/friction ship physics.

Mix into any sprite subclass that needs inertia-based movement.
The mixin owns velocity only; position is managed by the host class
(typically arcade.Sprite via self.center_x / self.center_y).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MomentumConfig:
    accel: float        # px/s² applied per unit of input (-1.0 to 1.0)
    friction: float     # velocity multiplier per second (0.0-1.0; 0.85 = decay)
    max_speed_x: float  # px/s horizontal clamp
    max_speed_y: float  # px/s vertical clamp


class MomentumShipMixin:
    """
    Mixin providing velocity_x / velocity_y with acceleration and friction.

    Host class must call apply_momentum(delta_time) each frame after
    setting input_x and input_y (-1.0, 0.0, or 1.0).

    The mixin does NOT update center_x / center_y — the host class does
    that after calling apply_momentum(), so it can apply its own clamping
    (world bounds, camera left edge, etc.) before committing the position.
    """

    def __init__(self, momentum_config: MomentumConfig) -> None:
        self._mcfg = momentum_config
        self.velocity_x: float = 0.0
        self.velocity_y: float = 0.0
        self.input_x: float = 0.0   # set by host before apply_momentum()
        self.input_y: float = 0.0

    def apply_momentum(self, delta_time: float) -> tuple[float, float]:
        """Update velocity from input and friction.

        Returns (delta_x, delta_y) — the position delta to apply this frame.
        The caller applies it to center_x / center_y after clamping.
        """
        cfg = self._mcfg
        self.velocity_x += self.input_x * cfg.accel * delta_time
        self.velocity_y += self.input_y * cfg.accel * delta_time

        # Friction: exponential decay independent of frame rate.
        decay = cfg.friction ** delta_time
        self.velocity_x *= decay
        self.velocity_y *= decay

        # Speed clamp.
        self.velocity_x = max(-cfg.max_speed_x, min(cfg.max_speed_x, self.velocity_x))
        self.velocity_y = max(-cfg.max_speed_y, min(cfg.max_speed_y, self.velocity_y))

        return self.velocity_x * delta_time, self.velocity_y * delta_time
```

### A2. Export from agf

Add to `agf/src/agf/__init__.py`:
```python
from agf.ships.momentum import MomentumShipMixin, MomentumConfig
```

Create `agf/src/agf/ships/__init__.py` (empty) if the `ships/` package
does not yet exist.

### A3. Commit agf

```bash
cd path/to/arcade-game-framework
git add -A
git commit -m "feat: add MomentumShipMixin and MomentumConfig to agf.ships"
git push
```

Do NOT tag agf yet — that happens at Phase 9.

### A4. Update Base Attackers agf pin

In `Base_Attackers/pyproject.toml`, update the agf git SHA to the new
commit. Then:
```bash
pip install -e ".[dev]"   # pulls updated agf
```

---

## Part B — GameConfig extension

### B1. Add ship config fields to `GameConfig`

The `[ship]` TOML section already exists. Wire it into the `GameConfig`
dataclass if not already done. The ship needs:

```python
# inside GameConfig or a nested ShipConfig dataclass
ship_accel: float        # from [ship] accel
ship_friction: float     # from [ship] friction
ship_max_speed_x: float  # from [ship] max_speed_x
ship_max_speed_y: float  # from [ship] max_speed_y
ship_hp: int             # add to game_config.toml [ship] — default 3
ship_hit_radius: float   # add to game_config.toml [ship] — default 16.0
```

### B2. Add renderer choice to level config

Add `terrain_renderer` to `[level_1]` in `game_config.toml`:
```toml
[level_1]
world_width = 6400
world_height = 720
terrain_amplitude = 80.0
terrain_frequency = 0.008
terrain_half_width = 280.0
ceiling_present = false
terrain_renderer = "tile"   # "tile" or "polygon"
terrain_seed = 0            # 0 = random each run
```

Wire this into `GameConfig` so `RunLevelView` can read it. This is how
keeping both renderers is managed — different levels can use different
looks purely via config.

### B3. Add to `game_config.toml` `[ship]` section

```toml
[ship]
accel = 400.0
friction = 0.85
max_speed_x = 350.0
max_speed_y = 300.0
ship_hp = 3
hit_radius = 16.0
```

---

## Part C — Player Ship

### C1. Create `src/base_attackers/ships/player_ship.py`

```python
"""PlayerShip — the player-controlled ship sprite.

Inherits arcade.Sprite for rendering and MomentumShipMixin for physics.
Does NOT handle terrain collision — RunLevelView does that after
applying the position delta, so it can compare against terrain before
committing.
"""
from __future__ import annotations

import arcade
from agf.ships.momentum import MomentumConfig, MomentumShipMixin
from agf.paths import resource_path


class PlayerShip(arcade.Sprite, MomentumShipMixin):
    MAX_HP: int = 3   # overridden by config at construction

    def __init__(self, momentum_config: MomentumConfig, max_hp: int = 3) -> None:
        arcade.Sprite.__init__(
            self,
            resource_path("assets/images/ships/player_ship.png"),
        )
        MomentumShipMixin.__init__(self, momentum_config)
        self.MAX_HP = max_hp
        self.hp: int = max_hp

    def update_ship(self, delta_time: float) -> tuple[float, float]:
        """Compute this frame's position delta without applying it.

        RunLevelView applies the delta after clamping against world bounds
        and terrain collision.
        """
        return self.apply_momentum(delta_time)

    def take_damage(self, amount: int = 1) -> bool:
        """Apply damage. Returns True if ship is destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    @property
    def is_alive(self) -> bool:
        return self.hp > 0
```

### C2. Create `src/base_attackers/ships/__init__.py`

```python
from src.base_attackers.ships.player_ship import PlayerShip
```

---

## Part D — RunLevelView

Create `src/base_attackers/views/run_level.py`. This replaces
`TerrainTestView` as the active gameplay view. `TerrainTestView` is
kept intact — it remains accessible via the state machine for future
use or debugging.

### D1. Terrain factory helper (inside `run_level.py`)

```python
def _build_terrain(cfg: GameConfig, level_cfg: LevelConfig) -> TerrainBase:
    """Instantiate the correct renderer for this level from config."""
    from src.base_attackers.terrain import (
        TileTerrainRenderer, PolygonTerrainRenderer,
        generate_corridor_profile, TerrainConfig,
    )
    seed = level_cfg.terrain_seed if level_cfg.terrain_seed != 0 else None
    terrain_cfg = TerrainConfig(
        world_width=level_cfg.world_width,
        world_height=level_cfg.world_height,
        chunk_width=cfg.terrain.chunk_width,
        cull_buffer_chunks=cfg.terrain.cull_buffer_chunks,
        amplitude=level_cfg.terrain_amplitude,
        frequency=level_cfg.terrain_frequency,
        half_width=level_cfg.terrain_half_width,
        ceiling_present=level_cfg.ceiling_present,
    )
    profile = generate_corridor_profile(terrain_cfg, seed=seed)
    screen_w = cfg.window.width
    if level_cfg.terrain_renderer == "polygon":
        return PolygonTerrainRenderer(profile, terrain_cfg, screen_w)
    return TileTerrainRenderer(profile, terrain_cfg, screen_w)
```

### D2. Camera deadzone constants

```python
# Ship must stay within this fraction of screen width from left/right
# before the camera moves.
_DEADZONE_LEFT   = 0.25   # camera moves if ship < 25% from left edge
_DEADZONE_RIGHT  = 0.65   # camera moves if ship > 65% from left edge
_DEADZONE_TOP    = 0.80   # camera moves if ship > 80% from bottom edge
_DEADZONE_BOTTOM = 0.20   # camera moves if ship < 20% from bottom edge
```

### D3. Camera update logic

The camera X is **monotonically increasing** — it never decreases.
Implement as a method `_update_camera(self)` called each frame:

```python
def _update_camera(self) -> None:
    sw = self.window.width
    sh = self.window.height

    # Current camera anchors (top-left of visible window in world space)
    cam_left = self.window.world_camera.position.x - sw / 2.0
    cam_bottom = self.window.world_camera.position.y - sh / 2.0

    ship_x = self._ship.center_x
    ship_y = self._ship.center_y

    # Horizontal deadzone — push camera right only, never left.
    left_bound  = cam_left + sw * _DEADZONE_LEFT
    right_bound = cam_left + sw * _DEADZONE_RIGHT
    if ship_x < left_bound:
        cam_left = ship_x - sw * _DEADZONE_LEFT
    elif ship_x > right_bound:
        cam_left = ship_x - sw * _DEADZONE_RIGHT
    # Monotonic clamp — camera X never decreases.
    cam_left = max(cam_left, self._min_camera_left)
    self._min_camera_left = cam_left

    # Vertical deadzone — free to scroll up and down within world bounds.
    bottom_bound = cam_bottom + sh * _DEADZONE_BOTTOM
    top_bound    = cam_bottom + sh * _DEADZONE_TOP
    if ship_y < bottom_bound:
        cam_bottom = ship_y - sh * _DEADZONE_BOTTOM
    elif ship_y > top_bound:
        cam_bottom = ship_y - sh * _DEADZONE_TOP
    # Clamp camera to world height.
    world_h = self._terrain_cfg.world_height
    cam_bottom = max(0.0, min(cam_bottom, world_h - sh))

    # Apply to world camera (position is centre of viewport).
    self.window.world_camera.position = Vec2(
        cam_left + sw / 2.0,
        cam_bottom + sh / 2.0,
    )
```

### D4. Ship position update with collision

Called each frame from `on_update()`:

```python
def _update_ship(self, delta_time: float) -> None:
    # Read input.
    self._ship.input_x = 0.0
    self._ship.input_y = 0.0
    if self._held_keys & {arcade.key.RIGHT, arcade.key.D}:
        self._ship.input_x = 1.0
    if self._held_keys & {arcade.key.LEFT, arcade.key.A}:
        self._ship.input_x = -1.0
    if self._held_keys & {arcade.key.UP, arcade.key.W}:
        self._ship.input_y = 1.0
    if self._held_keys & {arcade.key.DOWN, arcade.key.S}:
        self._ship.input_y = -1.0

    dx, dy = self._ship.update_ship(delta_time)

    new_x = self._ship.center_x + dx
    new_y = self._ship.center_y + dy

    # Clamp: ship cannot move left of camera's left edge.
    cam_left = self.window.world_camera.position.x - self.window.width / 2.0
    new_x = max(new_x, cam_left + self.window.width * _DEADZONE_LEFT)

    # Clamp: ship cannot leave world bounds.
    new_x = max(0.0, min(new_x, self._terrain_cfg.world_width))
    new_y = max(0.0, min(new_y, self._terrain_cfg.world_height))

    # Terrain collision.
    if self._terrain.point_in_terrain(new_x, new_y):
        self._on_terrain_collision()
        return

    self._ship.center_x = new_x
    self._ship.center_y = new_y
```

### D5. Terrain collision handler

```python
def _on_terrain_collision(self) -> None:
    """Ship hit terrain — instant death regardless of HP."""
    self._ship.hp = 0
    # Phase 2: just log and transition to game over.
    # Phase 3 will add explosion animation and delay.
    from src.base_attackers.state import GameState
    self._manager.transition(GameState.GAME_OVER)
```

### D6. on_draw() structure

Follow the exact pattern from `terrain_test.py`:

```python
def on_draw(self) -> None:
    self.clear()
    self.window.use_world_camera()
    self._terrain.draw()
    self._ship_list.draw()          # SpriteList containing just the ship
    self.window.use_gui_camera()
    # HUD stub — all arcade.Text objects, never arcade.draw_text()
    self._hud_fps.draw()
    self._hud_world_x.draw()
    self._hud_hp.draw()
    self._hud_fuel_label.draw()     # "FUEL: ---" placeholder
```

### D7. Ship spawn position

Spawn the ship at the level entry — left side of the world, vertically
centred in the corridor opening:

```python
def _spawn_ship(self) -> None:
    # Entry zone: first chunk. Corridor is always wide here (smoothstep ramp).
    entry_floor = self._terrain.floor_y_at(64.0)
    entry_ceil  = self._terrain.ceiling_y_at(64.0)
    if entry_ceil is not None:
        spawn_y = (entry_floor + entry_ceil) / 2.0
    else:
        spawn_y = entry_floor + 200.0   # open sky — spawn above floor
    self._ship.center_x = 160.0
    self._ship.center_y = spawn_y
    self._min_camera_left = 0.0
```

---

## Part E — HUD Stub

The HUD is intentionally minimal in Phase 2. All elements use
`arcade.Text` (never `arcade.draw_text()`). Font is `FONT_THIN`
imported from `agf.ui.text_utils` (game.py rebinds it at startup to
`"KenVector Future2 Thin"` — importing `FONT_THIN` picks up the
rebound value automatically provided `game.py._load_fonts()` runs
before any Text objects are created, which it does).

Position all HUD elements in **screen space** (GUI camera coordinates
0,0 = bottom-left of window):

```python
def _build_hud(self) -> None:
    sh = self.window.height
    sw = self.window.width
    common = dict(font_name=FONT_THIN, font_size=14, color=arcade.color.WHITE)
    self._hud_fps      = arcade.Text("FPS: --",    12, sh - 20, **common)
    self._hud_world_x  = arcade.Text("X: 0",       12, sh - 40, **common)
    self._hud_hp       = arcade.Text("HP: ---",     12, sh - 60, **common)
    self._hud_fuel_label = arcade.Text("FUEL: ---", 12, sh - 80, **common)
```

Update each frame in `_refresh_hud()`:
```python
def _refresh_hud(self) -> None:
    self._hud_fps.text     = f"FPS: {arcade.get_fps():.0f}"
    self._hud_world_x.text = f"X: {self._ship.center_x:.0f}"
    self._hud_hp.text      = f"HP: {self._ship.hp} / {self._ship.MAX_HP}"
    self._hud_fuel_label.text = "FUEL: ---"   # wired in Phase 3
```

---

## Part F — State Machine Wiring

### F1. Update `GameState` enum in `state.py`

Ensure `RUN_LEVEL` state exists and transitions to `RunLevelView`.
`TERRAIN_TEST` state should also exist so the testbed remains
accessible (useful for debugging terrain during later phases).

```python
class GameState(Enum):
    SPLASH        = auto()
    MAIN          = auto()
    RUN_LEVEL     = auto()
    TERRAIN_TEST  = auto()   # keep — testbed remains useful
    GAME_OVER     = auto()
    HIGH_SCORES   = auto()
    SCORE_ENTRY   = auto()
    LEVEL_COMPLETE = auto()
```

### F2. Change launch target in `game.py`

Change the initial transition from `GameState.SPLASH` to `GameState.RUN_LEVEL`
for Phase 2 development. This is a temporary dev shortcut — revert to
`SPLASH` when the full menu flow is wired in Phase 7.

```python
# In GameWindow.__init__() — Phase 2 dev shortcut
self._manager.transition(GameState.RUN_LEVEL)
```

Add a comment: `# TODO Phase 7: revert to GameState.SPLASH`

---

## Part G — CLAUDE.md Updates

After implementing, add to `CLAUDE.md`:

- `MomentumShipMixin` import path and how to use `apply_momentum()`
- The camera deadzone constants and why X is monotonically clamped
- The `_min_camera_left` pattern
- `terrain_renderer` config key in `[level_N]` sections controls which
  renderer is used — "tile" or "polygon"
- `terrain_seed = 0` means random; non-zero means reproducible
- `PlayerShip.update_ship()` returns delta, not applied — `RunLevelView`
  applies after clamping
- Terrain collision is instant death — no HP reduction, direct to GAME_OVER

---

## Commit Sequence

```bash
# agf repo
git commit -m "feat: add MomentumShipMixin and MomentumConfig to agf.ships"

# Base Attackers
git commit -m "chore: update agf pin to include MomentumShipMixin"
git commit -m "feat: GameConfig terrain_renderer and terrain_seed per level"
git commit -m "feat: PlayerShip with momentum physics"
git commit -m "feat: RunLevelView with camera deadzone and terrain collision"
git commit -m "feat: HUD stub in GUI camera space"
git commit -m "chore: wire RUN_LEVEL state, dev shortcut launch target"
git commit -m "chore: update CLAUDE.md with Phase 2 patterns"
```

All commits via terminal — not VS Code UI.

---

## Playtest Checklist

**Functionality**
- [ ] Game launches directly into `RunLevelView` (dev shortcut active)
- [ ] Ship spawns in the corridor entry zone, visually centred
- [ ] WASD and arrow keys move the ship with visible momentum and friction
- [ ] Releasing keys causes ship to coast and slow — not instant stop
- [ ] Camera tracks ship within deadzone — only moves when ship pushes edge
- [ ] Camera never scrolls left — moving ship left within deadzone, camera
      stays put
- [ ] Ship cannot move left of camera's left deadzone boundary
- [ ] Ship touching floor → immediate transition to GAME_OVER
- [ ] Ship touching ceiling (preset 3-5 terrain) → GAME_OVER
- [ ] HUD shows correct FPS, world X updates as ship moves, HP shows 3/3
- [ ] FUEL shows "---" placeholder

**Visual**
- [ ] `terrain_renderer = "tile"` in level_1 config → chunky tile terrain
- [ ] Change to `"polygon"` → smooth polygon terrain, no restart needed
      (change config, relaunch)
- [ ] HUD renders in screen space — does not move when camera scrolls
- [ ] No terrain rendering gaps or seams

**Physics feel — tune config values until these feel right**
- [ ] Ship has noticeable weight — not instant response to input
- [ ] Friction brings ship to rest within ~0.5 seconds of releasing input
- [ ] Max speed feels fast enough to be fun but controllable in tight terrain
- [ ] Vertical and horizontal feel balanced

**Cross-platform**
- [ ] Runs on Windows without errors
- [ ] Runs on Ubuntu without errors — particularly confirm font renders
      correctly (KenVector Future2 Thin, no bold)

**Config tuning decisions to make during playtest**
- [ ] Adjust `accel`, `friction`, `max_speed_x`, `max_speed_y` in
      `game_config.toml` until physics feel right — note final values
- [ ] Adjust `_DEADZONE_LEFT` / `_DEADZONE_RIGHT` if camera feel is off
- [ ] Report any terrain difficulty preset that produces unfair instant
      deaths on spawn

---

## User Actions Required (Summary)

These cannot be done by Claude Code:

1. **Confirm player ship sprite** is at `assets/images/ships/player_ship.png`
   and faces right — this was a Phase 1 action item
2. **Physics tuning** — play with `accel`, `friction`, `max_speed_x/y`
   in `game_config.toml` until the ship feel is right; note final values
3. **Run on both platforms** and confirm no font or rendering errors
4. **Report back to Claude.ai** before Phase 3:
   - Final physics config values
   - Any terrain collision edge cases observed
   - Whether vertical camera scrolling felt right or needs adjustment
