# Feature Brief — Phase 9: Polish, Radar Minimap & Release Prep

**Game:** Base Attackers
**Phase:** 9 of 9
**Depends on:** Phase 8 complete — full game loop working end to end
**Output:** Production-quality HUD modelled on Space Attackers style,
Defender-style radar minimap, music properly mapped to the 7 available
tracks, agf tagged at v0.3.0, PyInstaller release build, CI passing
**agf changes required:** Minimal — tag v0.3.0 only; no new agf code

---

## Goals

1. HUD overhaul — replace the debug-style text labels with a polished
   Space Attackers-style HUD using the `HUD` class pattern; icon sprites
   for lives; score formatted `SCORE: 000000`; level indicator; active
   power-up effects line; all using `FONT_THIN` (`"KenVector Future2 Thin"`)
2. Radar minimap — Defender-style horizontal strip showing the full level
   in miniature, synced to camera position, player dot, enemy dots,
   towers, boss indicator
3. Music mapping — wire all 7 available tracks to levels correctly via
   `agf.music._TRACKS` / `track_key_for_level`; confirm all files load
4. Font loading audit — verify `_load_fonts()` in `game.py` works on
   both Windows and Ubuntu; document the font name / filename split
5. Remove remaining debug HUD items from production build (FPS, world X,
   debug hints) — gate them behind `cfg.debug` only
6. agf v0.3.0 tag — tag the agf repo once all additions are stable
7. PyInstaller build — verify `python build.py` produces a working exe
   on Windows; confirm all assets bundle correctly
8. Final playtest — complete 3-level run, boss fight, game over, high
   score entry, main menu return

---

## Step 0 — Before Writing Any Code

Read these files in full:

```
src/base_attackers/views/run_level.py
  — _build_hud(), _refresh_hud(), _draw_hud(), _draw_boss_health_bar()
  — Current HUD layout: text labels at sh-20/40/60/80, bars at same rows
  — _draw_bar() helper already exists — reuse it
  — on_draw() structure — radar draws in gui_camera context after _draw_hud()

src/base_attackers/game.py
  — _load_fonts() — loads kenvector_future2.ttf and kenvector_future_thin2.ttf
  — GAME_FONT = "KenVector Future2 Thin" — this is the font internal name
  — Module-level rebind of agf.ui.text_utils.FONT_MAIN / FONT_THIN
  — _apply_window_size() / _refresh_cameras() — already handles 1422×800

Space_Attackers/src/ui/hud.py
  — HUD class with SCORE/LEVEL/LIVES layout, icon SpriteLists, effects line
  — All text uses FONT_MAIN (rebound to GAME_FONT at startup in game.py)
  — Lives rendered as icon sprites (SpriteList), not just text
  — Effects line shows active power-up name + remaining duration
  — Only write .text when value changes (cache-on-change pattern)

agf/src/agf/music.py
  — 7 tracks: ending, level_1..level_6
  — track_key_for_level(n) cycles through 6 level tracks
  — assets/music/ confirmed files:
      awake10_megaWall.mp3            → level_4
      Cyberpunk Moonlight Sonata.mp3  → level_5
      fight.ogg                       → level_6
      Juhani Junkala ... Ending.ogg   → ending
      Juhani Junkala ... Level 1.ogg  → level_1
      Juhani Junkala ... Level 2.ogg  → level_2
      Juhani Junkala ... Level 3.ogg  → level_3
  — NOTE: agf._TRACKS references "awake10_megawall.mp3" (lowercase w)
    but the actual file is "awake10_megaWall.mp3" (capital W).
    Fix the filename casing in agf music.py to match the actual file.

agf/src/agf/high_scores.py — HighScoreTable API (already wired in agf views)
agf/src/agf/ui/text_utils.py — FONT_MAIN / FONT_THIN constants, centered_text()
assets/images/PNG/ — ship sprites for life icons
assets/sounds/ — confirm laserSmall_001.wav and extraLife.wav are present
```

**Font loading — critical cross-platform notes:**
- `arcade.load_font(path)` loads the TTF file from disk
- The string passed to `arcade.Text(font_name=...)` is the font's
  **internal name** as registered in the TTF, NOT the filename
- `kenvector_future2.ttf` internal name: `"KenVector Future2"`
- `kenvector_future_thin2.ttf` internal name: `"KenVector Future2 Thin"`
- The "Thin" variant is a separate TTF file — NOT `bold=False` on the
  regular weight. Pyglet on Linux does NOT synthesise font variants;
  it falls back to the system font silently if the requested name is
  not loaded. Always load both TTF files and always use the exact
  internal name strings above.
- `game.py._load_fonts()` already does this correctly. Do NOT change it.
- The module-level rebind (`_tu.FONT_MAIN = GAME_FONT` etc.) is
  necessary because agf views import `FONT_MAIN` at module import time
  and cache the name locally. The rebind loop in `_load_fonts()` patches
  those cached references. Do NOT remove this rebind loop.
- `win32_gdi_font` is Windows-only — the existing `game.py` does NOT
  set it, which is correct (it is not needed for these fonts).

---

## Part A — Music Track Fix

### A1. Fix filename casing in `agf/src/agf/music.py`

The track `"level_4"` references `"awake10_megawall.mp3"` but the
actual file is `"awake10_megaWall.mp3"`. On Windows the filesystem is
case-insensitive so this works; on Linux/Ubuntu it fails silently.

```python
# Fix in agf/src/agf/music.py _TRACKS dict:
"level_4": "assets/music/awake10_megaWall.mp3",   # capital W
```

This is the only agf code change in Phase 9. Commit it separately:

```bash
cd path/to/arcade-game-framework
git add -A
git commit -m "fix: correct filename casing for awake10_megaWall.mp3 in music tracks"
git push
```

### A2. Update Base Attackers agf SHA pin

After the agf fix commit, update the SHA in `Base_Attackers/pyproject.toml`
and `pip install -e ".[dev]" --force-reinstall --no-deps`.

### A3. Tag agf v0.3.0

Once the casing fix is the last agf change:

```bash
cd path/to/arcade-game-framework
git tag -a v0.3.0 -m "v0.3.0 — Base Attackers support complete"
git push origin v0.3.0
```

Then pin Base Attackers to the tag in `pyproject.toml`:
```toml
"arcade-game-framework @ git+https://github.com/darthwilliam1118/arcade-game-framework.git@v0.3.0"
```

---

## Part B — HUD Overhaul

### B1. Design

The new HUD follows Space Attackers `HUD` class philosophy:
- All `arcade.Text` objects created once in `_build_hud()`
- `.text` / `.color` updated only when values change (cache sentinels)
- Font: `FONT_THIN` throughout (already imported from `agf.ui.text_utils`)
- Lives rendered as **icon sprites** in a `SpriteList` — use
  `playerShip1.png` at small scale (0.3) as the life icon
- Score formatted `SCORE  000000` (6 digits, zero-padded)
- Level indicator centred: `LEVEL  N`
- Active power-up effects line below the main row

**Layout (all in GUI camera space, y measured from bottom):**

```
┌─────────────────────────────────────────────────────────────────┐
│ [black mask band — _HUD_BAND_HEIGHT px]                        │
│ SCORE  000000   HP ███░░░  FUEL ████░  │  LEVEL  1  │  ♦ ♦ ♦  │  ← row 1: sh-24
│ [BOSS ████████████████████████████]  (centred, only when boss)  │  ← row 2: sh-44
│ [RAPID FIRE 6.2s]  (centred, only when effect active)          │  ← row 3: sh-64
│ [DOCKED ●]  (blinking, only when docked)                       │  ← row 4: inline
│ [DEBUG row — only cfg.debug=true]                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                    [RADAR STRIP]                                │  ← bottom of screen
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### B2. Update `_build_hud()`

Replace the current `_build_hud()` entirely:

```python
def _build_hud(self) -> None:
    sw = self.window.width
    sh = self.window.height
    fn = FONT_THIN   # "KenVector Future2 Thin" — loaded at game startup

    # Row 1 — main HUD band (sh - 24)
    self._hud_score = arcade.Text(
        "SCORE  000000", 12, sh - 24,
        arcade.color.WHITE, 14, font_name=fn, anchor_y="center",
    )
    self._hud_hp_label = arcade.Text(
        "HP", 200, sh - 24,
        arcade.color.WHITE, 14, font_name=fn, anchor_y="center",
    )
    self._hud_level = arcade.Text(
        "LEVEL  1", sw / 2, sh - 24,
        arcade.color.WHITE, 14, font_name=fn,
        anchor_x="center", anchor_y="center",
    )
    # Lives icons — SpriteList of up to 6 ship sprites
    self._hud_lives_list = arcade.SpriteList()
    self._hud_lives_icons: list[arcade.Sprite] = []
    icon_tex = arcade.load_texture(resource_path("assets/images/PNG/playerShip1.png"))
    for i in range(6):
        icon = arcade.Sprite(icon_tex, scale=0.25)
        icon.center_y = sh - 24
        icon.center_x = sw - 20 - i * (icon.width + 4)
        icon.visible = False
        self._hud_lives_list.append(icon)
        self._hud_lives_icons.append(icon)

    # Row 2 — boss health bar label (built in existing _draw_boss_health_bar)
    self._hud_boss_label = arcade.Text(
        "BOSS", sw * 0.25 - 50.0, sh - 44.0,
        arcade.color.RED, 12, font_name=fn, anchor_y="bottom",
    )

    # Row 3 — active effects (centred, empty when none active)
    self._hud_effects = arcade.Text(
        "", sw / 2, sh - 64,
        (180, 220, 255, 255), 12, font_name=fn,
        anchor_x="center", anchor_y="center",
    )

    # DOCKED indicator — same row as score, placed right of HP bar
    self._hud_docked = arcade.Text(
        "DOCKED", 400, sh - 24,
        arcade.color.YELLOW, 14, font_name=fn, anchor_y="center",
    )

    # Power-up flash — centred, large, temporary
    self._hud_powerup_flash = arcade.Text(
        "", sw / 2, sh / 2 + 60,
        arcade.color.YELLOW, 22, font_name=fn,
        anchor_x="center", anchor_y="center",
    )

    # Debug / god mode (only drawn when cfg.debug / cfg.god_mode)
    self._hud_fps = arcade.Text(
        "FPS: --", 12, sh - 44,
        (140, 140, 140, 255), 11, font_name=fn, anchor_y="center",
    )
    self._hud_world_x = arcade.Text(
        "X: 0", 100, sh - 44,
        (140, 140, 140, 255), 11, font_name=fn, anchor_y="center",
    )
    self._hud_god_mode = arcade.Text(
        "GOD MODE", sw / 2, sh - 44,
        arcade.color.YELLOW, 12, font_name=fn,
        anchor_x="center", anchor_y="center",
    )
    self._hud_debug_hints = arcade.Text(
        "Shift+G god  Shift+P p-up  Shift+E lvl+  Shift+K kill  Shift+F fuel",
        sw / 2, sh - 44,
        (140, 140, 140, 200), 10, font_name=fn,
        anchor_x="center", anchor_y="center",
    )

    # Pause overlay
    overlay = arcade.SpriteSolidColor(
        sw, sh, center_x=sw/2, center_y=sh/2, color=(0, 0, 0, 120)
    )
    self._pause_overlay_list.clear()
    self._pause_overlay_list.append(overlay)
    self._paused_text = arcade.Text(
        "PAUSED", sw / 2, sh / 2,
        arcade.color.WHITE, 48, font_name=fn,
        anchor_x="center", anchor_y="center",
    )
```

### B3. Update `_refresh_hud()`

Use cache-on-change pattern (only write `.text` when value changes):

```python
# Sentinel fields added to __init__():
#   self._last_score: int = -1
#   self._last_hp: int = -1
#   self._last_fuel: float = -1.0
#   self._last_lives: int = -1
#   self._last_level: int = -1
#   self._last_effects_str: str = ""

def _refresh_hud(self) -> None:
    if self._hud_score is None:
        return

    # Score
    if self._score != self._last_score:
        self._hud_score.text = f"SCORE  {self._score:06d}"
        self._last_score = self._score

    # Level
    if self._level_num != self._last_level:
        self._hud_level.text = f"LEVEL  {self._level_num}"
        self._last_level = self._level_num

    # HP bar (draw call only — no text change needed)

    # Fuel bar (draw call only)

    # Lives icons
    players = self._manager.context.get("players") or []
    idx = self._manager.context.get("active_player_index", 0)
    lives = players[idx].lives if players and 0 <= idx < len(players) else 0
    if lives != self._last_lives:
        self._last_lives = lives
        for i, icon in enumerate(self._hud_lives_icons):
            icon.visible = i < (lives - 1)  # one fewer than lives count

    # Active effects line
    effects_str = self._build_effects_str()
    if effects_str != self._last_effects_str:
        self._hud_effects.text = effects_str
        self._last_effects_str = effects_str

    # Debug
    if self._cfg.debug:
        self._hud_fps.text = f"FPS: {arcade.get_fps():.0f}"
        self._hud_world_x.text = f"X: {self._ship.center_x:.0f}"

    # Power-up flash text
    if self._hud_powerup_flash is not None:
        self._hud_powerup_flash.text = self._powerup_flash_label

def _build_effects_str(self) -> str:
    """Summarise active timed power-up effects for the HUD effects line."""
    if self._powerup_manager is None:
        return ""
    parts = []
    for effect in self._powerup_manager.active_effects:
        label = getattr(effect, "label", effect.effect_type.replace("_", " ").upper())
        dur = getattr(effect, "remaining_duration", 0.0)
        if dur > 0.0:
            parts.append(f"[{label} {dur:.1f}s]")
        elif hasattr(effect, "label"):
            parts.append(f"[{label}]")
    return "  ".join(parts)
```

**Note:** `_powerup_manager.active_effects` — check whether agf's
`PowerUpManager` exposes this property. If not, read the agf source
and use whatever iteration mechanism is available (e.g. `_active_effects`
list). Do NOT guess — read the source first.

### B4. Update `_draw_hud()`

```python
def _draw_hud(self) -> None:
    # ... existing HUD mask band drawing unchanged ...

    # HP bar (sh - 24 row, right of "HP" label)
    hp_frac = self._ship.hp / self._ship.MAX_HP if self._ship.MAX_HP else 0.0
    self._draw_bar(240, 100, self.window.height - 30, hp_frac, _HP_COLOR)

    # FUEL bar (sh - 24 row, right of HP bar)
    fuel_frac = self._ship.fuel / self._ship.fuel_capacity if self._ship.fuel_capacity else 0.0
    fuel_color = _FUEL_COLOR_LOW if fuel_frac < _FUEL_LOW_FRAC else _FUEL_COLOR
    self._draw_bar(350, 160, self.window.height - 30, fuel_frac, fuel_color)

    # Tower bar (only while docked)
    if self._ship.is_docked and self._ship.dock_tower is not None:
        tower = self._ship.dock_tower
        t_frac = tower.fuel_remaining / tower.cfg.tower_capacity if tower.cfg.tower_capacity else 0.0
        self._draw_bar(520, 100, self.window.height - 30, t_frac, _TOWER_COLOR)

    # Text elements
    if self._hud_score:    self._hud_score.draw()
    if self._hud_hp_label: self._hud_hp_label.draw()
    if self._hud_level:    self._hud_level.draw()
    self._hud_lives_list.draw()
    if self._hud_effects and self._last_effects_str:
        self._hud_effects.draw()
    if self._ship.is_docked and self._dock_blink_visible and self._hud_docked:
        self._hud_docked.draw()
    if self._powerup_flash_label and self._hud_powerup_flash:
        self._hud_powerup_flash.draw()

    # Debug — only when cfg.debug is True
    if self._cfg.debug:
        if self._hud_fps:        self._hud_fps.draw()
        if self._hud_world_x:    self._hud_world_x.draw()
        if self._hud_debug_hints: self._hud_debug_hints.draw()
    if self._cfg.god_mode and self._hud_god_mode:
        self._hud_god_mode.draw()

    self._draw_boss_health_bar()
    self._draw_radar()   # Phase 9 addition — see Part C
```

---

## Part C — Radar Minimap

The radar is a Defender-style horizontal strip at the bottom of the
screen showing the entire level width in miniature. It is drawn entirely
in GUI camera space using immediate-mode draw calls — no sprites,
no ShapeElementList.

### C1. Radar layout constants

```python
# Add to run_level.py module level:
_RADAR_HEIGHT      = 28.0    # px height of the radar strip
_RADAR_MARGIN_X    = 12.0    # px from window left/right edges
_RADAR_MARGIN_BOT  = 6.0     # px from window bottom
_RADAR_BG_COLOR    = (20, 30, 20, 200)
_RADAR_BORDER_COLOR= (60, 100, 60, 255)
_RADAR_PLAYER_COLOR= (255, 255, 100, 255)   # bright yellow dot
_RADAR_ENEMY_COLOR = (255, 80,  80,  200)   # red dots
_RADAR_TOWER_COLOR = (80,  200, 255, 200)   # cyan dots
_RADAR_BOSS_COLOR  = (255, 100, 30,  255)   # orange dot
_RADAR_CAM_COLOR   = (255, 255, 255, 60)    # white tint for visible area
_RADAR_DOT_R       = 2.0     # radius of entity dots
```

### C2. `_draw_radar()` method

```python
def _draw_radar(self) -> None:
    """Defender-style radar strip at the bottom of the screen.

    Drawn entirely in gui_camera space with immediate-mode calls.
    The radar maps world_x → radar_x linearly; world_y is ignored
    (everything appears on a single horizontal strip).
    """
    if self._terrain_cfg is None:
        return

    sw   = float(self.window.width)
    sh   = float(self.window.height)
    ww   = self._terrain_cfg.world_width

    # Radar strip geometry (screen space).
    rx   = _RADAR_MARGIN_X
    ry   = _RADAR_MARGIN_BOT
    rw   = sw - 2 * _RADAR_MARGIN_X
    rh   = _RADAR_HEIGHT

    def to_rx(world_x: float) -> float:
        """Map a world X coordinate to a radar X pixel."""
        return rx + (world_x / ww) * rw

    # Background + border.
    arcade.draw_lrbt_rectangle_filled(rx, rx + rw, ry, ry + rh, _RADAR_BG_COLOR)
    arcade.draw_lrbt_rectangle_outline(rx, rx + rw, ry, ry + rh, _RADAR_BORDER_COLOR, 1)

    # Camera viewport tint — shows what fraction of the world is visible.
    cam_left  = self.window.world_camera.position.x - sw / 2.0
    cam_right = cam_left + sw
    vx0 = max(rx, to_rx(cam_left))
    vx1 = min(rx + rw, to_rx(cam_right))
    if vx1 > vx0:
        arcade.draw_lrbt_rectangle_filled(vx0, vx1, ry, ry + rh, _RADAR_CAM_COLOR)

    mid_y = ry + rh / 2.0

    # Fuel towers — cyan dots.
    for tower in self._towers:
        arcade.draw_circle_filled(to_rx(tower.center_x), mid_y, _RADAR_DOT_R, _RADAR_TOWER_COLOR)

    # All stationary enemies — red dots.
    for silo in self._silos:
        if silo.is_alive:
            arcade.draw_circle_filled(to_rx(silo.center_x), mid_y, _RADAR_DOT_R, _RADAR_ENEMY_COLOR)
    for turret in self._turrets:
        if turret.is_alive:
            arcade.draw_circle_filled(to_rx(turret.base.center_x), mid_y, _RADAR_DOT_R, _RADAR_ENEMY_COLOR)
    for lt in self._laser_turrets:
        if lt.is_alive:
            arcade.draw_circle_filled(to_rx(lt.base.center_x), mid_y, _RADAR_DOT_R, _RADAR_ENEMY_COLOR)

    # Patrol ships — red dots (moving).
    for patrol in self._patrols:
        if patrol.is_alive:
            arcade.draw_circle_filled(to_rx(patrol.center_x), mid_y, _RADAR_DOT_R, _RADAR_ENEMY_COLOR)

    # Boss — larger orange dot.
    if self._boss is not None and self._boss.is_alive:
        arcade.draw_circle_filled(
            to_rx(self._boss.body.center_x), mid_y,
            _RADAR_DOT_R * 2.5, _RADAR_BOSS_COLOR
        )

    # Player — bright yellow dot (drawn last so always visible on top).
    arcade.draw_circle_filled(
        to_rx(self._ship.center_x), mid_y,
        _RADAR_DOT_R * 1.5, _RADAR_PLAYER_COLOR
    )
```

### C3. Wire into `on_draw()`

`_draw_radar()` is called from `_draw_hud()` — already included in
Part B4 above. No additional wiring needed.

### C4. Radar position notes

The radar sits at the very bottom of the screen (`_RADAR_MARGIN_BOT = 6`).
The main HUD mask band is at the top. The gameplay corridor fills the
middle. This mirrors the Defender layout exactly. Make sure the HUD
mask band constant `_HUD_BAND_HEIGHT` is large enough to cover all HUD
rows (currently 80px — verify this still covers row 3 at sh-64).

---

## Part D — Sound Additions

### D1. Extra life sound

`assets/sounds/extraLife.wav` exists but is not currently used. Wire it
to play when the player gains a life (if that mechanic is ever added) or
at level complete as a bonus sound. For Phase 9, at minimum register it
in the sound manager so it's available:

```python
# In RunLevelView.__init__():
self._snd_extra_life = arcade.Sound(resource_path("assets/sounds/extraLife.wav"))
self._sm_extra_life  = SoundManager(max_simultaneous=1)
```

Play it in `_trigger_level_complete()` as a positive feedback sound:
```python
def _trigger_level_complete(self) -> None:
    self._sync_score_to_player()
    self._play_sfx(self._sm_extra_life, self._snd_extra_life)
    from src.base_attackers.state import GameState
    self._manager.transition(GameState.LEVEL_COMPLETE)
```

### D2. Confirm `laserSmall_001.wav` usage

`laserSmall_001.wav` is present in assets but not used. Either wire it
as an alternate player shoot sound (e.g. when big gun effect is active)
or leave it unused and note it in CLAUDE.md for future use.

---

## Part E — Final Config Cleanup

### E1. Reset `game_config.toml` for release

The config is currently set for testing:
```toml
starting_level = 5
num_lives = 6
debug = true
god_mode = false
```

Reset to production defaults:
```toml
starting_level = 1
num_lives = 3
debug = false
god_mode = false
```

### E2. Confirm `[window]` settings

```toml
[window]
width = 1422
height = 800
title = "Base Attackers"
```

1422×800 is not a standard 16:9 resolution (1422/800 = 1.7775, vs
16:9 = 1.7778 — close enough). This is fine; the window size was
tuned during development. Keep it.

---

## Part F — PyInstaller Build

### F1. Verify `build.py` includes all assets

Check `base_attackers.spec` for the `datas` list. Confirm these are
all bundled:
- `assets/images/` — all subdirectories
- `assets/fonts/` — both TTF files
- `assets/sounds/` — all WAV files
- `assets/music/` — all OGG/MP3 files (note: `awake10_megaWall.mp3`
  with capital W — must match exactly after the casing fix)

### F2. Run the build

```bash
python build.py
```

Then run `dist/base_attackers.exe` and verify:
- Window opens at 1422×800
- Fonts render correctly (KenVector Future2 Thin, not a fallback)
- Music plays from the bundled files
- All sprites load (no missing texture errors)
- Full game loop works: splash → menu → level → boss → level complete → next level

---

## Part G — agf v0.3.0 Tag and Pin

After the music casing fix is committed and all Phase 9 features are
stable, tag agf:

```bash
cd path/to/arcade-game-framework
git tag -a v0.3.0 -m "v0.3.0 — Base Attackers support: ScrollingGameWindow, MomentumShipMixin, WorldSpacePowerUpSpawner, music track cycling"
git push origin v0.3.0
```

Pin in `Base_Attackers/pyproject.toml`:
```toml
"arcade-game-framework @ git+https://github.com/darthwilliam1118/arcade-game-framework.git@v0.3.0"
```

Verify Space Attackers is still pinned to `v0.2.0` — it should be
untouched. Confirm with `pip show arcade-game-framework` in each venv.

---

## Part H — CLAUDE.md Updates

After implementing, update `CLAUDE.md`:

- HUD uses icon sprites (`_hud_lives_list`) for lives — SpriteList drawn
  in GUI camera space. Icons are `playerShip1.png` at scale 0.25.
  Visibility toggled in `_refresh_hud()` using cache-on-change pattern.
- Effects line (`_hud_effects`) shows active power-up names and durations.
  Updated via `_build_effects_str()` which iterates `_powerup_manager`
  active effects. Only redrawn when the string changes.
- Radar is drawn by `_draw_radar()` called from `_draw_hud()` in GUI
  camera space. Immediate-mode draw calls only — no sprites, no
  ShapeElementList. Maps world X linearly to radar strip pixel X.
  Tower/enemy/player/boss all rendered as coloured dots.
- `extraLife.wav` plays on level complete (positive feedback).
- Production config: `starting_level=1`, `num_lives=3`, `debug=false`.
- agf pinned to v0.3.0 tag. Space Attackers remains on v0.2.0.
- Font internal names: `"KenVector Future2"` and `"KenVector Future2 Thin"`.
  These are NOT filename-based. Both TTFs must be loaded at startup.
  NEVER pass `bold=True` with either font — no bold variant exists.

---

## Commit Sequence

```bash
# agf repo
git commit -m "fix: correct filename casing for awake10_megaWall.mp3"
git tag -a v0.3.0 -m "v0.3.0 — Base Attackers support complete"
git push && git push origin v0.3.0

# Base Attackers
git commit -m "chore: pin agf to v0.3.0 tag"
git commit -m "feat: HUD overhaul — icon lives, score format, effects line"
git commit -m "feat: radar minimap — Defender-style level overview strip"
git commit -m "feat: extra life SFX on level complete"
git commit -m "chore: reset game_config.toml to production defaults"
git commit -m "chore: verify PyInstaller build bundles all assets"
git commit -m "chore: update CLAUDE.md with Phase 9 patterns"
```

---

## Playtest Checklist

**HUD**
- [ ] Score shows `SCORE  000000` format, zero-padded to 6 digits
- [ ] Score increments correctly on enemy kills and level complete
- [ ] Level indicator shows `LEVEL  N` centred at top
- [ ] Lives show as ship icon sprites (not text), count decrements on death
- [ ] HP bar visible and shrinks as ship takes damage
- [ ] Fuel bar visible, colour shifts red below 25%, refills on docking
- [ ] Tower bar appears when docked, disappears on undock
- [ ] Active power-up effects line shows name + duration while active
- [ ] Effects line clears when all effects expire
- [ ] DOCKED indicator blinks while docked, disappears on undock
- [ ] Boss health bar appears centred when boss is alive, disappears on kill
- [ ] Power-up flash shows collected type for ~2s then clears
- [ ] GOD MODE label only when god_mode enabled (Shift+G)
- [ ] Debug row (FPS, X, hints) only when cfg.debug = true
- [ ] All HUD text renders in KenVector Future2 Thin — NOT a system font

**Radar**
- [ ] Radar strip visible at bottom of screen at all times
- [ ] Strip spans full window width (minus small margins)
- [ ] Camera viewport tint shows what fraction of the level is visible
- [ ] Player dot (yellow) moves right as ship advances
- [ ] Towers (cyan dots) appear at correct relative positions
- [ ] Enemy dots (red) appear at turret/silo/laser positions
- [ ] Patrol ship dots move as patrols fly through level
- [ ] Boss dot (orange, larger) appears when boss spawns
- [ ] All dots disappear when their entity is destroyed
- [ ] Radar updates correctly on every level (new procedural layout)

**Music**
- [ ] Menu/splash plays Ending track
- [ ] Level 1 plays Level 1 track
- [ ] Level 2 plays Level 2 track
- [ ] Level 3 plays Level 3 track
- [ ] Level 4 plays awake10_megaWall track (was broken before fix)
- [ ] Level 5 plays Cyberpunk Moonlight Sonata
- [ ] Level 6+ cycles back to level_1 track
- [ ] Music pauses/resumes correctly with P key
- [ ] Music transitions cleanly between levels

**Full game flow**
- [ ] Splash → main menu → start game → level 1 loads correctly
- [ ] `starting_level = 1`, `num_lives = 3`, `debug = false` in config
- [ ] Die once — lives decrements, respawns on same level
- [ ] Die until lives = 0 — game over screen with correct score
- [ ] Score entry appears if score qualifies
- [ ] Return to main menu from game over
- [ ] Reach boss zone → boss spawns → kill boss → level complete
- [ ] Level 2 loads with harder terrain and more enemies
- [ ] Complete 3 levels without dying — verify score accumulates across levels

**Cross-platform (Ubuntu)**
- [ ] Fonts render as KenVector Future2 Thin (not system font fallback)
- [ ] Music files load correctly (casing fix verified on Linux)
- [ ] Radar draws correctly
- [ ] No crashes or missing asset errors

**PyInstaller build (Windows)**
- [ ] `python build.py` completes without errors
- [ ] `dist/base_attackers.exe` launches
- [ ] All fonts, sprites, sounds, music present in bundled build
- [ ] Full game loop works from the exe

---

## User Actions Required (Summary)

1. **Check `_powerup_manager.active_effects`** — before writing
   `_build_effects_str()`, read `agf/src/agf/powerups/manager.py` to
   find the correct way to iterate active effects. The property may be
   named differently. Do not guess.

2. **Tune HUD bar positions** — the pixel positions in Part B4
   (`x=240`, `x=350` etc.) are estimates based on the current label
   widths. After first run, adjust until bars sit flush right of their
   labels with no overlap. Note final values in CLAUDE.md.

3. **Tune radar dot sizes** — `_RADAR_DOT_R = 2.0` is a starting point.
   On the 1422px-wide window the radar is 1398px wide showing a 6400-unit
   world. Scale factor is ~0.218 px/world-unit. At `sprite_scale=0.5`,
   a turret base is ~16px wide in the world → ~3.5px on the radar.
   A dot of radius 2 should be just visible. Adjust if dots are too small
   or too cluttered on a dense level.

4. **Verify Ubuntu font rendering** — run on Ubuntu and confirm that
   HUD text uses KenVector Future2 Thin, not a fallback. If any text
   renders in a wrong font, check `_load_fonts()` is called before any
   `arcade.Text` is constructed, and that the font internal names match
   exactly (case-sensitive).

5. **Run `python build.py` on Windows** — verify the exe works. If any
   asset is missing from the bundle, add it to the `datas` list in
   `base_attackers.spec`.

---

## Addendum — decisions & architecture changes during/after Phase 9

This records the significant decisions and structural changes made while
implementing Phase 9 and the boss-polish work that followed it.  CLAUDE.md
has the authoritative day-to-day detail; this is the high-level rationale.

### Font loading — real cross-platform bug fixed
- Symptom: all HUD/menu text rendered in a system fallback font, not
  KenVector.  `_load_fonts()` was correct and **was** being called (agf's
  `GameWindowBase.__init__` calls it).
- Root cause: pyglet selects its Windows font backend the first time
  `pyglet.font` is imported, reading `win32_gdi_font` at that instant.  The
  first `agf` import pulls in `arcade` → `pyglet.font`, so the option was
  read **before** the entry point set it — DirectWrite locked in, and
  DirectWrite cannot resolve a family name ending in a weight word
  ("KenVector Future2 Thin").
- Fix: both entry points (`main.py`, `src/base_attackers/__main__.py`) set
  the `win32_gdi_font` / audio pyglet options block **above** the first
  `agf` import.  Do not move it back down.

### Bosses are now fully config-driven, one per level
- Replaced the single hard-wired boss (old `[combat]` `boss_*` fields) with
  `BossSettings` + `BossWeapon` dataclasses (`game_config.py`) and
  `[boss.<key>]` TOML sections (incl. `[[boss.<key>.weapons]]`).  A level
  selects its boss via `[level_N] boss = "<key>"`;
  `GameConfig.boss_settings_for(level)` resolves it with a `"default"`
  fallback (procedural levels included).  The `boss_*` fields were removed
  from `CombatSettings`/`[combat]`.
- `BaseBoss(world_x, level_num, settings, sprite_scale)`.  `BossGun` is a
  single fixed weapon sprite (no base, no rotation, destructible) tagged
  with `weapon_type` (`"cannon"`|`"laser"`).  A weapon's `offset` is its
  sprite top-left relative to the body top-left in native px (may be
  negative); weapons scale with the body and bob with it.
- `[boss.default]` = the original level-1 boss; `[boss.alpha]` = the level-2
  "dreadnought" (body 200×160, 2 cannons + 2 lasers).

### Boss behaviours added
- **Vertical bob**: slow sine oscillation centred in the available band
  (floor↔ceiling, or floor↔world-top when open), amplitude clamped to the
  room, disabled if the band is too tight.
- **Cannons**: fixed sprite, bullets **aimed at the player** from the gun
  centre.
- **Lasers**: telegraph→firing→cooldown beam.  Decision: aim is **locked at
  the player when the telegraph starts** (not continuously tracked) so the
  warning beam is **dodgeable**; damage applied once on the firing
  transition (shield-aware).  Driven by the view
  (`_update_boss_lasers`/`_draw_boss_laser_beams`) on the existing
  `cfg.combat.laser_*` timings.
- **Boss bullets are NOT time-limited** — they cull on leaving the camera
  viewport (or terrain), so the player can't retreat out of range and wait.
- **Spawn-scroll-in**: the boss sits at `world_width * 0.92` and is created
  once the camera's right edge comes within `_BOSS_SPAWN_LEAD` (~600 px) of
  it, so it scrolls in from the right instead of popping into existence.
  Boss firing is gated on-screen (`can_fire`); the bob runs regardless.
- Z-order: boss body + guns draw **after** the enemy-bullet list (bullets
  emerge from under the boss); guns above the body; laser beams above guns.

### SVG → PNG art pipeline (boss art)
- New boss art is authored as **SVG** (`assets/svg/`) and converted to PNG
  by `src/base_attackers/svg_to_png.py`.  Decision: the converter is a
  **Pillow rect-rasterizer** with **no native dependencies** — `cairosvg`
  was dropped because its native `libcairo-2` won't load on 64-bit Windows
  (the DLL the user found was 32-bit, wrong arch).  The dev dep is now
  `pillow` (already present via arcade).
- It renders rect-based pixel-art SVGs only (`<rect>` x/y/w/h, `rx`, `fill`,
  `stroke`, `opacity`) to transparent RGBA, and **auto-skips spec boards**
  (any SVG containing `<text>`, e.g. the combined `boss_alpha_left_facing`
  reference sheet).  Export each sprite as its own rect SVG.
- Workflow: the converter writes to `assets/images/` root; sprites are then
  filed into subfolders by hand.  Boss PNGs live in
  `assets/images/PNG/Bosses/` and the boss config points there.

### HUD / radar / sound (the original Phase 9 body)
- Implemented per the brief, with the corrections already noted above
  (effects line uses `PowerUpManager.get_active_effects()` +
  `display_label`; lives are icon sprites; debug HUD gated by `cfg.debug`;
  radar `_draw_radar`; extra-life SFX on level complete).

### Outstanding before a real release (NOT yet done)
- **agf `v0.3.0` tagged + pinned** ✅ — the tag was created on agf commit
  `cd9ed76` and pushed; `pyproject.toml` now pins
  `…arcade-game-framework@v0.3.0`.  (Minor: agf's package `__version__` in
  `agf/__init__.py` is still `"0.2.0"`, so `pip show` reports 0.2.0 even
  though the git tag is v0.3.0 — cosmetic only.)
- **Production config is not reset.**  Committed `game_config.toml` has
  `debug = true` and `music_volume = 40` (active playtest values).  Reset
  to `debug = false`, `music_volume = 80` (and confirm `starting_level = 1`,
  `num_lives = 3`) before building a release.
- **PyInstaller release build** not re-verified after the boss/art changes.
