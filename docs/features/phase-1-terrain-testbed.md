# Feature Brief — Phase 1: Project Bootstrap & Terrain Testbed

**Game:** Base Attackers
**Phase:** 1 of 9
**Depends on:** agf v0.2.0, architecture-overview.md
**Output:** Runnable terrain testbed — no ship, no combat, two switchable
terrain renderers scrolling across the screen
**agf changes required:** Yes — `ScrollingGameWindow` added to agf first

---

## Goals

1. Bootstrap the Base Attackers project from the cookiecutter template
2. Add `ScrollingGameWindow` to agf (dual-camera support)
3. Implement `TerrainBase` abstract class and corridor profile generator
4. Implement `TileTerrainRenderer` — sprite-based chunky terrain
5. Implement `PolygonTerrainRenderer` — smooth polygon terrain
6. Wire both into a `TerrainTestView` with live renderer switching
7. Commit everything, run on Windows and Ubuntu, playtest

---

## Step 0 — Before Writing Any Code

Read the following in order:

1. `docs/architecture-overview.md` in this repo (Base Attackers)
2. `agf/src/agf/window.py` — understand `GameWindowBase` before subclassing
3. `agf/src/agf/state.py` — understand `BaseGameStateManager`
4. `agf/pyproject.toml` — confirm current version is 0.2.0

Do **not** rely on README files as ground truth — read the source.

---

## Part A — agf Changes (do this first, in the agf VS Code window)

### A1. Add `ScrollingGameWindow` to `agf/src/agf/window.py`

Add a new class **below** `GameWindowBase`. Do not modify `GameWindowBase`.

```python
class ScrollingGameWindow(GameWindowBase):
    """
    GameWindowBase subclass for games with a scrolling world.
    Provides a world-space camera and a GUI/HUD camera.
    The GUI camera never moves. The world camera is controlled
    by the game's RunLevelView.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.world_camera: arcade.Camera2D = arcade.Camera2D()
        self.gui_camera: arcade.Camera2D = arcade.Camera2D()

    def use_world_camera(self) -> None:
        """Activate world camera. Call before drawing world-space content."""
        self.world_camera.use()

    def use_gui_camera(self) -> None:
        """Activate GUI camera. Call before drawing HUD/screen-space content."""
        self.gui_camera.use()
```

### A2. Export from agf `__init__.py`

Add `ScrollingGameWindow` to `agf/src/agf/__init__.py` exports so
Base Attackers can import it as `from agf import ScrollingGameWindow`.

### A3. Commit agf changes

```bash
cd path/to/arcade-game-framework
git add -A
git commit -m "feat: add ScrollingGameWindow with dual-camera support"
git push
```

Do **not** tag a new agf release yet — that happens at Phase 9 once all
agf additions for Base Attackers are complete.

---

## Part B — Bootstrap Base Attackers Project

### B1. Generate from cookiecutter template

```bash
cookiecutter gh:darthwilliam1118/arcade-game-template
# project_name: Base Attackers
# project_slug: base_attackers
# github_username: darthwilliam1118
```

### B2. Update pyproject.toml dependency

Pin agf to the current commit SHA on main (not a tag yet — tag comes
at Phase 9). Use the SHA of the agf commit that added
`ScrollingGameWindow`:

```toml
[project]
dependencies = [
    "arcade==3.3.3",
    "arcade-game-framework @ git+https://github.com/darthwilliam1118/arcade-game-framework.git@<SHA>",
]
```

### B3. Create directory structure

Create these empty packages (with `__init__.py`) inside
`src/base_attackers/`:

```
terrain/
    __init__.py
    terrain_base.py
    tile_terrain.py
    polygon_terrain.py
views/
    __init__.py
    terrain_test.py
```

### B4. Copy assets from Space Attackers

Copy the following into `base_attackers/assets/`:

**User action required — copy these manually from Space Attackers:**
- `assets/fonts/` — entire folder (KenVector Future TTF files)
- `assets/images/exp2_0.png` — explosions
- `assets/images/PNG/Lasers/` — entire folder
- `assets/sounds/` — entire folder (SFX and music)

**User action required — select a player ship sprite:**
- Browse Kenney Space Shooter Redux pack
- Pick a ship sprite that faces right (this is a side-scroller)
- Copy to `assets/images/PNG/playerShip1.png`
- Copy to `assets/images/PNG/playerShip2.png`

Terrain tile assets are **not needed yet** — chosen after Phase 1
playtest based on which renderer is selected.

### B5. Create `game_config.toml`

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

[terrain]
chunk_width = 64
cull_buffer_chunks = 3

[level_1]
world_width = 6400
world_height = 720
terrain_amplitude = 80.0
terrain_frequency = 0.008
terrain_half_width = 280.0
ceiling_present = false
```

### B6. Update `main.py` to use `ScrollingGameWindow`

```python
from agf import ScrollingGameWindow
# Replace GameWindowBase with ScrollingGameWindow in window instantiation
```

---

## Part C — Terrain Implementation

### C1. Corridor profile data structures (`terrain/terrain_base.py`)

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
import random


@dataclass
class CorridorSlice:
    """The terrain profile at a single X position."""
    x: float
    floor_y: float          # world Y of the top of the floor surface
    ceiling_y: float | None  # world Y of the bottom of ceiling (None = open sky)


@dataclass
class TerrainConfig:
    world_width: float
    world_height: float
    chunk_width: int         # px width of one renderable chunk
    cull_buffer_chunks: int  # extra chunks to keep outside camera each side
    amplitude: float         # max deviation of corridor center from midpoint
    frequency: float         # spatial frequency of center line wander (cycles/px)
    half_width: float        # half the clear corridor width in px
    ceiling_present: bool
```

### C2. Corridor profile generator

Add a module-level function (not a method) in `terrain_base.py`:

```python
def generate_corridor_profile(
    config: TerrainConfig,
    seed: int | None = None,
) -> list[CorridorSlice]:
    """
    Generate a corridor profile for the full world width.
    One CorridorSlice per chunk_width pixels.
    
    Center line wanders using layered sine waves at different
    frequencies and amplitudes for organic feel.
    Seed allows reproducible generation for testing.
    """
```

Implementation notes:
- Use two or three sine waves at different frequencies summed together —
  this produces more natural-looking terrain than a single sine wave
- Multiply by a smoothstep ramp at the start and end of the level so
  terrain opens wide at entry and widens again at the boss zone (last
  10% of world width)
- If `ceiling_present` is True, ceiling Y = floor_y + (half_width * 2)
  with the center line between them
- Clamp floor_y so it never goes below 0 or above world_height - min_gap
- `min_gap` should be at least 180px to always leave room for the ship

### C3. `TerrainBase` abstract class

```python
class TerrainBase(ABC):
    def __init__(self, profile: list[CorridorSlice], config: TerrainConfig):
        self.profile = profile
        self.config = config
        self._slice_map: dict[int, CorridorSlice] = {
            int(s.x // config.chunk_width): s for s in profile
        }

    def floor_y_at(self, world_x: float) -> float:
        """O(1) floor height lookup by world X."""
        idx = int(world_x // self.config.chunk_width)
        idx = max(0, min(idx, len(self.profile) - 1))
        return self.profile[idx].floor_y

    def ceiling_y_at(self, world_x: float) -> float | None:
        """O(1) ceiling height lookup by world X. None if no ceiling."""
        idx = int(world_x // self.config.chunk_width)
        idx = max(0, min(idx, len(self.profile) - 1))
        return self.profile[idx].ceiling_y

    def point_in_terrain(self, world_x: float, world_y: float) -> bool:
        """True if point is inside floor or ceiling geometry."""
        floor = self.floor_y_at(world_x)
        if world_y <= floor:
            return True
        ceiling = self.ceiling_y_at(world_x)
        if ceiling is not None and world_y >= ceiling:
            return True
        return False

    @abstractmethod
    def update(self, camera_x: float) -> None:
        """Manage active chunks based on current camera X position."""

    @abstractmethod
    def draw(self) -> None:
        """Draw active chunks. Must be called inside world_camera context."""
```

### C4. `TileTerrainRenderer` (`terrain/tile_terrain.py`)

- Terrain tiles are square sprites of size == `chunk_width`
- Floor: stack tiles from world Y 0 up to `floor_y` for each chunk
- Ceiling: stack tiles from `ceiling_y` up to `world_height` for each
  chunk (when ceiling is present)
- All tiles go into a single `arcade.SpriteList` with
  `use_spatial_hash=True` — terrain never moves so spatial hashing is
  valid and fast
- `update()` adds new chunk columns on the right as camera advances,
  removes columns on the left when they exit cull threshold
- Tile texture: use `arcade.make_image_texture()` with a simple solid
  color for Phase 1 — real tile sprites selected after renderer decision
- Tile color suggestion for testbed: `(80, 120, 60)` earthy green

### C5. `PolygonTerrainRenderer` (`terrain/polygon_terrain.py`)

- No sprites — draw filled polygons using `arcade.draw_polygon_filled()`
- Each active chunk is a trapezoid from world Y 0 to floor_y (floor) or
  from ceiling_y to world_height (ceiling)
- Build a list of active chunk polygons; redraw each frame from the list
- `update()` adds/removes chunks same as tile renderer
- Collision uses `point_in_terrain()` from base class — O(1) lookup via
  corridor profile, no spatial hash needed
- **Note:** `ShapeElementList` is NOT used here — the polygon list is
  redrawn each frame using immediate-mode draw calls. ShapeElementList
  would cause microstutter if any chunk is ever added or removed.
- Color suggestion for testbed: `(60, 100, 140)` blue-grey rock

---

## Part D — Terrain Test View (`views/terrain_test.py`)

This view has no ship, no HUD, no game state. Pure terrain showcase.

### Controls
| Key | Action |
|-----|--------|
| T | Toggle between TileTerrainRenderer and PolygonTerrainRenderer |
| R | Regenerate terrain with new random seed |
| → / D | Scroll camera right manually |
| ← / A | Scroll camera left (allowed in testbed — no ship clamp yet) |
| 1–5 | Jump to difficulty preset (see below) |
| ESC | Quit |

### Difficulty presets (for tuning)
```python
PRESETS = {
    1: TerrainConfig(amplitude=60,  frequency=0.005, half_width=300, ceiling_present=False),
    2: TerrainConfig(amplitude=100, frequency=0.007, half_width=260, ceiling_present=False),
    3: TerrainConfig(amplitude=130, frequency=0.010, half_width=220, ceiling_present=True),
    4: TerrainConfig(amplitude=160, frequency=0.013, half_width=185, ceiling_present=True),
    5: TerrainConfig(amplitude=190, frequency=0.016, half_width=155, ceiling_present=True),
}
```

### On-screen debug overlay (GUI camera space)
Display using `arcade.Text` objects (never `arcade.draw_text()`):
- Current renderer name (TILE / POLYGON)
- Current difficulty preset number
- Current seed
- Camera X position
- Active chunk count
- FPS

### `on_draw()` structure
```python
def on_draw(self):
    self.clear()
    self.window.use_world_camera()
    self._terrain.draw()
    self.window.use_gui_camera()
    # draw all arcade.Text debug objects
```

### Startup
`main.py` should launch directly into `TerrainTestView` for Phase 1.
The full state machine is wired in Phase 2 when the ship is added.

---

## Part E — CLAUDE.md Updates

After implementing, update `CLAUDE.md` in Base Attackers with:

- The dual-camera usage pattern (`use_world_camera()` / `use_gui_camera()`)
- The `TerrainBase` interface and where to find it
- The `CorridorSlice` data structure
- The Arcade 3.x rules (copy from Space Attackers CLAUDE.md — all apply)
- The renderer toggle keybind for future reference
- The chunk culling strategy

---

## Commit Sequence

Make separate commits for logical units — do not commit everything at once:

```bash
# After Part A (in agf repo)
git commit -m "feat: add ScrollingGameWindow with dual-camera support"

# After Part B bootstrap
git commit -m "chore: bootstrap Base Attackers from cookiecutter template"

# After Part C terrain base + profile generator
git commit -m "feat: terrain corridor profile generator and TerrainBase"

# After tile renderer
git commit -m "feat: TileTerrainRenderer with spatial-hashed SpriteList"

# After polygon renderer  
git commit -m "feat: PolygonTerrainRenderer with immediate-mode draw"

# After test view
git commit -m "feat: TerrainTestView with renderer toggle and debug overlay"

# Final
git commit -m "chore: update CLAUDE.md with Phase 1 architecture notes"
```

All commits via terminal to trigger pre-commit hooks (Black + Ruff).

---

## Playtest Checklist

Run the testbed and work through this checklist before declaring Phase 1
complete:

**Functionality**
- [ ] Game launches without errors on Windows
- [ ] Game launches without errors on Ubuntu
- [ ] T key switches between TILE and POLYGON renderers cleanly
- [ ] R key regenerates terrain with a new seed — visually different each time
- [ ] Difficulty presets 1–5 produce visibly different terrain profiles
- [ ] Preset 3–5 show a ceiling as well as a floor
- [ ] Camera scrolls smoothly with arrow keys — no stutter
- [ ] Debug overlay shows correct values and updates each frame

**Visual quality**
- [ ] Tile renderer — terrain looks clean, no gaps between tiles
- [ ] Polygon renderer — terrain looks smooth, no visible seams between chunks
- [ ] Both renderers — the level entry zone is wide and open (smoothstep ramp)
- [ ] Both renderers — terrain never creates an impossible gap (min 180px clear)
- [ ] Preset 5 — tunnel feels genuinely tight and threatening

**Performance**
- [ ] Tile renderer — stable 60fps across full world width scroll
- [ ] Polygon renderer — stable 60fps across full world width scroll
- [ ] No frame spikes when chunks are added or removed at camera edges

**Renderer decision**
- [ ] After playtesting both, decide which renderer to use for Phase 2
- [ ] Note decision and reasoning in a comment at top of chosen renderer file
- [ ] Note decision in CLAUDE.md

---

## User Actions Required (Summary)

These cannot be done by Claude Code — they require your input:

1. **Copy assets** from Space Attackers into `base_attackers/assets/`
   (fonts, explosions, bullets, sounds)
2. **Select a player ship sprite** from Kenney Space Shooter Redux that
   faces right — copy to `assets/images/ships/player_ship.png`
3. **Run on both Windows and Ubuntu** and confirm no platform-specific errors
4. **Play through all 5 difficulty presets** on both renderers and decide
   which renderer to use going forward
5. **Report renderer decision** back to Claude.ai before starting Phase 2
   brief — Phase 2 terrain tile asset selection depends on this choice
