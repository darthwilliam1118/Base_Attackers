# Base Attackers — Claude Code Guidelines

## Project structure
- src/base_attackers/ — game source code
- assets/                — images, fonts, sounds, music
- tests/                 — pytest tests
- game_config.toml       — user-editable config
- main.py                — entry point
- docs/features/         — one feature brief per phase; read the relevant
                           brief before implementing each phase

## Framework dependency
agf (arcade-game-framework) is installed as a dependency.
Source: https://github.com/darthwilliam1118/arcade-game-framework
Version: v0.3.0 (Base Attackers support complete — ScrollingGameWindow,
MomentumShipMixin, WorldSpacePowerUpSpawner, music track cycling). Pinned
to the tag in `pyproject.toml`. Space Attackers stays on v0.2.0. Bump the
pin and
`pip install -e ".[dev]" --force-reinstall --no-deps "arcade-game-framework @ git+…@<ref>"`
whenever agf gains a new piece this game depends on.
Import as: from agf.paths import resource_path

Do NOT re-implement anything already in agf. Check agf source first.
Game-specific classes (ship, enemies, terrain, bosses, power-up effects)
stay in src/base_attackers/.

## Architecture overview
Read docs/architecture-overview.md before starting any implementation
session. It defines the world coordinate system, dual-camera pattern,
terrain abstraction, ship physics model, and planned agf additions.
It is more authoritative than this file on those topics.

## Key agf modules
- agf.paths.resource_path()      — PyInstaller-safe asset loading
- agf.background                 — StaticBackground, ProceduralStarField
- agf.events.GameEvent           — base game events enum
- agf.high_scores                — HighScoreTable persistence
- agf.music.MusicPlayer          — streaming music management
- agf.sound_manager.SoundManager — per-SFX playback throttle (cap
                                   simultaneous pyglet Players per sound)
- agf.levels.base_level          — BaseLevel abstract interface
- agf.powerups                   — PowerUpManager, effect categories
- agf.ui                         — HUDBase, ScorePopup, text_utils
- agf.views                      — base view classes (subclass these)
- agf.state                      — BaseGameStateManager (subclassed in state.py)
- agf.window                     — GameWindowBase → ScrollingGameWindow
                                   (subclassed in game.py)
- agf.ships.momentum             — MomentumShipMixin, MomentumConfig
                                   (NOT re-exported at the agf top level —
                                   import the submodule explicitly)

## Dual-camera system (Base Attackers specific)
Base Attackers uses ScrollingGameWindow from agf, which provides two cameras:
- world_camera — tracks the player ship in world space; X is monotonically
  increasing (never scrolls back left)
- gui_camera   — fixed at screen origin always; used for all HUD rendering

Always structure on_draw() as:
  def on_draw(self):
      self.clear()
      self.window.use_world_camera()
      # draw terrain, enemies, player, projectiles, power-ups
      self.window.use_gui_camera()
      # draw HUD, fuel gauge, HP bar, score, boss health bar

Never draw HUD elements in world camera context — they will scroll away.
Never draw world objects in gui camera context — they will not scroll.

### Camera tracking (RunLevelView)
- Deadzone constants live in `views/run_level.py`:
    _DEADZONE_LEFT = 0.25, _DEADZONE_RIGHT = 0.65
    _DEADZONE_TOP  = 0.80, _DEADZONE_BOTTOM = 0.20
- Monotonic X clamp via `self._min_camera_left`. Each frame:
    cam_left = max(cam_left_from_deadzone, self._min_camera_left)
    cam_left = min(cam_left, max(0, world_width - sw))   # right edge stop
    self._min_camera_left = cam_left
  The right-edge clamp parks the camera once the world's right edge meets
  the screen's right edge. The monotonic floor means the camera never
  scrolls left, regardless of which direction the ship moves.
- Vertical clamp is `cam_bottom ∈ [0, max(0, world_h - sh)]`. While
  `world_height <= window_height` (Phase 2's level 1: 720 ≤ 800), the
  bound degenerates to 0 and the camera doesn't scroll vertically. It
  re-enables itself once a level has `world_height > window_height`.

### HUD mask
The future HUD lives in the band above the world ceiling. To keep the
tile renderer's ceiling overstack hidden, `RunLevelView` draws a black
`arcade.draw_lrbt_rectangle_filled` in GUI-camera space from
`hud_bottom = world_height - cam_bottom` up to the window top, BEFORE
drawing any HUD text. The bound is computed each frame because
`cam_bottom` varies once vertical scrolling kicks in.

## Where to add game logic
- src/base_attackers/terrain/    — TerrainBase subclasses
- src/base_attackers/ships/      — player ship
- src/base_attackers/enemies/    — turrets, missiles, patrol ships, bosses
- src/base_attackers/powerups/   — SAPowerUpManager subclass, effect overrides
- src/base_attackers/views/run_level.py — main gameplay view
- src/base_attackers/views/terrain_test.py — Phase 1 testbed only

## Architecture principles
- Keep game logic strictly separated from rendering
- Classes like PlayerShip, Enemy, Terrain contain pure logic (position,
  velocity, health, collision bounds) — no direct Arcade draw calls
- Views handle all drawing
- This separation ensures unit tests never need a display
- All logic classes must be instantiatable without a game window
- Do not load image/sound assets in __init__ — lazy load or inject them

## Claude Code behavior
- When implementing a major new feature, make a plan and present it for
  approval before editing any files
- Ask questions needed to resolve ambiguities before writing code
- Do not use unicode characters in debug output — plain ASCII only
- Follow existing patterns in the codebase; do not introduce new patterns
  without discussion
- Read the relevant feature brief in docs/features/ before starting;
  read the source files it references before writing any code
- Do not rely on README files as ground truth — read actual source

## Code quality standards
- Formatter: Black (line length 100). Run `black .` before committing.
- Linter: Ruff. Run `ruff check .` and fix all errors before committing.
- Type hints on all function signatures and return values
- No unused imports, no bare `except:` clauses
- Pylance type checking: basic — fix any type errors before committing

## Before submitting any code
1. `ruff check .` — must be clean
2. `black .` — must be clean
3. No new type errors introduced
4. Existing tests still pass: `pytest --cov=src`

## Commits
- Always commit via terminal, NOT via VS Code UI
- VS Code UI commits skip pre-commit hooks (Black + Ruff won't run)
- Make separate commits per logical unit — not one giant commit per phase

## Testing
- pytest --cov=src
- All tests must run without a display (no arcade.Window needed)
- Inject textures/sounds as optional constructor parameters for testability
- No test should import game-specific rendering code
- GameEvent enum returned from update() methods — never call state machine
  directly from logic classes (keeps classes unit-testable)

---

## Arcade 3.x — Critical API Notes

Claude Code's training data contains significant amounts of Arcade 2.x
code which is NOT compatible. This project uses Arcade 3.3.3. Always use
the 3.x API. Key breaking changes:

### Drawing
- `self.clear()` replaces `arcade.start_render()` — 2.x method REMOVED
- `arcade.finish_render()` REMOVED — not needed in 3.x
- Never call `arcade.draw_text()` inside `on_draw()` — it allocates a new
  OpenGL texture every call at 60fps. Use `arcade.Text` objects instead.

### SpriteList
- `SpriteList.update()` requires `delta_time` argument in 3.x
- While `gc.disable()` is active during gameplay, never construct an
  `arcade.SpriteList()` per frame containing sprites that already live in
  another SpriteList — creates an unbreakable reference cycle
- `use_spatial_hash=True` is ONLY for SpriteLists whose sprites never move.
  Spatial hashing on moving sprites causes hash rebuilds every frame —
  slower, not faster. Rules:
    - Terrain tiles (never move): ✅ spatial hash OK
    - Bullets, particles, enemies, player: ❌ no spatial hash
    - Power-ups (moving): ❌ no spatial hash

### ShapeElementList — critical performance rule
- ShapeElementList is for STATIC geometry ONLY
- It requires a full GPU buffer rebuild whenever any element changes,
  causing visible microstutter
- NEVER use ShapeElementList for any moving object
- NEVER use ShapeElementList for terrain chunks that get added/removed
  as the camera scrolls — use immediate-mode draw calls instead
- Use SpriteList for anything that moves, even procedural shapes
- ProceduralStarField in agf uses SpriteList + make_circle_texture(),
  NOT ShapeElementList — follow this pattern

### Sprites
- Sprite constructor: `arcade.Sprite(path, scale=1.0)`
- Use global config SPRITE_SCALE when constructing all sprites
- `remove_from_sprite_lists()` still works in 3.x
- `arcade.Sprite.textures` is a list — set current with `self.texture`

### Spritesheet loading
  arcade.load_spritesheet(file_path, sprite_width, sprite_height,
                          columns, count)
  Returns a list of Texture objects

### Text
- Never `arcade.draw_text()` in `on_draw()` — use `arcade.Text` objects
- arcade.Text constructor:
    arcade.Text(text, x, y, color, font_size, font_name=...,
                anchor_x="left", anchor_y="baseline",
                multiline=False, width=None)
- Call `.draw()` on the Text object inside `on_draw()`
- Update content: `text_obj.text = "new string"`
- Load fonts before creating any Text objects (do it at startup)

### Fonts
- Load TTF fonts once at startup via `arcade.load_font(resource_path(...))`
- Font name in `arcade.Text` is the font's internal name (shown in OS
  font preview), NOT the filename
- KenVector Future and KenVector Future Thin are the target fonts for all
  game UI — located in `assets/fonts/`
- NEVER use `bold=True` unless the TTF file actually contains a bold
  variant. On Linux, Pyglet falls back to the system font entirely instead
  of synthesising bold (Windows synthesises it; Linux does not). This
  causes the wrong font to render silently.
- KenVector Future has no bold variant — never pass `bold=True`
- `win32_gdi_font` pyglet option is Windows-only — always guard:
    if sys.platform == "win32":
        pyglet.options["win32_gdi_font"] = True
- This game DOES require `win32_gdi_font = True`: all UI text uses the
  thin TTF whose family name is `"KenVector Future2 Thin"`, and pyglet's
  default Windows backend (DirectWrite) cannot resolve a family name
  ending in a weight word ("Thin") — it falls back to the system font
  silently.  The GDI backend can.
- CRITICAL ORDERING: pyglet selects its font backend the first time
  `pyglet.font` is imported (which `arcade`, and therefore the first
  `agf` import, pulls in).  The `win32_gdi_font` option MUST be set
  before any `agf`/`arcade` import.  Both entry points (`main.py`,
  `src/base_attackers/__main__.py`) set the pyglet options block ABOVE
  `from agf.paths import set_project_root` for exactly this reason — do
  not move it back below the agf import.

### Sound
- Initialise audio backend before arcade.Window:
    pyglet.options["audio"] = ("xaudio2", "directsound", "openal", "silent")
- `arcade.play_sound()` creates a new pyglet Player every call — many
  simultaneous calls cause audio crackling
- Use `agf.sound_manager.SoundManager` to cap simultaneous playbacks per
  sound type (2-3 for explosions, 1 for most SFX)
- Deduplicate sounds fired in the same frame (e.g. if multiple enemies
  fire simultaneously, play the sound once per frame not once per enemy)
- Use `streaming=True` for music tracks; static loading for short SFX
- Convert SFX to 16-bit mono WAV for fastest decode path

### Input
- Key constants: `arcade.key.LEFT`, `arcade.key.SPACE` etc. — unchanged
- `on_key_press(key, modifiers)` and `on_key_release(key, modifiers)` — unchanged

### Camera (Arcade 3.x)
- Use `arcade.Camera2D` for both world and GUI cameras
- Call `camera.use()` to activate (or use ScrollingGameWindow helpers)
- World camera X must only ever increase — see the "Camera tracking
  (RunLevelView)" section above for the full deadzone + monotonic-floor
  + right-edge-stop pattern used in this game. Don't enforce monotonic
  X by hand on the camera property — use `_min_camera_left` so the
  invariant survives a frame where the deadzone math wants to scroll
  left.

### Window and View
- `self.window.show_view(view)` — unchanged
- `on_show_view()` replaces `on_show()`
- `on_hide_view()` replaces `on_hide()`

### General rule
- If in doubt about any Arcade 3.x API, ask before writing it rather than
  guessing from 2.x memory. Arcade 3.x docs: https://api.arcade.academy/

---

## Sprite animation
- Use sprite sheets via `arcade.load_spritesheet()`, not individual frames
- Animated sprites manage their own frame timing via delta_time
- Animation state tracked as string ("idle", "flying", "dying") on sprite
- Explosions are self-contained AnimatedSprite subclasses that call
  `remove_from_sprite_lists()` on final frame — no external tracking needed
- Add an "explosions" layer to Scene so they render above other sprites
- All game animations and sounds should continue for max 2 seconds after
  player death, including background, explosions, bullets

---

## Ship physics (Base Attackers specific)

`PlayerShip` (`src/base_attackers/ships/player_ship.py`) inherits both
`arcade.Sprite` (rendering) and `agf.ships.momentum.MomentumShipMixin`
(physics). Import the mixin from `agf.ships.momentum` — it's not
re-exported at the agf top level.

### Update flow
- `PlayerShip(momentum_cfg, ship_cfg: ShipSettings)` — the second
  argument carries fuel + HP + gravity in one bundle.  Build
  `momentum_cfg` from the same `ShipSettings` for consistency.
- `PlayerShip.update_ship(delta_time)` returns `(dx, dy)` — the position
  delta for this frame. **It does NOT mutate `center_x` / `center_y`.**
  `RunLevelView._update_ship` applies the delta only after clamping
  against window/world bounds and running terrain collision, so a
  contact frame never has the ship inside terrain.
- `RunLevelView._update_ship` short-circuits when
  `ship.is_docked or ship.fuel_empty` — the fuel-empty death spiral
  and the docked-on-tower state both bypass `update_ship` entirely,
  so the brief's `control_enabled` property is the gate for input
  AND weapons.  `control_enabled` is `not fuel_empty and not is_docked`.
- Set `input_x` / `input_y` to -1.0, 0.0, or +1.0 before calling
  `update_ship`. Friction is exponential per-second decay
  (`velocity *= friction ** delta_time`), so the same `friction` value
  feels identical across frame rates.

### Gravity
Optional constant downward acceleration, configured via
`[ship] gravity` (default 0). Applied in `PlayerShip.update_ship`
**before** the momentum step so friction damps it to a stable
terminal velocity; setting `gravity = 0` disables it entirely.

### Hitbox
The player texture is loaded with
`hit_box_algorithm=arcade.hitbox.algo_detailed` so collision tests
against the actual ship silhouette (17 vertices for `playerShip1.png`).
Use `algo_detailed` for any sprite where collision accuracy matters and
the sprite is large enough that bbox cost is irrelevant. Bullets and
similar small/fast sprites continue to use `algo_simple` (see
"Collision detection performance" below).

`PlayerShip.collides_with_terrain(terrain, at_x, at_y)` iterates the
texture-local hitbox vertices, translates them to `(at_x, at_y)`, and
calls `terrain.point_in_terrain` on each. Vertex sampling is sufficient
because the corridor profile is piecewise-constant per `chunk_width`
while detailed-algo vertices are ~1 px apart. Note: raw points assume
`angle = 0` and `scale = 1`; if either changes, use
`hit_box.get_adjusted_points()` instead.

### Ship boundaries (enforced in RunLevelView._update_ship)
- Left:   `cam_left + chunk_width`         — `velocity_x = 0` on contact
- Right:  `world_width - chunk_width`      — `velocity_x = 0` on contact
- Top:    `world_height - ship.height/2`   — `velocity_y = 0` on contact
- Bottom: `ship.height/2`                  — `velocity_y = 0` on contact

These supersede the brief's `cam_left + sw * _DEADZONE_LEFT` ship-left
clamp — the deadzone still drives the camera, but the ship is allowed
to drift to ~1 chunk_width of the window's left edge before stopping.

### Terrain contact = ship destruction
On collision, `RunLevelView._on_terrain_collision` sets `ship.hp = 0`
and calls `_destroy_ship()` — see the "Ship destruction sequence"
subsection of "Fuel & docking" below.  Lives bookkeeping arrives in
a later phase; today the destruction sequence always lands in
`GameState.GAME_OVER`.

---

## Fuel & docking (Base Attackers specific)

### Fuel state on PlayerShip
- `ship.fuel` / `ship.fuel_capacity` drive the gauge.
- `ship.drain_fuel(dt)` is a no-op while docked.
- `ship.add_fuel(amount)` clamps to capacity (canister overflow is a no-op).
- `ship.fuel_empty` (`fuel <= 0`) flips `control_enabled` to False —
  `RunLevelView` then bypasses `update_ship` and runs
  `_apply_fuel_gravity` instead.
- `fuel_gravity` is applied in `_apply_fuel_gravity` *without* going
  through `MomentumShipMixin.apply_momentum`, so friction doesn't damp
  the fall.  Normal-flight `gravity` (the Phase 2 field) is still
  applied inside `PlayerShip.update_ship`.

### Scratch overlays
- Three textures (`scratch1/2/3.png` in `assets/images/PNG/Parts/`)
  loaded lazily via `ship.load_scratch_textures()` after construction.
- One `arcade.Sprite` (`ship.scratch_sprite`) is owned by `PlayerShip`
  and lives in a dedicated `RunLevelView._scratch_list` drawn just
  above the ship sprite list.
- `ship.update_scratch_overlay()` re-evaluates the texture each frame
  by HP fraction:  `> 2/3` invisible, `> 1/3` → scratch1, else → scratch3.
  (No damage source today other than instant-kill terrain, so this
  doesn't visibly trigger until later phases.)

### FuelTower
`src/base_attackers/terrain_features/fuel_tower.py`.
**Construction safety pattern** — Arcade only knows sprite dimensions
after the texture loads, so the caller MUST do:

    tower = FuelTower(world_x=x, world_y=0.0,        # dummy y
                      surface="floor", cfg=cfg.fuel_tower, scale=1.0)
    floor_y = terrain.floor_y_at(x)
    tower.center_y = floor_y + tower.height / 2.0
    tower.dock_y   = tower.center_y + tower.height / 2.0 + 12.0

The constructor stores the dummy `world_y` and initialises `dock_y`
to the same value as placeholders; both are overwritten by the caller
once `tower.height` is available.  `_place_fuel_towers` follows this
exact ordering.

`fuel-tower.png` is 128 px tall.  Towers use `scale=1.0` — do NOT
pass `cfg.sprite_scale` (the ship/canister scale) to FuelTower; if
size tuning ever becomes necessary, add a dedicated `tower_scale`
field to `[fuel_tower]` rather than coupling it to the ship.

### Docking flow (RunLevelView)
- `_check_docking` runs each frame.  Early-outs in priority order:
  already-docked → `_handle_docked`; `ship.fuel_empty`; or
  `_dock_cooldown > 0` (post-undock liftoff window).
- Otherwise it picks the first non-depleted tower within
  `cfg.fuel_tower.snap_distance` of `tower.dock_y`, calls `_dock_to`.
- `_dock_to` snaps `ship.center_(x|y)` to `(tower.center_x, tower.dock_y)`,
  zeroes both velocities, sets `is_docked` and `dock_tower`.
- `_handle_docked` transfers fuel via `tower.update_transfer(ship, dt)`
  every frame; undocks on `_undock_requested` (SPACE),
  `tower.is_depleted`, or `not ship.is_alive`; ticks
  `tower.update_pressure(dt)` and fires `_on_dock_pressure_spawn` on
  each interval.
- SPACE undocks while docked.  Phase 4 will reuse SPACE for firing —
  the `is_docked` check in `on_key_press` is the gate.

### Undock liftoff (the re-snap fix)
After clearing the dock state, the ship is sitting at exactly
`dock_y` with zero velocity.  Without a kick, `_check_docking` on
the next frame finds the same tower well inside `snap_distance` and
instantly re-snaps.  Two belts-and-braces guard against that:
1. `_perform_undock` sets `velocity_y = ±_LIFTOFF_SPEED` away from
   the tower (`+` for floor, `−` for future ceiling towers, picked
   via `tower.surface`).
2. `_dock_cooldown` is armed to `_DOCK_COOLDOWN` seconds, during
   which `_check_docking` returns early.
All three undock paths (manual, depleted, dying) go through
`_perform_undock` so each gets the liftoff.

### `_on_dock_pressure_spawn`
Phase-4 hook fired on every `tower.update_pressure(dt)` tick (every
`spawn_pressure_interval` seconds while docked).  Today it logs an
INFO line — observable in stdout when the project's `logging`
root is at INFO — so the cadence is testable before enemies arrive.
**Do not remove the method** even if you don't add behaviour to it
yet; Phase 4 wires real enemy spawns into it.

### Fuel canisters
World-space `arcade.Sprite` objects (`bolt_gold.png`) placed at
hardcoded X positions in Phase 3, floating `floor_y_at(x) + 80` above
the visible floor.  Touched via
`arcade.check_for_collision_with_list(self._ship, self._canister_list)`;
pickup calls `ship.add_fuel(cfg.ship.fuel_canister_restore)` and
`canister.remove_from_sprite_lists()`.  Phase 5 will replace these
with the proper power-up spawner.

### Placement (towers, silos, turrets, lasers)
As of Phase 7 there are NO hardcoded position constants.  Tower / silo /
turret / laser positions come from `LevelGenerator` (see "Level
generation & flow"); canisters were absorbed into the power-up spawner
in Phase 5.  Do not re-add `_PHASE*_*_POSITIONS` lists.

### Ship destruction sequence
- `_destroy_ship()` spawns an `agf.sprites.explosion.ExplosionSprite`
  at the ship position (scale = `max(1.0, cfg.sprite_scale * 2.0)`),
  hides the ship + scratch sprite, clears any dock state, and sets
  `_death_timer = _DEATH_DURATION` (1.5 s).
- While `_death_timer > 0`, `on_update` ticks the timer and *only*
  the explosion list (`_explosion_list.update(dt)`) — every other
  ship/camera/fuel update is skipped so the player isn't still
  steering an invisible corpse.  On timer expiry, transition to
  `GameState.GAME_OVER`.
- Re-entry into `_destroy_ship` is idempotent (no-op if a timer is
  already running), so an instant-kill terrain hit during the
  fuel-empty death spiral doesn't double-spawn explosions.

### HUD bars and DOCKED indicator
- All bars draw with `arcade.draw_lrbt_rectangle_filled` in GUI-camera
  space — never sprites, never `ShapeElementList`.
- Bars are co-located with the FPS/X/HP/FUEL text rows inside the
  existing HUD mask band (top of screen), NOT at the bottom-left as
  the brief draws them: HP bar on the HP text row, FUEL bar on the
  FUEL text row, optional TOWER bar to the right of the FUEL bar
  while docked.
- Fuel bar foreground colour flips from cyan to red below
  `_FUEL_LOW_FRAC` (25%).
- "DOCKED" is an `arcade.Text` next to the FPS line, blinked at
  `_DOCK_BLINK_PERIOD` (0.4 s) while `ship.is_docked`.

---

## Terrain system (Base Attackers specific)
- Terrain is generated once at level start for the entire world width —
  not streamed on the fly
- The corridor profile (list of CorridorSlice) is the source of truth for
  both rendering and collision detection
- `point_in_terrain(world_x, world_y)` is an O(1) lookup — use it for
  all ship-vs-terrain collision checks
- Terrain chunks are added/removed from the active render set as the
  camera scrolls; the full profile is always in memory
- Tile renderer uses SpriteList with spatial_hash=True (tiles never move)
- Polygon renderer uses immediate-mode draw calls — NOT ShapeElementList
- **Each renderer overrides the surface lookups to match what it draws**,
  because the base-class `floor_y_at`/`ceiling_y_at` return the *step*
  value at the chunk's left edge:
    - **Tile renderer** overrides `floor_y_at` to return the *visible*
      tile top (`ceil(raw_floor_y / chunk_width) * chunk_width`). Its
      terrain is step-rendered per column, so the base (step)
      `ceiling_y_at` already matches the ceiling tiles' bottom — no
      ceiling override needed.
    - **Polygon renderer** overrides BOTH `floor_y_at` and `ceiling_y_at`
      to **linearly interpolate** between adjacent chunk samples (via
      `_bracket`). Its trapezoids draw sloped floor/ceiling edges, so a
      step lookup diverges from the drawn edge by up to
      `slope * chunk_width` — on steep higher-level terrain that's ~100px,
      enough that the ship explodes well below the *visible* ceiling.
      Interpolation makes `point_in_terrain` match the drawn slopes
      exactly. Do NOT revert this to the base-class step lookup.
- See docs/architecture-overview.md for full terrain design

---

## Power-up system (Base Attackers specific)
- Spawning is world-space.  `agf.powerups.WorldSpacePowerUpSpawner` is
  built in `RunLevelView._build_powerup_system()` once terrain exists
  and owned by the view — NOT by `BAPowerUpManager`.  agf's screen-space
  `PowerUpSpawner` is unused; `BAPowerUpManager.update_effects` ticks
  only `_active_effects` and never drives the inherited spawner.
- `BAPowerUpManager(cfg.powerups, fuel_canister_restore, w, h, scale)` —
  the second positional arg is `cfg.ship.fuel_canister_restore` since
  the canister value lives on `ShipSettings`, not `PowerUpSettings`.
- Effect category rules (enforced by agf `PowerUpManager._add_effect`):
    - One BehaviorEffect at a time (new replaces old)
    - One ConstraintEffect at a time
    - One OverlayEffect at a time
    - Multiple StatModifierEffects stack
    - InstantEffects applied immediately, never tracked
- `BAPowerUpManager.apply_effect(effect, ship, ctx)` is the public
  wrapper around agf's `_add_effect`.  Use it instead of touching the
  underscore method directly.
- Stat routing: `PlayerShip` mirrors `player_fire_cooldown` and
  `player_bullet_damage` (initialised from `cfg.combat`).  `_try_fire`
  and `_check_player_bullet_hits` read from the ship, NOT from
  `cfg.combat`.  `RapidFireEffect` and `BigGunEffect` mutate those
  attributes via `StatModifierEffect.apply()`; the existing read sites
  pick up the new value automatically.
- `PowerUpSprite` registry key is `effect_type` (NOT `type_name`).
  `WorldSpacePowerUpSpawner.collect()` returns the `effect_type` string;
  pass it straight to `manager.create_effect()`.
- Texture registration via `PowerUpSprite.register(effect_type, path)`
  must happen before any spawn.  `RunLevelView.__init__` does this for
  all six types from `_POWERUP_TEXTURES`.
- Multi-shot bullet spawn lives in `RunLevelView._fire_multi_shot`, not
  in `MultiShotEffect.get_bullets()` (which returns `[]`).  Keeps the
  PlayerBullet/SFX/cooldown coupling with the existing firing pipeline.
- Shield damage gate: `_damage_player` checks for an active
  `OverlayEffect` with `effect_type == "shield"`, calls
  `on_hit_absorbed()` on it, and force-removes via
  `manager.remove_effect(...)` when depleted.  Damage never reaches
  `ship.take_damage` while a shield is active.
- Spawner + manager cleanup happens in `_destroy_ship`:
  `spawner.clear()` + `manager.clear_all(ship, ctx)`.  Don't add a
  second cleanup path — the death sequence is the single funnel.
- Per-level weight table comes from
  `cfg.powerups.weight_table_for_level(level_num)`; empty dict ⇒ no
  spawning.  Level 1 is intentionally empty.  `_level_num` comes from the
  active `PlayerState.current_level` (falling back to `cfg.starting_level`).

---

## Enemies — Phase 6 additions (Base Attackers specific)

### PatrolShip
- `src/base_attackers/enemies/patrol_ship.py`.  A single `arcade.Sprite`
  (NOT composite); lives in `RunLevelView._patrol_list` + `_patrols`.
- Three behaviours selected at spawn and immutable for life:
  `BEHAVIOUR_STRAIGHT` / `BEHAVIOUR_INTERCEPT` / `BEHAVIOUR_KAMIKAZE`.
  `_pick_patrol_behaviour()` weights them by `_level_num` (more
  kamikazes at higher levels).
- `update_patrol(ship_x, ship_y, dt, terrain)` sets velocity by
  behaviour, applies reactive terrain avoidance, ticks the fire
  cooldown, steps position (mutates `center_x/center_y` directly), then
  rotates the sprite to face its travel heading.  The `terrain` arg is
  passed at update time (not `__init__`), so the class is still
  constructible without terrain.
- **Facing**: rotated every frame to point along velocity via
  `angle = _NATURAL_BEARING_DEG - degrees(atan2(vy, vx))` (clockwise-
  positive, same convention as `GunTurret`).  `_NATURAL_BEARING_DEG =
  270.0` because Kenney enemy art is nose-down at angle 0.  Flip this one
  constant by 180 if a swapped sprite points the opposite way.
- **Terrain avoidance** (`_avoid_terrain`): reactive only — samples
  floor/ceiling at the current X and a short lookahead in the travel
  direction; within `_AVOID_MARGIN` of a surface it overrides `_vy` to
  climb/dive, otherwise leaves the behaviour velocity alone (so the
  mission resumes automatically once clear).  NOT path-planning; a ship
  that still contacts terrain explodes.
- **Terrain contact**: `_update_patrol_ships` checks
  `terrain.point_in_terrain(center)` each frame and routes a hit through
  `_explode_patrol` (explosion + SFX, **no score** — distinct from
  `_on_patrol_destroyed`, the player-kill path that adds +200).
- **Firing** (`_fire_patrol_bullet`): non-kamikaze only, gated to
  on-screen, on `patrol_fire_cooldown`.  Straight ships fire forward
  (left, angle π); intercept ships aim at the player's current position.
  Bullets go into the shared `_enemy_bullet_list`.  `ship.try_fire()`
  consumes the cooldown; `ship.fires` is False for kamikazes.
- **Spawning**: autonomous `patrol_spawn_interval` timer in `on_update`
  (`_patrol_spawn_timer`, seeded short) calls `_spawn_patrol_ship()`;
  dock-pressure spawns an intercept patrol on top of that.  The
  power-up `spawn_interval_*` keys are unrelated to enemy spawning.
- Culled in `_update_patrol_ships` when off the left/right/top/bottom
  world edges by `bullet_cull_margin`.  Kamikazes never exit left —
  they only die on player contact, player bullets, terrain, or drifting
  off top/bottom.
- Sprite map: straight=`enemyBlack2.png`, intercept=`enemyBlue3.png`,
  kamikaze=`enemyRed1.png`.

### LaserTurret
- `src/base_attackers/enemies/laser_turret.py`.  Composite like
  `GunTurret` — two SpriteLists (`_laser_base_list`,
  `_laser_barrel_list`).  `position_on_terrain()` MUST be called after
  construction (same two-step pattern as `GunTurret`/`FuelTower`).
- Parts: base `turretBase_big.png`, barrel `gun09.png`.
- State machine `idle → telegraph → firing → cooldown`.  `update()`
  returns the current state name.  Barrel tracks the player at
  `turret_rotation_speed * 0.5` (slower than a gun turret).
- The beam is drawn with `arcade.draw_line()` in world-camera space —
  NOT a sprite, NOT `ShapeElementList`.  Acceptable because it lasts
  < 0.7s total; no per-frame GPU buffer allocation of consequence.
- `_damage_dealt` flag prevents multiple damage applications during the
  FIRING window; reset on each telegraph→firing transition.  Damage is
  applied once, on the first FIRING frame, via `_ship_in_laser_beam`
  (point-to-segment distance) → `_damage_player` (shield-aware).
- Laser colours are `list[int]` RGBA in `[combat]`
  (`laser_beam_color`, `laser_telegraph_color`), parsed as lists into
  `CombatSettings` with `field(default_factory=...)` and converted to
  `tuple(...)` only at draw time in `_draw_laser_beams()`.

### Dock pressure
- `_on_dock_pressure_spawn()` now spawns a single intercept
  `PatrolShip` (replacing the Phase 4 enemy-bullet wave).  Phase 9 may
  tune behaviour weighting.

### Ceiling variants
- Ceiling-mounted silo/gun-turret/laser-turret require
  `ceiling_present = true` in the active level config; placement code
  silently skips any position whose `ceiling_y_at()` returns `None`.
  `[level_2]` enables the ceiling for Phase 6 playtesting.

### On-screen firing gate
- `RunLevelView._is_on_screen(world_x)` (within the camera's horizontal
  band) gates *activation*: silos check proximity, gun turrets
  rotate/fire, laser turrets telegraph/fire, and patrols fire only while
  on screen — the player never takes shots from enemies they can't see.
  `_draw_laser_beams` is gated too, so a turret frozen mid-telegraph as
  it scrolls off-screen can't render a stray beam into view.  In-flight
  projectiles move and cull independently of this gate.

### Score values
- silo = 100, gun turret = 150, patrol = 200, laser turret = 250.

---

## Level generation & flow — Phase 7 additions (Base Attackers specific)

### LevelGenerator
- `src/base_attackers/levels/level_generator.py`.  Pure Python (no
  arcade) — unit-testable without a display.  Module fns `difficulty`,
  `lerp`, `derive_seed`; dataclasses `TowerPlacement`/`SiloPlacement`/
  `TurretPlacement`/`LaserPlacement`/`LevelLayout`.
- `LevelGenerator(cfg).generate(level_num, world_width, ceiling_present,
  run_seed)` returns a `LevelLayout` of `(x, surface)` placements within
  `[entry_clear_x, boss_zone_x]`.  Density/spacing/ceiling-fraction/
  unlock-level all come from `cfg.level_gen` (`[level_gen]` TOML) and
  lerp along the difficulty curve.  Towers are placed first; enemies
  clear both each other and towers (`min_spacing`).

### Seed model (procedural but stable on respawn)
- `context["run_seed"]` is set ONCE per new game in
  `GameStateManager._handle_game_init`: `cfg.level_gen.run_seed` if
  non-zero (reproducible debugging), else a fresh random int.  It is NOT
  re-rolled on respawn or level transition, so it persists for the whole
  game.
- Each level's seed = `derive_seed(run_seed, level_num)`, used for BOTH
  terrain (`_build_terrain` seed override) and `LevelGenerator`.  Same
  run_seed + level_num ⇒ identical map, so dying and respawning rebuilds
  the exact same level; a new game (new run_seed) differs.
- A level's explicit non-zero `terrain_seed` in `[level_N]` always wins
  for that level's terrain shape (per-level pin), independent of run_seed.
- `cfg.level_settings_for(n)` returns explicit `[level_N]` settings if
  present, else procedural `LevelSettings` from the difficulty curve
  (ceiling at level ≥ 3, renderer alternates tile/polygon). Infinite
  levels need no TOML entry.

### RunLevelView placement & flow
- `on_show_view` builds terrain with the derived seed, calls
  `LevelGenerator.generate`, stores `_boss_zone_x`, then
  `_place_from_layout(layout)` (iterates the four lists into per-item
  helpers `_place_tower/_place_silo/_place_turret/_place_laser` — the
  Phase 8 boss reuses this pattern).
- Boss zone: `_boss_triggered` single-fires when `ship.center_x >=
  _boss_zone_x` → `_on_boss_zone_reached()` (Phase 7 placeholder →
  level complete; Phase 8 replaces the body).
- `_trigger_level_complete()` is the ONLY path to
  `GameState.LEVEL_COMPLETE` (used by the boss hook and the Shift+E
  debug shortcut).  It writes score to PlayerState then transitions; the
  `current_level` increment lives in `LevelCompleteView._on_complete` —
  do NOT increment in RunLevelView.

### Lives, death, score
- Death routes to `GameState.PLAYER_KILLED` (not GAME_OVER).
  `PlayerKilledView` owns the lives decrement and the GAME_OVER-vs-
  respawn branch; RunLevelView never touches `lives`.
- Score is the player's running total: `_score` is seeded from
  `PlayerState.score` in `__init__` and written back via
  `_sync_score_to_player()` in `_destroy_ship` and
  `_trigger_level_complete`.  HUD shows `LIVES` (from PlayerState) under
  `SCORE`.

### Music
- `_start_level_music()` (called from `on_show_view`) plays
  `agf.music.track_key_for_level(level_num)` — agf cycles its 6 bundled
  tracks; `music.play` no-ops if already playing and stops the menu
  track.  Pause/resume handled by the existing `P` handler.

---

## Boss — Phase 8 additions (Base Attackers specific)

### BaseBoss
- `src/base_attackers/bosses/boss.py`.  Composite (like `GunTurret`/
  `LaserTurret`) — NOT an `arcade.Sprite`.  Owns `body` (`arcade.Sprite`,
  scale = `sprite_scale * boss_scale_factor`) and `hardpoints`
  (`list[GunTurret]`).  HP = `boss_hp_base + (level-1)*boss_hp_per_level`
  (level 1 = 30, level 5 = 70).  Stationary — no movement.
- **Two-step placement**: construct, then `boss.place(center_y)` once
  `body.height` is known; `place` also calls `_attach_hardpoints()` so
  hardpoint offsets are relative to the final body centre.  Hardpoints
  float (positions set directly, NOT `position_on_terrain`).  Offset
  multipliers `hw*0.4`/`hh*0.5` are art-tunable.
- `_BossCombatSettings` shim wraps `CombatSettings` and overrides only
  `turret_fire_cooldown` → `boss_fire_cooldown`, so hardpoint
  `GunTurret`s reuse the stock class on the boss cadence.
- `BaseBoss.update()` ticks live hardpoints and returns the `BossBullet`s
  fired this frame (built from `hp._aim_angle`); the body never moves.

### RunLevelView wiring
- **Dedicated boss SpriteLists** — `_boss_body_list`,
  `_boss_hp_base_list`, `_boss_hp_barrel_list` — NOT the shared
  `_turret_*_list`.  Hardpoints are updated/fired by the boss (not
  `_update_turrets`), and player-bullet collision is a dedicated pass in
  `_check_player_bullet_hits` (hardpoint bases via
  `next(h for h in boss.hardpoints …)`, then the body).  The brief's
  "reuse `_turret_base_list` for free" does NOT work — the turret lookup
  is against `self._turrets`, which boss hardpoints are intentionally not
  in.  Do not add them there.
- `BossBullet` subclasses `EnemyBullet` (uses `boss_shot1.png`) and goes
  into `_enemy_bullet_list`, so existing move/cull/expiry and
  player-damage all handle it for free.
- `_on_boss_zone_reached` → `_spawn_boss` (boss at `world_width*0.92`).
  `_update_boss` runs in `on_update` after the laser turrets; while
  `_boss_death_timer > 0` the death sequence owns the frame (early
  return).  `_finish_boss_death` is the ONLY boss path to
  `_trigger_level_complete` (+`level_num*500` score).
- Hardpoint kill = `_on_hardpoint_destroyed` (explosion, +150, body
  survives).  Body kill = `_start_boss_death` (hide sprites, scatter
  explosions over `boss_death_duration`).  Ship contact with the body
  damages the player (`_check_enemy_hits`, shield-aware).
- Patrol auto-spawns are suppressed while `self._boss is not None`; dock
  pressure spawns are not.

---

## HUD & radar — Phase 9 additions (Base Attackers specific)

All HUD/radar rendering lives in `RunLevelView` (`views/run_level.py`),
drawn in GUI-camera space.  The separate `src/base_attackers/ui/hud.py`
`HUD` class is unused/orphaned — do NOT wire it in; extend the inline
methods instead.

### HUD (cache-on-change)
- `_build_hud` creates every `arcade.Text` once.  `_refresh_hud` only
  rewrites `.text`/visibility when the value changed, gated by sentinels
  on the view (`_last_score`, `_last_hp`, `_last_fuel`, `_last_lives`,
  `_last_level`, `_last_effects_str`).  Never set `.text` unconditionally
  per frame.
- Text rows use module constants `_ROW1_Y`/`_ROW2_Y`/`_ROW3_Y`/`_ROW4_Y`
  (screen-Y offsets from `sh`).  Row 1: SCORE (`SCORE  000000`,
  6-digit zero-pad) left, `LEVEL  N` centred, lives icons right, DOCKED.
  Row 2: centred boss bar + left-aligned effects line.  Rows 3/4: HP/FUEL
  text + bars (`_HP_BAR_X` … `_TOWER_BAR_X`).  Bar X offsets are tunable.
- **Lives are icon sprites**, not text: `_hud_lives_list` (SpriteList) of
  up to `_LIVES_ICON_MAX` `playerShip1.png` sprites at
  `_LIVES_ICON_SCALE` (0.25), anchored to the right edge.  `_refresh_hud`
  toggles `icon.visible = i < (lives - 1)` — one fewer icon than the live
  count (the active ship is the one you fly).
- **Effects line** (`_hud_effects`) is built by `_build_effects_str()`,
  which iterates `self._powerup_manager.get_active_effects()` — the public
  getter; there is NO `active_effects` property.  Labels come from
  `display_label` (only `StatModifierEffect` exposes it; behaviour/overlay
  effects fall back to a title-cased `effect_type`), durations from
  `remaining_duration` (a property on every effect category).
- **Debug HUD is gated**: FPS / world-X / hints draw only when
  `cfg.debug`; GOD MODE only when `cfg.god_mode`.  Production config has
  both false, so the band stays clean.

### Radar minimap (`_draw_radar`)
- Defender-style strip at the bottom of the screen, drawn from
  `_draw_hud()` in GUI-camera space with immediate-mode calls only — no
  sprites, no ShapeElementList.  Constants are `_RADAR_*` at module level.
- Maps world X linearly to radar pixel X via the inner `to_rx(world_x) =
  rx + (world_x / world_width) * rw`.  World Y is ignored — everything
  sits on one horizontal strip.
- A white camera-viewport tint (`world_camera.position.x ± sw/2`) shows
  the visible fraction of the level.  Dots: towers cyan, all stationary
  enemies + patrols red (guard `is_alive`; turrets/lasers via
  `.base.center_x`), boss orange (2.5×), player yellow (1.5×, drawn last).
  `_RADAR_DOT_R` is tunable (~0.218 px/world-unit on the 1398px strip).

### Sound
- `extraLife.wav` plays on `_trigger_level_complete()` as positive
  feedback (`_snd_extra_life` + a `max_simultaneous=1` SoundManager).
- `laserSmall_001.wav` is present in `assets/sounds/` but intentionally
  unused — reserved for a future alternate-fire sound (e.g. Big Gun).

### Production config
- Release defaults in `game_config.toml`: `starting_level = 1`,
  `num_lives = 3`, `debug = false`, `god_mode = false`.  Window stays
  1422×800.

### Fonts
- All HUD text uses `FONT_THIN` → `"KenVector Future2 Thin"` (the TTF's
  internal name, NOT the filename).  Both `kenvector_future2.ttf` and
  `kenvector_future_thin2.ttf` are loaded at startup in `game._load_fonts`
  (do not remove the agf-module FONT rebind loop).  NEVER pass
  `bold=True` — neither font has a bold variant; Linux pyglet silently
  falls back to a system font.
- NOTE: do NOT run `black` against `game_config.toml` — black is for
  Python only; passing the TOML collapses its aligned inline comments.

---

## Collision detection performance
- Terrain collision: O(1) via corridor profile — check every frame, fine
- Player bullets vs enemies: check every frame (must feel responsive)
- Enemy bullets vs player: check every 2 frames (% 2 == 0)
- Enemy contact vs player: check every 3 frames
- Cull off-screen bullets immediately in the same frame they exit
- Projectiles also cull on terrain contact (`point_in_terrain`) each
  frame they move — player bullets, enemy bullets, and missiles alike.
  A missile that hits terrain re-arms its owning silo, same as the
  off-world path.
- Enemy bullets additionally expire after `cfg.combat.enemy_bullet_lifetime`
  (default 3 s) via `EnemyBullet.expired`, so a stray shot that never hits
  terrain or leaves the world still disappears.  Lifetime is threaded in
  at construction (`GunTurret.fire_bullet`, `_fire_patrol_bullet`).
- Enemy firing is gated to on-screen enemies (`_is_on_screen`), so no
  bullets originate off-screen — see the "On-screen firing gate" note.
- Use `hit_box_algorithm=arcade.hitbox.algo_simple` for bullets —
  pixel-perfect hitboxes add cost with no gameplay benefit for small
  fast projectiles
- Use `arcade.hitbox.algo_detailed` for the player ship and any sprite
  where wing/nose contact should count, not just centre-pixel overlap.
  `PlayerShip` loads its texture with this algorithm — see "Ship
  physics" above.

---

## Configuration (Base Attackers specific)

`GameConfig.load()` parses `game_config.toml` into a `GameConfig`
dataclass with four nested settings groups and a per-level map:

- `cfg.ship` — `ShipSettings`. Fields: `accel`, `friction` (per-second
  decay multiplier), `max_speed_x`, `max_speed_y`, `hp`, `hit_radius`,
  `gravity`, plus the Phase 3 fuel fields `fuel_capacity`,
  `fuel_drain_rate`, `fuel_gravity`, `fuel_canister_restore`.
  Maps to `[ship]` in the TOML.
- `cfg.fuel_tower` — `FuelTowerSettings`. Fields: `transfer_rate`,
  `snap_distance`, `tower_capacity`, `spawn_pressure_interval`.
  Maps to `[fuel_tower]`.
- `cfg.terrain` — `TerrainSettings`. Fields: `chunk_width`,
  `cull_buffer_chunks`. Maps to `[terrain]`.
- `cfg.levels` — `dict[int, LevelSettings]`. One entry per
  `[level_N]` section in the TOML (regex `^level_(\d+)$`). Each
  `LevelSettings` has `world_width`, `world_height`, terrain wave
  params, `ceiling_present`, `terrain_renderer` (`"tile"` or
  `"polygon"`), and `terrain_seed`.

### Renderer & seed per level
- `[level_N] terrain_renderer = "tile"` or `"polygon"` picks the
  visual style for that level — set per level for variety (natural
  rock vs artificial structure).
- `[level_N] terrain_seed = 0` means "pick a random seed at run start"
  — the level shape changes each playthrough. Any non-zero value is
  passed verbatim to `generate_corridor_profile`, producing a
  reproducible profile across runs (useful for bug repro and for
  hand-tuned levels).

Anything that needs config should pull from `GameConfig.load()` (or
`manager.context.get("config")` when the state machine populated it).
Don't re-parse TOML in views — `TerrainTestView` was refactored in
Phase 2 to read `cfg.terrain` + `cfg.levels[1]` exactly like
`RunLevelView` does.

---

## State machine
- Follows Space Attackers GameStateManager pattern exactly
- Import views inside `_enter_state()` — not at module level — so that
  tests can import GameState without triggering arcade init
- No rendering in state transition logic — only view swaps and bookkeeping
- Levels return GameEvent values from update() — never call state machine
  directly from level or enemy classes

---

## Assets
- All assets in `assets/` — agf contains no assets
- All asset paths via `resource_path()` for PyInstaller compatibility
- Music: one track per level, `streaming=True`
- SFX: 16-bit mono WAV preferred
- Fonts: KenVector Future / KenVector Future Thin in `assets/fonts/`
- Explosion + bullet sprites copied from Space Attackers assets (CC0)
- Terrain tile sprites: chosen after Phase 1 renderer decision
- Phase 3 fixtures:
    - `assets/images/PNG/Parts/fuel-tower.png` (128 px tall)
    - `assets/images/PNG/Parts/scratch1.png` / `scratch2.png` / `scratch3.png`
    - `assets/images/PNG/Power-ups/bolt_gold.png` (fuel canister)

---

## Build
- `python build.py` → produces `dist/base_attackers.exe`
- PyInstaller bundles agf automatically via site-packages
- `.spec` file is source code — commit it, do NOT gitignore it
- `build/` and `dist/` ARE gitignored (build artifacts)
- agf package needs no special handling in spec — bundled automatically

## Feature brief index
- Phase 1 — Terrain testbed:      docs/features/phase-1-terrain-testbed.md (done)
- Phase 2 — Ship in the world:    docs/features/phase-2-ship.md (done)
- Phase 3 — Fuel system:          docs/features/phase-3-fuel.md (done)
- Phase 4 — Weapons and enemies:  docs/features/phase-4-combat.md (TBD)
- Phase 5 — Power-ups:            docs/features/phase-5-powerups.md (TBD)
- Phase 6 — Enemy ships + lasers: docs/features/phase-6-enemies.md (TBD)
- Phase 7 — Level structure:      docs/features/phase-7-levels.md (done)
- Phase 8 — Boss encounter:       docs/features/phase-8-boss.md (done)
- Phase 9 — Polish + release:     docs/features/phase-9-polish.md (done)
