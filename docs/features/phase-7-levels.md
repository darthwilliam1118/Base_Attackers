# Feature Brief — Phase 7: Procedural Level Generation & Level Flow

**Game:** Base Attackers
**Phase:** 7 of 9
**Depends on:** Phase 6 complete — all enemy types working, debug mode in place
**Output:** Fully procedural level generation replacing all hardcoded
positions; smooth level-to-level progression; main menu → game →
level complete → next level → game over → high score flow wired end
to end; boss zone threshold trigger placeholder for Phase 8
**agf changes required:** None — all level generation is game-specific

---

## Goals

1. `LevelGenerator` — procedural placement of towers, silos, turrets,
   laser turrets within a level based on difficulty parameters derived
   from level number. No hardcoded positions anywhere.
2. Difficulty curve — single `difficulty(level)` function 0.0→1.0
   driving all density and parameter lerps
3. Boss zone reservation — last 15% of world width kept clear of all
   terrain enemies; boss trigger threshold at 85%
4. Level config in `game_config.toml` — min/max tunable parameters for
   every placement rule; no magic numbers in code
5. Full level flow — `LEVEL_COMPLETE` state wired to agf
   `LevelCompleteView`; level number increments; `RunLevelView` rebuilt
   for new level; `GAME_OVER` wired to agf `GameOverView` with score;
   lives system; splash → main menu → game init → level flow
6. Remove all `_PHASE3_*`, `_PHASE4_*`, `_PHASE6_*` hardcoded position
   constants from `run_level.py`
7. Music — one track per level via agf `MusicPlayer`; track selected
   by level number
8. Commit, run on both platforms, full playthrough test

---

## Step 0 — Before Writing Any Code

Read in order:
1. `docs/architecture-overview.md`
2. `src/base_attackers/views/run_level.py` — full current file. Key
   sections:
   - `__init__()` — `_level_num` sourced from `players[idx].current_level`
     already; this is the right hook for level progression
   - `on_show_view()` — `_place_*` calls replaced by `LevelGenerator`
   - `_update_camera()` — right-edge clamp already implemented; boss
     zone trigger slots in here or in `on_update()`
   - `_destroy_ship()` — lives decrement goes here before GAME_OVER
   - `_PHASE3_TOWER_POSITIONS`, `_PHASE4_SILO_POSITIONS`,
     `_PHASE4_TURRET_POSITIONS`, `_PHASE6_LASER_POSITIONS` — all removed
3. `src/base_attackers/state.py` — current `GameState` enum and
   transition handlers; understand what states exist and what context
   keys are passed between views
4. `src/base_attackers/game_config.py` — `GameConfig`, `LevelSettings`,
   all dataclasses; `levels: dict[int, LevelSettings]` already parsed
5. `src/base_attackers/game.py` — `GameWindow`, music loading pattern,
   `_manager.context["config"]`
6. `agf/src/agf/views/` — read `level_complete.py`, `game_over.py`,
   `main_menu.py`, `splash.py` — understand what context keys they
   expect and what states they transition to
7. `agf/src/agf/player_state.py` — `PlayerState` dataclass; `lives`,
   `score`, `current_level` fields
8. `agf/src/agf/high_scores.py` — `HighScoreTable` API
9. `agf/src/agf/music.py` — `MusicPlayer` API; `load_track()`,
   `play()`, `stop()`
10. `assets/sounds/` — list available music files; one per level ideally,
    fall back to a single track if only one exists

Do NOT rely on README files. Read actual source.

---

## Part A — Config Extensions

### A1. Add level generation parameters to `game_config.toml`

These are the tunable knobs for the procedural generator. All enemy
density and spacing values lerp between `_min` (level 1) and `_max`
(max difficulty level) using the difficulty curve.

```toml
[level_gen]
max_difficulty_level = 10      # level at which difficulty reaches 1.0
boss_zone_fraction = 0.85      # world X fraction where boss zone starts
entry_clear_fraction = 0.05    # first N% of world kept clear (entry zone)

# Fuel towers — guaranteed refuel points; count decreases with difficulty
# (fewer towers = more pressure). Min count is a safety floor.
tower_count_max = 4            # level 1
tower_count_min = 2            # max difficulty
tower_min_spacing = 800.0      # minimum px between towers
tower_ceiling_unlock_level = 4 # level at which ceiling towers can appear

# Missile silos
silo_density_min = 0.0003      # silos per px of playfield at level 1
silo_density_max = 0.0010      # silos per px at max difficulty
silo_min_spacing = 350.0       # minimum px between any two silos
silo_ceiling_fraction_min = 0.0   # fraction of silos on ceiling at level 1
silo_ceiling_fraction_max = 0.5   # fraction on ceiling at max difficulty
silo_unlock_level = 1          # available from level 1

# Gun turrets
turret_density_min = 0.0002
turret_density_max = 0.0008
turret_min_spacing = 400.0
turret_ceiling_fraction_min = 0.0
turret_ceiling_fraction_max = 0.4
turret_unlock_level = 1

# Laser turrets
laser_density_min = 0.0
laser_density_max = 0.0004
laser_min_spacing = 600.0
laser_ceiling_fraction_min = 0.0
laser_ceiling_fraction_max = 0.3
laser_unlock_level = 3         # not available until level 3

# Lives
lives_per_level_start = 3      # lives granted at game start
```

### A2. Add music track mapping to `game_config.toml`

```toml
[music]
# Map level number to track name (loaded via agf MusicPlayer).
# If a level has no entry, falls back to "default".
# Track names must match filenames in assets/sounds/ without extension.
level_1 = "level1"
level_2 = "level2"
default = "level1"             # fallback if level has no track
menu = "ending"                # already loaded in game.py
```

### A3. Add `LevelGenSettings` dataclass to `game_config.py`

```python
@dataclass
class LevelGenSettings:
    max_difficulty_level: int = 10
    boss_zone_fraction: float = 0.85
    entry_clear_fraction: float = 0.05

    tower_count_max: int = 4
    tower_count_min: int = 2
    tower_min_spacing: float = 800.0
    tower_ceiling_unlock_level: int = 4

    silo_density_min: float = 0.0003
    silo_density_max: float = 0.0010
    silo_min_spacing: float = 350.0
    silo_ceiling_fraction_min: float = 0.0
    silo_ceiling_fraction_max: float = 0.5
    silo_unlock_level: int = 1

    turret_density_min: float = 0.0002
    turret_density_max: float = 0.0008
    turret_min_spacing: float = 400.0
    turret_ceiling_fraction_min: float = 0.0
    turret_ceiling_fraction_max: float = 0.4
    turret_unlock_level: int = 1

    laser_density_min: float = 0.0
    laser_density_max: float = 0.0004
    laser_min_spacing: float = 600.0
    laser_ceiling_fraction_min: float = 0.0
    laser_ceiling_fraction_max: float = 0.3
    laser_unlock_level: int = 3

    lives_per_level_start: int = 3
```

Add `level_gen: LevelGenSettings` to `GameConfig` and parse `[level_gen]`
in `GameConfig.load()` following the existing pattern.

Also add `music_tracks: dict[str, str]` to `GameConfig` parsed from
`[music]` section.

---

## Part B — LevelGenerator

Create `src/base_attackers/levels/level_generator.py`.

```
src/base_attackers/levels/
    __init__.py
    level_generator.py
```

### B1. Difficulty curve

```python
def difficulty(level: int, max_level: int = 10) -> float:
    """Returns 0.0 at level 1, 1.0 at level max_level and beyond."""
    return min(1.0, (level - 1) / max(1, max_level - 1))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t
```

### B2. Placement dataclasses

```python
@dataclass
class TowerPlacement:
    x: float
    surface: str   # "floor" always for now; "ceiling" unlocked later

@dataclass
class SiloPlacement:
    x: float
    surface: str

@dataclass
class TurretPlacement:
    x: float
    surface: str

@dataclass
class LaserPlacement:
    x: float
    surface: str

@dataclass
class LevelLayout:
    """Complete procedural layout for one level."""
    level_num: int
    towers: list[TowerPlacement]
    silos: list[SiloPlacement]
    turrets: list[TurretPlacement]
    lasers: list[LaserPlacement]
    boss_zone_x: float          # world X where boss zone begins
    entry_clear_x: float        # world X where entry clear zone ends
```

### B3. LevelGenerator class

```python
class LevelGenerator:
    """Generates a complete procedural level layout from difficulty params.

    All randomness is seeded from (level_num, run_seed) so the layout
    is reproducible for a given run but differs between runs.
    """

    def __init__(self, cfg: "GameConfig") -> None:
        self._cfg = cfg
        self._gen_cfg = cfg.level_gen

    def generate(
        self, level_num: int, world_width: float, ceiling_present: bool,
        run_seed: int | None = None,
    ) -> LevelLayout:
        import random
        rng = random.Random(run_seed if run_seed is not None else level_num)

        gc = self._gen_cfg
        d = difficulty(level_num, gc.max_difficulty_level)

        boss_zone_x    = world_width * gc.boss_zone_fraction
        entry_clear_x  = world_width * gc.entry_clear_fraction
        playfield_w    = boss_zone_x - entry_clear_x

        towers  = self._place_towers(rng, d, entry_clear_x, boss_zone_x,
                                     ceiling_present, level_num)
        silos   = self._place_enemies(
            rng, d, entry_clear_x, boss_zone_x, playfield_w,
            gc.silo_density_min, gc.silo_density_max, gc.silo_min_spacing,
            gc.silo_ceiling_fraction_min, gc.silo_ceiling_fraction_max,
            ceiling_present, gc.silo_unlock_level, level_num,
            placement_cls=SiloPlacement,
        )
        turrets = self._place_enemies(
            rng, d, entry_clear_x, boss_zone_x, playfield_w,
            gc.turret_density_min, gc.turret_density_max, gc.turret_min_spacing,
            gc.turret_ceiling_fraction_min, gc.turret_ceiling_fraction_max,
            ceiling_present, gc.turret_unlock_level, level_num,
            placement_cls=TurretPlacement,
        )
        lasers  = self._place_enemies(
            rng, d, entry_clear_x, boss_zone_x, playfield_w,
            gc.laser_density_min, gc.laser_density_max, gc.laser_min_spacing,
            gc.laser_ceiling_fraction_min, gc.laser_ceiling_fraction_max,
            ceiling_present, gc.laser_unlock_level, level_num,
            placement_cls=LaserPlacement,
        )

        return LevelLayout(
            level_num=level_num,
            towers=towers,
            silos=silos,
            turrets=turrets,
            lasers=lasers,
            boss_zone_x=boss_zone_x,
            entry_clear_x=entry_clear_x,
        )

    # ---- placement helpers -----------------------------------------

    def _place_towers(
        self, rng, d: float, x_min: float, x_max: float,
        ceiling_present: bool, level_num: int,
    ) -> list[TowerPlacement]:
        gc = self._gen_cfg
        count = round(lerp(gc.tower_count_max, gc.tower_count_min, d))
        count = max(1, count)   # always at least one tower
        span  = x_max - x_min
        towers: list[TowerPlacement] = []
        used_x: list[float] = []
        for _ in range(count * 10):   # retry loop
            if len(towers) >= count:
                break
            x = rng.uniform(x_min, x_max)
            if not self._clear_of(x, used_x, gc.tower_min_spacing):
                continue
            can_ceil = (ceiling_present
                        and level_num >= gc.tower_ceiling_unlock_level)
            surface = "ceiling" if (can_ceil and rng.random() < 0.3) else "floor"
            towers.append(TowerPlacement(x=x, surface=surface))
            used_x.append(x)
        return towers

    def _place_enemies(
        self, rng, d: float, x_min: float, x_max: float,
        playfield_w: float,
        density_min: float, density_max: float, min_spacing: float,
        ceil_frac_min: float, ceil_frac_max: float,
        ceiling_present: bool, unlock_level: int, level_num: int,
        placement_cls,
    ) -> list:
        if level_num < unlock_level:
            return []
        density  = lerp(density_min, density_max, d)
        count    = max(0, round(density * playfield_w))
        ceil_frac = lerp(ceil_frac_min, ceil_frac_max, d) if ceiling_present else 0.0
        placed: list = []
        used_x: list[float] = []
        for _ in range(count * 10):
            if len(placed) >= count:
                break
            x = rng.uniform(x_min, x_max)
            if not self._clear_of(x, used_x, min_spacing):
                continue
            surface = "ceiling" if (ceiling_present and rng.random() < ceil_frac) else "floor"
            placed.append(placement_cls(x=x, surface=surface))
            used_x.append(x)
        return placed

    @staticmethod
    def _clear_of(x: float, used: list[float], spacing: float) -> bool:
        return all(abs(x - ux) >= spacing for ux in used)
```

### B4. Also avoid tower/enemy overlap

After generating all placements, run a cross-type clearance pass — no
enemy should sit within `min_spacing / 2` of a tower. Drop the enemy
placement if it conflicts; the retry loop in `_place_enemies` handles
regeneration naturally if you pass the tower X list into it.

Simplest implementation: extend `_clear_of` to accept a combined
`used_x` list that includes tower positions before enemy placement runs.

---

## Part C — RunLevelView Procedural Wiring

### C1. Remove all hardcoded position constants

Delete from `run_level.py`:
```python
_PHASE3_TOWER_POSITIONS = [...]
_PHASE4_SILO_POSITIONS  = [...]
_PHASE4_TURRET_POSITIONS = [...]
_PHASE6_LASER_POSITIONS  = [...]
```

### C2. Add LevelGenerator to `on_show_view()`

Replace the four `_place_*()` calls with a single generator call:

```python
from src.base_attackers.levels.level_generator import LevelGenerator

def on_show_view(self) -> None:
    if self._terrain is None:
        self._terrain, self._terrain_cfg = _build_terrain(...)
        self._spawn_ship()
        ...
        layout = LevelGenerator(self._cfg).generate(
            level_num=self._level_num,
            world_width=self._terrain_cfg.world_width,
            ceiling_present=self._level_cfg.ceiling_present,
        )
        self._boss_zone_x = layout.boss_zone_x
        self._place_from_layout(layout)
        self._build_powerup_system()
    ...
```

### C3. `_place_from_layout()` method

```python
def _place_from_layout(self, layout: "LevelLayout") -> None:
    """Construct all terrain-mounted objects from the procedural layout."""
    assert self._terrain is not None
    for p in layout.towers:
        self._place_tower(p.x, p.surface)
    for p in layout.silos:
        self._place_silo(p.x, p.surface)
    for p in layout.turrets:
        self._place_turret(p.x, p.surface)
    for p in layout.lasers:
        self._place_laser(p.x, p.surface)
```

### C4. Extract single-item placement helpers

Refactor existing `_place_fuel_towers()`, `_place_missile_silos()`,
`_place_gun_turrets()`, `_place_laser_turrets()` into single-item
helpers that take `(x, surface)`. The existing two-step construct +
position pattern is unchanged — just extracted:

```python
def _place_tower(self, x: float, surface: str) -> None:
    tower = FuelTower(world_x=x, world_y=0.0, surface=surface,
                      cfg=self._cfg.fuel_tower, scale=1.0)
    floor_y  = self._terrain.floor_y_at(x)
    ceil_y   = self._terrain.ceiling_y_at(x)
    if surface == "floor":
        tower.center_y = floor_y  + tower.height / 2.0
        tower.dock_y   = tower.center_y + tower.height / 2.0 + 12.0
    else:
        if ceil_y is None:
            return
        tower.center_y = ceil_y - tower.height / 2.0
        tower.dock_y   = tower.center_y - tower.height / 2.0 - 12.0
    self._tower_list.append(tower)
    self._towers.append(tower)

def _place_silo(self, x: float, surface: str) -> None:
    # ... same pattern as existing _place_missile_silos() per-item logic

def _place_turret(self, x: float, surface: str) -> None:
    # ... same as existing _place_gun_turrets() per-item logic

def _place_laser(self, x: float, surface: str) -> None:
    # ... same as existing _place_laser_turrets() per-item logic
```

### C5. Boss zone trigger

Add to `__init__()`:
```python
self._boss_zone_x: float = 0.0   # set from layout in on_show_view
self._boss_triggered: bool = False
```

Add to `on_update()` after `_update_camera()`:

```python
if (
    not self._boss_triggered
    and self._boss_zone_x > 0.0
    and self._ship.center_x >= self._boss_zone_x
):
    self._boss_triggered = True
    self._on_boss_zone_reached()
```

```python
def _on_boss_zone_reached(self) -> None:
    """Phase 7: trigger level complete immediately (boss placeholder).
    Phase 8 replaces this with the boss encounter sequence.
    """
    from src.base_attackers.state import GameState
    log.info(f"Boss zone reached on level {self._level_num}")
    self._trigger_level_complete()

def _trigger_level_complete(self) -> None:
    """Award score, increment level, transition to LEVEL_COMPLETE."""
    from src.base_attackers.state import GameState
    # Update player state in context.
    players = self._manager.context.get("players") or []
    idx     = self._manager.context.get("active_player_index", 0)
    if players and 0 <= idx < len(players):
        players[idx].score        = self._score
        players[idx].current_level += 1
    self._manager.transition(GameState.LEVEL_COMPLETE)
```

Also wire the existing debug shortcut:
```python
def _debug_complete_level(self) -> None:
    self._trigger_level_complete()   # was direct transition — now goes through helper
```

---

## Part D — Lives System

### D1. PlayerState lives field

`agf.player_state.PlayerState` should already have a `lives` field.
Read it before writing anything. If it doesn't, add `lives: int = 3`
to the dataclass (agf change — additive only, Space Attackers
unaffected).

### D2. Decrement lives in `_destroy_ship()`

```python
def _destroy_ship(self) -> None:
    if self._death_timer > 0.0:
        return
    # ... existing explosion + hide ship code ...

    # Decrement lives.
    players = self._manager.context.get("players") or []
    idx     = self._manager.context.get("active_player_index", 0)
    if players and 0 <= idx < len(players):
        players[idx].lives -= 1
        if players[idx].lives <= 0:
            # No lives left — go to game over.
            players[idx].score = self._score
            self._death_timer = _DEATH_DURATION
            # Transition happens in on_update() death timer expiry.
            self._manager.context["death_leads_to_game_over"] = True
            return
    # Lives remain — respawn on same level after death timer.
    self._death_timer = _DEATH_DURATION
```

### D3. Death timer expiry in `on_update()`

```python
if self._death_timer <= 0.0:
    from src.base_attackers.state import GameState
    if self._manager.context.get("death_leads_to_game_over"):
        self._manager.context.pop("death_leads_to_game_over", None)
        self._manager.transition(GameState.GAME_OVER)
    else:
        # Respawn on same level — rebuild RunLevelView.
        self._manager.transition(GameState.RUN_LEVEL)
```

### D4. Lives in HUD

Add a `_hud_lives` Text object in `_build_hud()`:
```python
self._hud_lives = arcade.Text(
    "LIVES 3", sw - 200, sh - 40,
    font_name=FONT_THIN, font_size=14, color=arcade.color.WHITE,
)
```

Update in `_refresh_hud()`:
```python
players = self._manager.context.get("players") or []
idx = self._manager.context.get("active_player_index", 0)
lives = players[idx].lives if players and 0 <= idx < len(players) else 0
self._hud_lives.text = f"LIVES {lives}"
```

Draw in `_draw_hud()`.

---

## Part E — State Machine & Level Flow

Read `src/base_attackers/state.py` carefully before writing anything
here. Understand what transition handlers already exist and what context
keys are set/expected at each transition.

### E1. GameState enum — ensure these states exist

```python
class GameState(Enum):
    SPLASH         = auto()
    MAIN           = auto()
    RUN_LEVEL      = auto()
    TERRAIN_TEST   = auto()
    LEVEL_COMPLETE = auto()
    GAME_OVER      = auto()
    HIGH_SCORES    = auto()
    SCORE_ENTRY    = auto()
```

### E2. Game init state handler

When transitioning to `RUN_LEVEL` for the first time (new game), the
state machine must initialise `PlayerState` objects in context. Add a
`_handle_game_init()` method called from the `MAIN` → `RUN_LEVEL`
transition:

```python
def _handle_game_init(self) -> None:
    """Set up PlayerState(s) in context for a new game."""
    from agf.player_state import PlayerState
    cfg = self.context.get("config") or GameConfig.load()
    player = PlayerState(
        lives=cfg.level_gen.lives_per_level_start,
        score=0,
        current_level=cfg.starting_level,
    )
    self.context["players"] = [player]
    self.context["active_player_index"] = 0
```

Call this in `_enter_state()` when entering `RUN_LEVEL` from `MAIN`
(new game start) but NOT when re-entering from `LEVEL_COMPLETE` or
death respawn (player state must persist).

Guard: `if "players" not in self.context: self._handle_game_init()`

### E3. LEVEL_COMPLETE transition

Wire `LEVEL_COMPLETE` to agf `LevelCompleteView`. Read that view's
source to understand what context keys it reads (score, level number,
etc.) and set them before transitioning.

After `LevelCompleteView` dismisses (player presses any key or timer
expires), it should transition back to `RUN_LEVEL`. `RunLevelView.__init__()`
reads `players[idx].current_level` which was already incremented in
`_trigger_level_complete()` — so the new level loads automatically.

### E4. GAME_OVER transition

Wire `GAME_OVER` to agf `GameOverView`. Read its source for context
keys. Pass `score` from `players[idx].score`. After game over, player
should be offered high score entry if their score qualifies, then
return to `MAIN`.

### E5. Revert dev launch shortcut

In `game.py`, revert the Phase 2 dev shortcut:
```python
# Remove: self._manager.transition(GameState.RUN_LEVEL)
# Restore: self._manager.transition(GameState.SPLASH)
```

---

## Part F — Music Per Level

### F1. Music track selection in `RunLevelView.on_show_view()`

```python
def _start_level_music(self) -> None:
    """Load and play the music track for this level."""
    tracks = self._cfg.music_tracks   # dict[str, str] from config
    key    = f"level_{self._level_num}"
    track  = tracks.get(key, tracks.get("default", "level1"))
    # Stop menu music, start level music.
    self.window.music.stop()
    self.window.music.load_track(track)
    self.window.music.play(track)
```

Call `_start_level_music()` from `on_show_view()` after terrain is built.

### F2. Music track files

**User action required** — check `assets/sounds/` for music files.
If only one track exists (e.g. `ending.ogg`), use it for all levels
by pointing all `[music]` config entries at it. Source additional
tracks from OpenGameArt.org (CC0) if desired. All music via
`streaming=True` (agf `MusicPlayer` default).

---

## Part G — LevelSettings procedural terrain scaling

The existing `[level_N]` TOML sections define terrain per level. For
levels without an explicit TOML entry, generate terrain settings
procedurally from the difficulty curve rather than using the default
`LevelSettings()` values.

Add a helper to `GameConfig`:

```python
def level_settings_for(self, level_num: int) -> LevelSettings:
    """Return explicit LevelSettings if configured, else generate
    from difficulty curve."""
    if level_num in self.levels:
        return self.levels[level_num]
    d = difficulty(level_num, self.level_gen.max_difficulty_level)
    return LevelSettings(
        world_width=6400.0,
        world_height=min(2160.0, lerp(720.0, 1440.0, d)),
        terrain_amplitude=lerp(80.0, 190.0, d),
        terrain_frequency=lerp(0.008, 0.016, d),
        terrain_half_width=lerp(280.0, 155.0, d),
        ceiling_present=(level_num >= 3),
        terrain_renderer="polygon" if level_num % 2 == 0 else "tile",
        terrain_seed=0,
    )
```

In `RunLevelView.__init__()`, replace:
```python
self._level_cfg = cfg.levels.get(self._level_num, LevelSettings())
```
With:
```python
self._level_cfg = cfg.level_settings_for(self._level_num)
```

---

## Part H — CLAUDE.md Updates

After implementing, add to `CLAUDE.md`:

- `LevelGenerator` is in `src/base_attackers/levels/level_generator.py`.
  Call `generate(level_num, world_width, ceiling_present)` from
  `on_show_view()`. Returns `LevelLayout` with placement lists.
- All `_PHASE*_*_POSITIONS` constants are removed. Do not re-add them.
- `_place_from_layout(layout)` calls four single-item helpers. Add new
  enemy types here when introduced (Phase 8 boss uses same pattern).
- Boss zone: `_boss_zone_x` set from `layout.boss_zone_x` in
  `on_show_view()`. `_boss_triggered` guards single-fire. Phase 8
  replaces `_on_boss_zone_reached()` body.
- Lives: stored in `PlayerState.lives` in `context["players"][0]`.
  `_destroy_ship()` decrements and sets `death_leads_to_game_over`
  context key when lives reach 0.
- `_trigger_level_complete()` increments `current_level` in PlayerState
  before transitioning. Do not call `GameState.LEVEL_COMPLETE` directly
  from anywhere else.
- `cfg.level_settings_for(n)` returns procedural `LevelSettings` for
  levels not explicitly in `game_config.toml`.
- Music: `_start_level_music()` called from `on_show_view()`. Track
  name from `cfg.music_tracks` dict keyed by `"level_N"`.
- Dev launch shortcut (`GameState.RUN_LEVEL` in `game.py`) is reverted
  to `GameState.SPLASH` in Phase 7.

---

## Commit Sequence

```bash
git commit -m "feat: LevelGenSettings config dataclass and game_config.toml entries"
git commit -m "feat: LevelGenerator procedural placement with difficulty curve"
git commit -m "feat: RunLevelView _place_from_layout replacing hardcoded positions"
git commit -m "feat: boss zone trigger threshold and _on_boss_zone_reached hook"
git commit -m "feat: lives system in PlayerState and _destroy_ship decrement"
git commit -m "feat: full level flow — LEVEL_COMPLETE, GAME_OVER, respawn wired"
git commit -m "feat: procedural LevelSettings for levels without explicit config"
git commit -m "feat: per-level music track selection"
git commit -m "chore: revert dev launch shortcut to SPLASH"
git commit -m "chore: update CLAUDE.md with Phase 7 patterns"
```

---

## Playtest Checklist

**Procedural generation**
- [ ] Each run produces visibly different enemy positions
- [ ] No enemies in the entry zone (first 5% of world width)
- [ ] No enemies in the boss zone (last 15% of world width)
- [ ] No two silos within `silo_min_spacing` px of each other
- [ ] No turret within `turret_min_spacing` of another turret
- [ ] No enemies overlapping fuel towers
- [ ] At least one fuel tower always present
- [ ] Level 1: no laser turrets (unlock_level = 3)
- [ ] Level 3+: laser turrets appear
- [ ] Level 3+: ceiling enemies appear (ceiling_present = true)
- [ ] Higher levels visibly denser and harder than lower levels

**Level flow**
- [ ] Splash screen → main menu → new game starts level 1
- [ ] Reaching boss zone X triggers level complete
- [ ] Level complete screen shows score and level number
- [ ] After level complete, level 2 loads with harder terrain and enemies
- [ ] Level 2 terrain is noticeably different (different seed, params)
- [ ] Player death with lives remaining: respawns on same level, same
      terrain seed, same enemy layout (layout is deterministic from seed)
- [ ] Player death with no lives: game over screen with score
- [ ] Game over → high score entry if score qualifies → main menu

**Lives HUD**
- [ ] Lives count visible in HUD top-right area
- [ ] Count decrements correctly on death
- [ ] God mode prevents lives decrement (test with Shift+G)

**Music**
- [ ] Level music starts when level loads, menu music stops
- [ ] Music changes between levels if multiple tracks configured
- [ ] Music resumes correctly after pause (P key)

**Debug shortcuts still work**
- [ ] Shift+E advances to next level via `_trigger_level_complete()`
- [ ] Shift+G toggles god mode
- [ ] Shift+K kills ship (tests death/respawn flow)
- [ ] Shift+P spawns random power-up

**Full playthrough**
- [ ] Play level 1 start to boss zone — complete without dying
- [ ] Play level 2 — confirm harder, ceiling present, more enemies
- [ ] Die deliberately on level 1 with 1 life — game over fires correctly
- [ ] Die with 2 lives — respawn on same level

---

## User Actions Required (Summary)

1. **Read agf view sources** before wiring state transitions —
   `LevelCompleteView`, `GameOverView`, `MainMenuView` all expect
   specific context keys; wrong keys cause silent failures or crashes
2. **Read `PlayerState`** — confirm `lives` field exists before writing
   the lives decrement code; add to agf if missing (additive change)
3. **Check music files** in `assets/sounds/` — update `[music]` config
   to point at actual filenames. If only one track exists, use it for
   all levels.
4. **Tune `[level_gen]` parameters** during playtest — the density
   values in the brief are starting points. Adjust until level 1 feels
   appropriately sparse and level 5+ feels genuinely threatening.
5. **Run on both Windows and Ubuntu** — level generation is pure Python
   (no arcade calls) so platform issues are unlikely, but confirm the
   full flow runs on both.
6. **Report back to Claude.ai** before Phase 8:
   - Final tuned `[level_gen]` density and spacing values
   - How many levels feel distinct before the difficulty plateaus
   - Whether the boss zone feels like the right size / position
   - Any state machine transition issues found during flow testing
