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
Version: da37339 (pre-v0.3.0 — will be tagged once Base Attackers agf
additions are stable)
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
- World camera X must only ever increase — enforce with:
    self.world_camera.position = Vec2(
        max(self.world_camera.position.x, new_x),
        new_y
    )

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
- See docs/architecture-overview.md for full terrain design

---

## Power-up system
- Reuses agf power-up infrastructure (effect categories, manager, spawner)
- Power-ups exist in world space — they have world coordinates and scroll
  with the camera; cull when they exit the left edge of the camera
- Fuel canister is a new InstantEffect specific to Base Attackers —
  restores partial fuel on collection
- Effect category rules (enforced by PowerUpManager):
    - One BehaviorEffect at a time (new replaces old)
    - One ConstraintEffect at a time
    - One OverlayEffect at a time
    - Multiple StatModifierEffects stack
    - InstantEffects applied immediately, never tracked

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

---

## Build
- `python build.py` → produces `dist/base_attackers.exe`
- PyInstaller bundles agf automatically via site-packages
- `.spec` file is source code — commit it, do NOT gitignore it
- `build/` and `dist/` ARE gitignored (build artifacts)
- agf package needs no special handling in spec — bundled automatically

## Feature brief index
- Phase 1 — Terrain testbed:      docs/features/phase-1-terrain-testbed.md
- Phase 2 — Ship in the world:    docs/features/phase-2-ship.md (TBD)
- Phase 3 — Fuel system:          docs/features/phase-3-fuel.md (TBD)
- Phase 4 — Weapons and enemies:  docs/features/phase-4-combat.md (TBD)
- Phase 5 — Power-ups:            docs/features/phase-5-powerups.md (TBD)
- Phase 6 — Enemy ships + lasers: docs/features/phase-6-enemies.md (TBD)
- Phase 7 — Level structure:      docs/features/phase-7-levels.md (TBD)
- Phase 8 — Boss archetypes:      docs/features/phase-8-bosses.md (TBD)
- Phase 9 — Polish + release:     docs/features/phase-9-polish.md (TBD)
