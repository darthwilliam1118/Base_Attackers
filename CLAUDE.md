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
Version: 1e89589 (pre-v0.3.0 — will be tagged once Base Attackers agf
additions are stable). Bump the SHA in `pyproject.toml` and
`pip install -e ".[dev]" --force-reinstall --no-deps "arcade-game-framework @ git+…@<sha>"`
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

### Hardcoded placement (Phase 3 only)
Tower positions live in `_PHASE3_TOWER_POSITIONS` and canister
positions in `_PHASE3_CANISTER_POSITIONS` at the top of `run_level.py`.
Phase 7 moves towers into level config; Phase 5 moves canisters into
the power-up spawner.

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
- **Tile renderer overrides `floor_y_at`** to return the *visible* tile
  top (`ceil(raw_floor_y / chunk_width) * chunk_width`) rather than the
  raw corridor profile value. This keeps `point_in_terrain` aligned
  with what's actually drawn so the ship can't sink into a tile by up
  to `chunk_width - 1` px before dying. The polygon renderer uses the
  raw `floor_y` from the base class because its trapezoids reach
  exactly to that value. Ceiling tiles already bottom out at
  `ceiling_y` exactly, so `ceiling_y_at` doesn't need an override.
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
  spawning.  Level 1 is intentionally empty.  `_level_num` is hardcoded
  to 1 in `__init__` until Phase 7 wires it through state context.

---

## Collision detection performance
- Terrain collision: O(1) via corridor profile — check every frame, fine
- Player bullets vs enemies: check every frame (must feel responsive)
- Enemy bullets vs player: check every 2 frames (% 2 == 0)
- Enemy contact vs player: check every 3 frames
- Cull off-screen bullets immediately in the same frame they exit
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
- Phase 7 — Level structure:      docs/features/phase-7-levels.md (TBD)
- Phase 8 — Boss archetypes:      docs/features/phase-8-bosses.md (TBD)
- Phase 9 — Polish + release:     docs/features/phase-9-polish.md (TBD)
