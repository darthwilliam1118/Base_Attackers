# Feature Brief — Phase 8: Boss Encounter

**Game:** Base Attackers
**Phase:** 8 of 9
**Depends on:** Phase 7 complete — procedural levels, full level flow,
`PLAYER_KILLED` / `LEVEL_COMPLETE` / `GAME_OVER` all wired
**Output:** A boss that appears at the end of every level, with multiple
weapon hardpoints, a visible health bar, a multi-explosion death
sequence, and clean wiring into the existing level-complete flow
**agf changes required:** None — all boss logic is game-specific

**Recommended split:** implement in two Claude Code sessions.
- **Session 1** — `BaseBoss`, body sprite, health bar, weapon hardpoints,
  placement in boss zone, rendering
- **Session 2** — weapon firing logic, death sequence, RunLevelView
  wiring, `_on_boss_zone_reached()` replacement

---

## Goals

1. `BaseBoss` class — large sprite with multiple `GunTurret`-style
   hardpoints that fire independently, a health pool scaled by level,
   and a `take_damage()` / `is_alive` interface
2. Boss body: `enemyBlackBoss.png` scaled up (~3× `sprite_scale`), 
   centered in the boss zone, stationary (no movement in Phase 8)
3. Hardpoints: 2–4 `GunTurret` instances attached to the boss body,
   positioned relative to boss center, firing at the player
4. Boss health bar: wide bar drawn in GUI camera space above the HUD,
   distinct from the ship HP bar, shrinks as boss takes damage
5. Death sequence: 2–3 seconds of multiple explosions scattered across
   the boss body before `_trigger_level_complete()` fires
6. Replace `_on_boss_zone_reached()` placeholder with real boss spawn
7. Player bullets and collision wired to boss hardpoints and body
8. Commit, run on both platforms, full boss fight playtest

---

## Step 0 — Before Writing Any Code

Read these files in full before writing a single line:

```
src/base_attackers/views/run_level.py
  — on_show_view(), _place_from_layout(), on_update(), on_draw()
  — _on_boss_zone_reached() — this is the ONLY entry point to replace
  — _trigger_level_complete() — do NOT modify, boss calls this when dead
  — _check_player_bullet_hits() — add boss collision here
  — _check_enemy_hits() — boss bullets already use _enemy_bullet_list
  — _damage_player() — boss weapons route through this unchanged
  — _destroy_ship() — death goes to PLAYER_KILLED unchanged

src/base_attackers/enemies/gun_turret.py
  — GunTurret constructor, position_on_terrain(), update(), fire_bullet()
  — Boss hardpoints reuse GunTurret directly — no subclass needed

src/base_attackers/game_config.py
  — CombatSettings, LevelGenSettings — add boss config fields here

game_config.toml
  — starting_level = 5, debug = true — good for boss testing
  — window: 1422×800, sprite_scale = 0.5

assets/images/PNG/Enemies/enemyBlackBoss.png — boss body sprite (exists)
assets/images/PNG/Parts/ — gun04.png barrel used by GunTurret hardpoints
```

**Critical patterns to carry forward exactly:**
- All sprites must be in a SpriteList — no standalone `.draw()` calls
- Composite enemies (boss body + hardpoints) follow the GunTurret pattern:
  owner class holds sprite references, RunLevelView manages SpriteLists
- Two-step construct + position: boss body sprite height known only after
  texture loads; position boss AFTER construction
- `EnemyBullet` constructor requires `lifetime=` kwarg (added in Phase 7)
- `_damage_player()` is the single gate for all damage — boss weapons
  create `EnemyBullet` objects that enter `_enemy_bullet_list` and hit
  the player via the existing `_check_enemy_hits()` — no new collision
  path needed

---

## Part A — Config Extensions

### A1. Add boss config to `game_config.toml` `[combat]` section

```toml
# Boss
boss_scale_factor = 3.0        # boss sprite = sprite_scale * this
boss_hp_base = 30              # HP at level 1
boss_hp_per_level = 10         # additional HP per level above 1
boss_hardpoint_count = 3       # gun turrets attached to boss body
boss_fire_cooldown = 1.2       # seconds between each hardpoint shot
boss_bullet_speed = 220.0      # px/s — slightly slower than turret bullets
boss_death_duration = 2.5      # seconds of death explosion before level complete
boss_death_explosion_interval = 0.25  # seconds between death explosions
```

### A2. Wire into `CombatSettings` dataclass and `GameConfig.load()`

Add fields with the above defaults to `CombatSettings`. Parse from
`combat_raw` in `GameConfig.load()` following the exact same pattern
as the laser turret fields immediately above them.

---

## Part B — BaseBoss Class

Create `src/base_attackers/bosses/boss.py`.

```
src/base_attackers/bosses/
    __init__.py
    boss.py
```

### B1. Class design

`BaseBoss` is NOT itself an `arcade.Sprite`. It follows the same
composite pattern as `GunTurret`:
- Owns a `body` sprite (`arcade.Sprite`) for the boss body
- Owns a list of `GunTurret` hardpoints attached relative to body center
- `RunLevelView` manages all SpriteLists

```python
"""BaseBoss — large stationary boss enemy with multiple gun hardpoints.

Composite object: owns a body sprite and N GunTurret hardpoints.
RunLevelView adds the body to _boss_body_list, hardpoint bases to
_turret_base_list (reused), and hardpoint barrels to _turret_barrel_list
(reused) — this means existing player-bullet-vs-turret collision
detection automatically hits boss hardpoints for free.

Placement: boss center is set by RunLevelView after construction once
body.height is known (same two-step pattern as FuelTower/GunTurret).
"""
from __future__ import annotations

import math
import arcade
from agf.paths import resource_path
from src.base_attackers.enemies.gun_turret import GunTurret
from src.base_attackers.combat.enemy_bullet import EnemyBullet
from src.base_attackers.game_config import CombatSettings

_BODY_SPRITE      = "assets/images/PNG/Enemies/boss_body.png"
_BOSS_BULLET_PATH = "assets/images/PNG/Lasers/boss_shot1.png"


class BossBullet(EnemyBullet):
    """Boss-specific bullet — identical to EnemyBullet but uses the
    dedicated boss_shot1.png sprite.  Constructed the same way;
    RunLevelView adds to _enemy_bullet_list and existing collision
    detection handles it automatically.
    """

    def __init__(
        self,
        x: float,
        y: float,
        angle_rad: float,
        speed: float,
        scale: float,
        lifetime: float = 3.0,
    ) -> None:
        # Bypass EnemyBullet.__init__ texture load and load our own.
        arcade.Sprite.__init__(
            self,
            arcade.load_texture(
                resource_path(_BOSS_BULLET_PATH),
                hit_box_algorithm=arcade.hitbox.algo_simple,
            ),
            scale=scale,
        )
        self.center_x = x
        self.center_y = y
        self._vx = math.cos(angle_rad) * speed
        self._vy = math.sin(angle_rad) * speed
        # Reuse EnemyBullet's natural bearing constant (0 = east).
        self.angle = 0.0 - math.degrees(angle_rad)
        self._lifetime = lifetime
        self._age = 0.0


class BaseBoss:
    def __init__(
        self,
        world_x: float,
        level_num: int,
        cfg: CombatSettings,
        sprite_scale: float,
    ) -> None:
        self.cfg = cfg
        self.level_num = level_num

        # HP scales with level.
        self.max_hp: int = cfg.boss_hp_base + (level_num - 1) * cfg.boss_hp_per_level
        self.hp: int = self.max_hp

        # Body sprite — large, centered in boss zone.
        boss_scale = sprite_scale * cfg.boss_scale_factor
        self.body = arcade.Sprite(resource_path(_BODY_SPRITE), scale=boss_scale)
        self.body.center_x = world_x
        self.body.center_y = 0.0   # caller sets after construction

        # Hardpoints — GunTurret instances positioned relative to body.
        # Positions are set in _attach_hardpoints() once body.height known.
        self.hardpoints: list[GunTurret] = []
        self._sprite_scale = sprite_scale

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if boss is destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    @property
    def hp_fraction(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    def place(self, center_y: float) -> None:
        """Set vertical position and attach hardpoints.

        Call after construction once body.height is available:
            boss = BaseBoss(...)
            boss.place(corridor_center_y)
        """
        self.body.center_y = center_y
        self._attach_hardpoints()

    def _attach_hardpoints(self) -> None:
        """Create GunTurret hardpoints positioned around the boss body.

        Hardpoints are standard GunTurret instances with custom fire
        cooldown. Their base sprites are positioned relative to the boss
        body center so they appear to be part of the boss.

        For boss_hardpoint_count = 3, positions:
          - Top hardpoint:    body center + (0, body.height * 0.3)
          - Mid-left:         body center + (-body.width * 0.3, 0)
          - Mid-right:        body center + (+body.width * 0.3, 0)
        Adjust offsets if the art looks wrong — these are starting points.
        """
        cfg = self.cfg
        hw = self.body.width / 2.0
        hh = self.body.height / 2.0
        cx = self.body.center_x
        cy = self.body.center_y

        # Override fire cooldown for boss hardpoints.
        boss_cfg = _BossCombatSettings(cfg)

        count = min(cfg.boss_hardpoint_count, 4)
        offsets: list[tuple[float, float, str]] = []
        if count >= 1:
            offsets.append((0.0,        hh * 0.5,   "floor"))    # top
        if count >= 2:
            offsets.append((-hw * 0.4,  0.0,        "floor"))    # left
        if count >= 3:
            offsets.append(( hw * 0.4,  0.0,        "floor"))    # right
        if count >= 4:
            offsets.append((0.0,       -hh * 0.5,   "ceiling"))  # bottom

        for ox, oy, surface in offsets:
            turret = GunTurret(
                world_x=cx + ox,
                surface=surface,
                cfg=boss_cfg,
                scale=self._sprite_scale,
            )
            # Position hardpoints directly — no terrain surface needed.
            # We set the base center manually instead of calling
            # position_on_terrain() since boss hardpoints float in space.
            half_base   = turret.base.height   / 2.0
            half_barrel = turret.barrel.height / 2.0
            turret.base.center_x   = cx + ox
            turret.base.center_y   = cy + oy
            turret.barrel.center_x = cx + ox
            if surface == "floor":
                turret.base.angle         = 180.0
                turret._barrel_offset_y   = half_base + half_barrel + 2.0
            else:
                turret.base.angle         = 0.0
                turret._barrel_offset_y   = -(half_base + half_barrel + 2.0)
            turret.barrel.center_y = turret.base.center_y + turret._barrel_offset_y
            self.hardpoints.append(turret)

    def update(self, ship_x: float, ship_y: float, delta_time: float) -> list:
        """Tick all hardpoints; return list of BossBullet objects to spawn.

        Boss body is stationary — no movement update needed.
        Hardpoints rotate and fire independently.
        """
        bullets = []
        for hp in self.hardpoints:
            if not hp.is_alive:
                continue
            fired = hp.update(ship_x, ship_y, delta_time)
            if fired:
                # Use BossBullet instead of EnemyBullet so boss shots use
                # the dedicated boss_shot1.png sprite.  Same collision path.
                import math as _math
                angle_rad = _math.radians(hp._aim_angle)
                bullet = BossBullet(
                    x=hp.barrel.center_x,
                    y=hp.barrel.center_y,
                    angle_rad=angle_rad,
                    speed=self.cfg.boss_bullet_speed,
                    scale=self._sprite_scale,
                    lifetime=self.cfg.enemy_bullet_lifetime,
                )
                bullets.append(bullet)
        return bullets
```

### B2. `_BossCombatSettings` shim

`GunTurret` reads `cfg.turret_fire_cooldown` and `cfg.turret_aim_jitter`.
Boss hardpoints need a different cooldown. A simple shim avoids modifying
`GunTurret` or duplicating the class:

```python
class _BossCombatSettings:
    """Thin wrapper that overrides turret_fire_cooldown for boss hardpoints."""
    def __init__(self, base: CombatSettings) -> None:
        self._base = base

    def __getattr__(self, name: str):
        if name == "turret_fire_cooldown":
            return self._base.boss_fire_cooldown
        return getattr(self._base, name)
```

Place this class at the top of `boss.py`, before `BaseBoss`.

---

## Part C — RunLevelView Wiring

### C1. New SpriteLists in `__init__()`

Add alongside the existing turret lists:

```python
self._boss_body_list  = arcade.SpriteList()   # one sprite max
self._boss: BaseBoss | None = None
self._boss_death_timer: float = 0.0
self._boss_explosion_timer: float = 0.0
```

### C2. Replace `_on_boss_zone_reached()`

```python
def _on_boss_zone_reached(self) -> None:
    """Spawn the boss at the boss zone and switch to boss-fight mode."""
    log.info("Boss zone reached on level %d — spawning boss", self._level_num)
    self._spawn_boss()

def _spawn_boss(self) -> None:
    assert self._terrain is not None and self._terrain_cfg is not None
    from src.base_attackers.bosses.boss import BaseBoss

    cfg = self._cfg.combat
    # Center X: 92% of world width (center of boss zone).
    boss_x = self._terrain_cfg.world_width * 0.92
    boss = BaseBoss(
        world_x=boss_x,
        level_num=self._level_num,
        cfg=cfg,
        sprite_scale=self._cfg.sprite_scale,
    )
    # Two-step: set Y after construction once body.height is known.
    floor_y = self._terrain.floor_y_at(boss_x)
    ceil_y  = self._terrain.ceiling_y_at(boss_x)
    if ceil_y is not None:
        center_y = (floor_y + ceil_y) / 2.0
    else:
        center_y = floor_y + boss.body.height / 2.0 + 20.0
    boss.place(center_y)

    # Add body to its own list.
    self._boss_body_list.append(boss.body)
    # Add hardpoint sprites to the EXISTING turret lists so existing
    # player-bullet collision detection hits them automatically.
    for hp in boss.hardpoints:
        self._turret_base_list.append(hp.base)
        self._turret_barrel_list.append(hp.barrel)
    self._boss = boss
```

### C3. Boss update in `on_update()`

Add after `_update_turrets(delta_time)` and before
`_update_laser_turrets(delta_time)`:

```python
self._update_boss(delta_time)
if self._boss_death_timer > 0.0:
    return   # death sequence running — skip remaining updates
```

```python
def _update_boss(self, delta_time: float) -> None:
    if self._boss is None:
        return

    # Death sequence tick.
    if self._boss_death_timer > 0.0:
        self._boss_death_timer -= delta_time
        self._boss_explosion_timer -= delta_time
        if self._boss_explosion_timer <= 0.0:
            self._boss_explosion_timer = self._cfg.combat.boss_death_explosion_interval
            self._spawn_boss_death_explosion()
        self._explosion_list.update(delta_time)
        if self._boss_death_timer <= 0.0:
            self._finish_boss_death()
        return

    if not self._boss.is_alive:
        return

    # Normal update — tick hardpoints, collect fired bullets.
    bullets = self._boss.update(
        self._ship.center_x, self._ship.center_y, delta_time
    )
    for bullet in bullets:
        self._enemy_bullet_list.append(bullet)
        self._play_sfx(self._sm_enemy_shoot, self._snd_enemy_shoot)
```

### C4. Boss death sequence

```python
def _start_boss_death(self) -> None:
    """Hide the boss body, begin explosion sequence."""
    assert self._boss is not None
    self._boss.body.visible = False
    for hp in self._boss.hardpoints:
        hp.base.visible   = False
        hp.barrel.visible = False
    self._boss_death_timer      = self._cfg.combat.boss_death_duration
    self._boss_explosion_timer  = 0.0   # fire first explosion immediately

def _spawn_boss_death_explosion(self) -> None:
    """Spawn one explosion at a random offset within the boss body."""
    import random
    assert self._boss is not None
    hw = self._boss.body.width  / 2.0
    hh = self._boss.body.height / 2.0
    cx = self._boss.body.center_x
    cy = self._boss.body.center_y
    ex = cx + random.uniform(-hw * 0.8, hw * 0.8)
    ey = cy + random.uniform(-hh * 0.8, hh * 0.8)
    explosion = ExplosionSprite(
        x=ex, y=ey,
        scale=max(1.0, self._cfg.sprite_scale * 3.0),
    )
    self._explosion_list.append(explosion)
    self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)

def _finish_boss_death(self) -> None:
    """Clean up boss sprites and trigger level complete."""
    assert self._boss is not None
    self._boss.body.remove_from_sprite_lists()
    for hp in self._boss.hardpoints:
        hp.base.remove_from_sprite_lists()
        hp.barrel.remove_from_sprite_lists()
    self._boss = None
    self._score += self._level_num * 500   # score scales with level
    self._trigger_level_complete()
```

### C5. Wire `_start_boss_death()` into player bullet hits

In `_check_player_bullet_hits()`, add after laser turret base check:

```python
# vs boss body
if self._boss is not None and self._boss.is_alive and self._boss_death_timer <= 0.0:
    for bullet in list(self._bullet_list):
        if not bullet.sprite_lists:
            continue
        hits = arcade.check_for_collision_with_list(
            bullet, self._boss_body_list
        )
        if hits:
            bullet.remove_from_sprite_lists()
            if self._boss.take_damage(self._ship.player_bullet_damage):
                self._start_boss_death()
            break
```

**Note:** Boss hardpoints already share `_turret_base_list` — they are
destroyed by the existing turret collision code automatically. When all
hardpoints are destroyed the boss body still has HP; players must shoot
the body directly to finish the boss. Hardpoints dead = easier fight,
but body kill is required for level complete.

### C6. Boss draw in `on_draw()`

Add `_boss_body_list.draw()` after `_turret_barrel_list.draw()`:

```python
self._turret_barrel_list.draw()
self._boss_body_list.draw()     # Phase 8 addition
self._laser_base_list.draw()
```

### C7. Boss health bar in `_draw_hud()`

Draw a wide health bar at the top of the HUD band, centred, only when
boss is alive:

```python
def _draw_boss_health_bar(self) -> None:
    if self._boss is None or not self._boss.is_alive:
        return
    sw = self.window.width
    sh = self.window.height
    bar_w   = sw * 0.5
    bar_h   = 14.0
    bar_x   = (sw - bar_w) / 2.0
    bar_y   = sh - 18.0
    frac    = self._boss.hp_fraction
    # Background
    arcade.draw_lrbt_rectangle_filled(
        bar_x, bar_x + bar_w,
        bar_y, bar_y + bar_h,
        (60, 60, 60, 200),
    )
    # Foreground — red, shifts to orange when below 30%
    color = (255, 100, 30) if frac < 0.3 else (220, 40, 40)
    arcade.draw_lrbt_rectangle_filled(
        bar_x, bar_x + bar_w * frac,
        bar_y, bar_y + bar_h,
        color,
    )
    # Label — "BOSS" left of bar
    if self._hud_boss_label is not None:
        self._hud_boss_label.draw()
```

Add `_hud_boss_label` Text object in `_build_hud()`:

```python
self._hud_boss_label = arcade.Text(
    "BOSS",
    (sw - sw * 0.5) / 2.0 - 50,
    sh - 18.0,
    arcade.color.RED,
    font_size=12,
    font_name=FONT_THIN,
    anchor_y="bottom",
)
```

Call `_draw_boss_health_bar()` at the end of `_draw_hud()`.

---

## Part D — Stopping Patrol Spawns During Boss Fight

While the boss is alive, suppress autonomous patrol spawns — the boss
fight should feel focused, not crowded with distractions. Keep dock
pressure spawns (they reflect active pressure while docked, which is
still valid):

```python
# In on_update(), modify the patrol spawn block:
self._patrol_spawn_timer -= delta_time
if self._patrol_spawn_timer <= 0.0:
    self._patrol_spawn_timer = self._cfg.combat.patrol_spawn_interval
    if self._boss is None:   # only auto-spawn outside boss fight
        self._spawn_patrol_ship()
```

---

## Part E — CLAUDE.md Updates

After implementing, add to `CLAUDE.md`:

- `BossBullet` subclasses `EnemyBullet` and uses `boss_shot1.png`.
  Constructed directly in `BaseBoss.update()` using `hp._aim_angle`.
  Goes into `_enemy_bullet_list` — existing collision handles it.
- `BaseBoss` is in `src/base_attackers/bosses/boss.py`. NOT a Sprite —
  owns `body` (arcade.Sprite) and `hardpoints` (list[GunTurret]).
- Boss body goes in `_boss_body_list`. Hardpoint sprites go into the
  EXISTING `_turret_base_list` and `_turret_barrel_list` — existing
  player bullet collision hits them automatically for free.
- `_BossCombatSettings` shim overrides `turret_fire_cooldown` for boss
  hardpoints without modifying `GunTurret` or `CombatSettings`.
- Boss placement two-step: construct first, then `boss.place(center_y)`
  once `boss.body.height` is known. `place()` also calls
  `_attach_hardpoints()` so hardpoint positions are relative to the
  final body Y.
- `_boss_death_timer > 0` means death sequence is running — skip all
  other updates during this window (return early in `_update_boss`).
- `_trigger_level_complete()` is called by `_finish_boss_death()` — do
  NOT call it anywhere else in the boss flow.
- Boss score = `level_num * 500` — scales with difficulty.
- Patrol auto-spawns are suppressed while boss is alive (`self._boss is
  None` guard). Dock pressure spawns are NOT suppressed.
- `boss_hp_base + (level_num - 1) * boss_hp_per_level` — HP formula.
  Level 1 boss = 30 HP. Level 5 boss = 70 HP.

---

## Session Checkpoint (between Session 1 and Session 2)

**End of Session 1** — commit and verify before starting Session 2:

```bash
git commit -m "feat: BaseBoss class with body sprite and hardpoint attachment"
git commit -m "feat: RunLevelView boss SpriteLists and _spawn_boss()"
git commit -m "feat: boss body draw and health bar HUD"
```

**Verify before Session 2:**
- [ ] Boss body sprite appears in boss zone when ship reaches 85% of
      world width
- [ ] Boss hardpoints visible as turret base/barrel pairs on the boss
- [ ] Boss health bar visible in HUD top-centre when boss is alive
- [ ] No crashes on boss zone entry

**Session 2 starts here** — read run_level.py again before continuing.

---

## Commit Sequence

```bash
# Session 1
git commit -m "feat: BaseBoss class with body, hardpoints, _BossCombatSettings shim"
git commit -m "feat: boss config fields in CombatSettings and game_config.toml"
git commit -m "feat: RunLevelView boss spawn, draw, health bar"

# Session 2
git commit -m "feat: boss update loop, hardpoint firing, enemy bullets"
git commit -m "feat: boss death sequence with multi-explosion and level complete"
git commit -m "feat: player bullet vs boss body collision"
git commit -m "feat: suppress patrol spawns during boss fight"
git commit -m "chore: update CLAUDE.md with Phase 8 boss patterns"
```

---

## Playtest Checklist

**Boss appearance**
- [ ] Boss spawns when ship crosses 85% of world width (boss zone)
- [ ] Boss body is visibly large (~3× normal enemy size)
- [ ] Boss is centred vertically in the corridor
- [ ] Hardpoints visible on the boss body at correct offsets
- [ ] Boss health bar appears centred at top of HUD
- [ ] Patrol ships stop auto-spawning when boss appears

**Boss combat**
- [ ] Hardpoint barrels rotate to track player
- [ ] Hardpoints fire at `boss_fire_cooldown` interval
- [ ] Boss bullets enter `_enemy_bullet_list` and damage player correctly
- [ ] Shield absorbs boss bullets (routes through `_damage_player`)
- [ ] Player bullets hitting hardpoint bases damage the hardpoint
- [ ] Destroyed hardpoint base/barrel disappear; boss body remains
- [ ] Player bullets hitting the boss BODY damage boss HP
- [ ] Boss health bar shrinks correctly as HP decreases
- [ ] Health bar shifts orange below 30% HP

**Boss death sequence**
- [ ] Killing boss (HP → 0) triggers death sequence
- [ ] Boss body and hardpoints become invisible immediately
- [ ] Multiple explosions appear scattered across boss area over 2.5s
- [ ] Explosion SFX plays for each death explosion
- [ ] After death sequence, level complete screen appears
- [ ] Score incremented by `level_num * 500`

**Level scaling**
- [ ] Level 1 boss: 30 HP
- [ ] Level 5 boss: 70 HP (use `starting_level = 5` in config to test)
- [ ] `starting_level = 5` with `debug = true` and `god_mode = false`:
      boss fight is noticeably harder than level 1

**Integration**
- [ ] Dying during boss fight → `PLAYER_KILLED` → respawn on same level
      with boss zone re-enterable (boss resets)
- [ ] Full run: level 1 start → boss zone → boss death → level complete
      → level 2 loads with new terrain and boss

---

## User Actions Required (Summary)

1. **`boss_body.png` is in `assets/images/PNG/Enemies/`** and
   **`boss_shot1.png` is in `assets/images/PNG/Lasers/`** — both
   confirmed present, no action needed. If after playtesting the boss
   body looks too small even at 3× scale, adjust `boss_scale_factor`
   in `game_config.toml`.

2. **Hardpoint offsets** — the offsets in `_attach_hardpoints()` are
   geometric starting points based on body half-width/height. After
   first run, adjust `hw * 0.4` and `hh * 0.5` multipliers until
   hardpoints look like they're attached to the boss rather than
   floating near it. Add a note to CLAUDE.md with the final values.

3. **Boss HP tuning** — `boss_hp_base = 30` and `boss_hp_per_level = 10`
   are starting points. A solo playtester should be able to kill the
   level 1 boss in roughly 20–30 seconds of sustained fire. Adjust
   the base and per-level values in `game_config.toml`.

4. **Boss fire cooldown** — `boss_fire_cooldown = 1.2` means each
   hardpoint fires roughly once per second. With 3 hardpoints that's
   ~2.5 bullets/sec total. Tune this until the boss feels dangerous
   but not overwhelming on level 1.

5. **Run on both Windows and Ubuntu** — verify boss sprite scaling and
   hardpoint positioning are consistent across platforms.

6. **Report back to Claude.ai** before Phase 9:
   - Final tuned boss HP and fire cooldown values
   - Final hardpoint offset multipliers
   - Whether the boss zone feels the right size
   - Whether the death sequence duration feels dramatic or too long
