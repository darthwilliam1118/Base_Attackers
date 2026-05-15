# Base Attackers — Architecture Overview

**Version:** 0.1 (Phase 1 baseline)
**Date:** May 2026
**Refs:** agf v0.2.0, Arcade 3.3.3, Python 3.14

This document is the authoritative reference for Claude Code sessions
working on Base Attackers. Read this before reading any feature brief.
Update this document whenever a significant architectural decision is
made during implementation.

---

## Project Identity

- **Game:** Base Attackers — side-scrolling space shooter inspired by
  Scramble (1981)
- **Repos:**
  - `github.com/darthwilliam1118/Base_Attackers`
  - `github.com/darthwilliam1118/arcade-game-framework` (agf) — shared
    infrastructure, currently v0.2.0, will evolve to v0.3.0
  - `github.com/darthwilliam1118/Space_Attackers` — sibling game, pinned
    to agf v0.2.0, must not be broken by agf changes
- **Language:** Python 3.14
- **Framework:** Arcade 3.3.3
- **Window:** 1280×720 (16:9)
- **Platform:** Windows primary, Ubuntu 24.04 secondary
- **Tools:** VS Code + Claude Code extension, PyInstaller, GitHub Actions

---

## Repository Layout

```
base_attackers/
├── src/
│   └── base_attackers/
│       ├── __init__.py
│       ├── main.py              — entry point, window init
│       ├── state.py             — GameStateManager subclass
│       ├── config.py            — GameConfig dataclass + TOML loading
│       ├── game_config.toml     — runtime config values
│       ├── ships/
│       │   └── player_ship.py
│       ├── terrain/
│       │   ├── terrain_base.py
│       │   ├── tile_terrain.py
│       │   └── polygon_terrain.py
│       ├── enemies/
│       ├── powerups/
│       ├── bosses/
│       └── views/
│           ├── run_level.py
│           └── terrain_test.py  — Phase 1 testbed view
├── assets/
│   ├── images/
│   ├── sounds/
│   └── music/
├── docs/
│   └── features/               — one markdown brief per phase
├── tests/
├── pyproject.toml
├── CLAUDE.md                   — persistent context for Claude Code
└── .github/
    └── workflows/
        └── ci.yml
```

---

## World Coordinate System

This is the most important concept to understand before touching any
rendering or physics code.

**World space** is the full extent of a level. All game objects
(terrain, enemies, power-ups, the player ship) live in world
coordinates. The world origin (0, 0) is the bottom-left corner of the
level.

| Parameter | Value | Notes |
|-----------|-------|-------|
| World width | 6400 px | 5 × window width |
| World height (min) | 720 px | Level 1 — one screen tall |
| World height (max) | 2160 px | Later levels — three screens tall |
| Window width | 1280 px | Fixed |
| Window height | 720 px | Fixed |

World height per level is defined in the level config TOML. The terrain
generator uses the full world height. Early levels have world height ==
window height so vertical scrolling is invisible.

**Screen space** is always 0,0 to 1280,720. The HUD lives exclusively
in screen space and must never be drawn in world coordinates.

---

## Dual-Camera System (agf addition)

Base Attackers requires two cameras, a pattern not present in Space
Attackers. This will be added to `agf` as an additive-only change that
does not affect `GameWindowBase` or any Space Attackers class.

### World Camera (`self.world_camera`)
- Type: `arcade.Camera2D`
- Tracks the player ship within a deadzone rectangle
- World X position is **monotonically increasing** — the camera never
  scrolls left. Enforced as:
  ```python
  new_x = max(self.world_camera.position.x, target_x)
  ```
- World Y scrolls freely within level bounds when world height > 720

### GUI Camera (`self.gui_camera`)
- Type: `arcade.Camera2D`
- Always anchored to screen origin (0, 0) — never moves
- Used exclusively for HUD rendering

### Usage pattern in `on_draw()`
```python
def on_draw(self):
    self.clear()
    self.world_camera.use()
    # draw terrain, sprites, enemies, player
    self.gui_camera.use()
    # draw HUD, fuel gauge, HP bar, score
```

### agf implementation note
Add a `ScrollingGameWindow` subclass of `GameWindowBase` in
`agf/window.py` that initialises both cameras and exposes
`use_world_camera()` / `use_gui_camera()` convenience methods.
`GameWindowBase` itself is unchanged. Base Attackers window inherits
from `ScrollingGameWindow`. Space Attackers is unaffected.

Import using the submodule pattern (consistent with the rest of agf,
e.g. `from agf.paths import resource_path`):

```python
from agf.window import ScrollingGameWindow
```

`agf/__init__.py` does not re-export classes at the top level.

---

## Terrain System

### Core concept
Terrain is generated once at level start for the entire world width.
It is **not** generated on the fly during scrolling. This allows
deliberate pacing — boss zone, fuel tower placement, and difficulty
ramps can be planned across the full level length.

The terrain describes a **corridor** — a floor surface and an optional
ceiling surface. The corridor is defined by a center line Y value and a
half-width at each X position. The player must fly within the corridor
without touching either surface.

### Corridor profile
```python
@dataclass
class CorridorSlice:
    x: float           # world X of this slice
    floor_y: float     # top of floor surface at this X
    ceiling_y: float   # bottom of ceiling surface (None if no ceiling)
```

The corridor profile is a list of `CorridorSlice` objects spaced at
chunk intervals across the full world width. This list is the source of
truth for both rendering and collision detection.

### Difficulty parameters (driven by level config)
| Parameter | Level 1 | Level N |
|-----------|---------|---------|
| Center amplitude | low | high |
| Center frequency | low | high |
| Half-width | wide | narrow |
| Ceiling present | no | yes (from ~level 3) |
| Ceiling tightness | — | increases per level |

### Chunk-based rendering
The corridor profile is rendered in chunks. A chunk covers a fixed X
span (e.g. 64 px). Only chunks within camera view plus a small buffer
ahead and behind are active in the SpriteList or polygon list. Chunks
are added on the right as the camera advances and removed on the left
when they exit the culling threshold.

### TerrainBase abstract interface
```python
class TerrainBase(ABC):
    def __init__(self, profile: list[CorridorSlice], config: TerrainConfig):
        ...

    @abstractmethod
    def update(self, camera_x: float) -> None:
        """Add/remove chunks based on camera position."""

    @abstractmethod
    def draw(self) -> None:
        """Draw active chunks. Called inside world_camera context."""

    def floor_y_at(self, world_x: float) -> float:
        """Return floor Y at given world X. O(1) lookup."""

    def ceiling_y_at(self, world_x: float) -> float | None:
        """Return ceiling Y at given world X, or None if no ceiling."""

    def point_in_terrain(self, world_x: float, world_y: float) -> bool:
        """Return True if point is inside floor or ceiling geometry."""
```

### Two renderer subclasses (Phase 1)
- **`TileTerrainRenderer`** — floor and ceiling built from small square
  sprite tiles in a SpriteList with `use_spatial_hash=True` (terrain
  never moves). Chunky retro look.
- **`PolygonTerrainRenderer`** — floor and ceiling rendered as filled
  polygons using Arcade drawing primitives. Collision via
  `point_in_terrain()` using the corridor profile directly (no spatial
  hash needed — O(1) lookup by X index). Smoother look.

Both subclasses implement identical `TerrainBase` interfaces. The test
view can switch between them with a keypress.

---

## Ship Physics

Inherited conceptually from Space Attackers' momentum model. The player
ship has a velocity vector. Input applies acceleration. No input applies
friction deceleration back toward zero. This gives the ship weight and
inertia.

```python
# Per-frame update sketch
self.velocity_x += input_x * ACCEL * delta_time
self.velocity_y += input_y * ACCEL * delta_time
self.velocity_x *= FRICTION ** delta_time
self.velocity_y *= FRICTION ** delta_time
self.position += self.velocity * delta_time
```

ACCEL and FRICTION are config parameters in `game_config.toml`.

### Camera clamp on X
After updating ship world position, enforce the camera minimum X:
```python
ship_world_x = max(ship_world_x, self.world_camera.position.x - LEFT_MARGIN)
```
The ship cannot move left of the camera's left edge plus a small margin.
The ship can slow to zero horizontal velocity but cannot scroll the
camera backward.

### Fuel-empty physics (Phase 3)
When fuel reaches zero:
- Input is disabled
- Gravity constant applied to `velocity_y` each frame (downward)
- `velocity_x` retains current value and decays via friction normally
- Terrain contact at any velocity = instant death (100% damage)

---

## State Machine

Follows identical pattern to Space Attackers `GameStateManager`.

```python
class GameState(Enum):
    SPLASH = auto()
    MAIN_MENU = auto()
    RUN_LEVEL = auto()
    PLAYER_KILLED = auto()
    LEVEL_COMPLETE = auto()
    BOSS_FIGHT = auto()      # may merge with RUN_LEVEL — decide in Phase 7
    GAME_OVER = auto()
    HIGH_SCORES = auto()
    SCORE_ENTRY = auto()
```

agf views (SplashView, MainMenuView, GameOverView, ScoreEntryView,
LevelCompleteView) are reused directly as in Space Attackers.

---

## Configuration Pattern

Follows Space Attackers `GameConfig` pattern exactly. TOML file at
project root (resolved via `agf.paths.config_path()`).

```toml
[window]
width = 1280
height = 720
title = "Base Attackers"

[ship]
accel = 400.0
friction = 0.85
max_speed_x = 350.0
max_speed_y = 300.0
fuel_capacity = 100.0
fuel_drain_rate = 3.5        # units per second
gravity_when_empty = 120.0   # px/s² downward

[terrain]
chunk_width = 64
cull_buffer_chunks = 3       # chunks kept outside camera each side

[level_1]
world_width = 6400
world_height = 720
terrain_amplitude = 80.0
terrain_frequency = 0.008
terrain_half_width = 280.0
ceiling_present = false
scroll_speed_base = 120.0    # px/s minimum forward camera advance
```

---

## Asset Strategy

All assets live in `base_attackers/assets/`. agf contains no assets.

| Asset type | Source | Notes |
|------------|--------|-------|
| Ship sprite | Kenney Space Shooter Redux | Copy from Space Attackers assets |
| Explosion sheets | Kenney Space Shooter Redux | Copy from Space Attackers assets |
| Bullet sprites | Kenney Space Shooter Redux | Copy from Space Attackers assets |
| Enemy sprites | Kenney Space Shooter Redux / Extension | Select per enemy type |
| Terrain tiles | Kenney (TBD) | Chosen after Phase 1 renderer decision |
| Fonts | KenVector Future / KenVector Future Thin | Copy from Space Attackers assets |
| SFX | OpenGameArt.org CC0 | Reuse Space Attackers SFX where appropriate |
| Music | OpenGameArt.org CC0 | One track per level — sourced in Phase 9 |

**Never use `bold=True`** with KenVector Future — no bold variant exists,
Linux falls back to system font.

---

## agf Changes Planned for Base Attackers

All agf changes are **additive only**. No existing agf class is modified.
Space Attackers on agf v0.2.0 is unaffected by all of these.

| Change | Phase | Description |
|--------|-------|-------------|
| `ScrollingGameWindow` | 1 | Subclass of `GameWindowBase` with dual cameras |
| `MomentumShipMixin` | 2 | Generalised momentum/friction physics |
| World-space `PowerUpSpawner` | 5 | Spawns at world coords, culls on left edge |

When these additions are stable, tag agf **v0.3.0** and pin Base
Attackers to it.

---

## Arcade 3.x Rules (inherited from Space Attackers CLAUDE.md)

These apply to Base Attackers without exception:

- Use `self.clear()` — never `arcade.start_render()`
- `SpriteList.update()` requires `delta_time` argument
- **Never** use `ShapeElementList` for moving objects — microstutter
- **Never** use `arcade.draw_text()` in `on_draw()` — use `arcade.Text`
  objects
- **Never** use `bold=True` with KenVector Future fonts
- Commit via terminal, not VS Code UI, to trigger pre-commit hooks
- Spatial hashing only on SpriteLists that never move (terrain tiles: ✅,
  bullets: ❌, enemies: ❌)
- Force XAudio2 on Windows before arcade init:
  `pyglet.options["audio"] = ("xaudio2", "directsound", "openal", "silent")`

---

## Development Workflow Reminder

- **Claude.ai** — architecture, feature brief writing
- **Claude Code** — implementation only, works from briefs in `docs/features/`
- **Two VS Code windows** — one for agf repo, one for Base Attackers
- **Brief location** — `docs/features/phase-N-title.md`
- **CLAUDE.md** — update after every significant architectural decision
- **Commits** — terminal only, pre-commit hooks run Black + Ruff
- **agf session** — open agf repo in its own VS Code window when making
  agf changes; commit and push agf before pulling into Base Attackers
