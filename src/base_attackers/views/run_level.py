"""RunLevelView — main gameplay view.

Builds the level's terrain from ``GameConfig.levels[N]`` (renderer kind
selected by ``terrain_renderer``), spawns the player ship at the level
entry, runs momentum physics via ``MomentumShipMixin``, follows the
ship with a deadzone-tracking world camera (X monotonically clamped
plus a right-edge stop; Y degenerates while
``world_height <= window_height``), and renders the HUD in GUI-camera
space.

Phase 3 additions:
- Fuel drain during flight; fuel-empty disables input and applies a
  separate ``fuel_gravity`` that bypasses normal momentum/friction so
  the ship plummets without ``friction`` damping the fall.
- ``FuelTower`` fixtures (3 hardcoded positions for this phase); the
  ship snaps to a tower's dock point when within ``snap_distance``.
  Fuel transfers each frame while docked.
- Fuel-canister collectibles (3 hardcoded positions) — touching one
  refunds ``fuel_canister_restore`` and removes the sprite.
- HUD bars (HP, fuel, tower-fuel while docked) drawn with
  ``draw_lrbt_rectangle_filled`` inside the existing HUD mask band.
- Ship destruction sequence: ``ExplosionSprite`` at the ship position,
  then a 1.5s timer before the ``GAME_OVER`` transition.  Terrain
  contact (instant kill) routes through this sequence.

Terrain collision is still tested via the ship's tight (algo_detailed)
hitbox before committing the new position; on contact the destruction
sequence fires.
"""

from __future__ import annotations

import gc
import logging
from typing import TYPE_CHECKING

import arcade
from pyglet.math import Vec2

from agf.paths import resource_path
from agf.powerups import WorldSpacePowerUpSpawner
from agf.powerups.powerup_sprite import PowerUpSprite
from agf.music import track_key_for_level
from agf.ships.momentum import MomentumConfig
from agf.sound_manager import SoundManager
from agf.sprites.explosion import ExplosionSprite
from agf.ui.text_utils import FONT_THIN
from src.base_attackers.bosses import BaseBoss, BossBullet, BossGun
from src.base_attackers.combat import EnemyBullet, Missile, PlayerBullet
from src.base_attackers.enemies import (
    BEHAVIOUR_INTERCEPT,
    BEHAVIOUR_KAMIKAZE,
    BEHAVIOUR_STRAIGHT,
    GunTurret,
    LaserTurret,
    MissileSilo,
    PatrolShip,
)
from src.base_attackers.game_config import GameConfig, LevelSettings
from src.base_attackers.levels.level_generator import (
    LevelGenerator,
    LevelLayout,
    derive_seed,
)
from src.base_attackers.powerups import BAPowerUpManager
from src.base_attackers.ships import PlayerShip
from src.base_attackers.sprites import ShieldSprite
from src.base_attackers.terrain import (
    PolygonTerrainRenderer,
    TerrainBase,
    TerrainConfig,
    TileTerrainRenderer,
    generate_corridor_profile,
)
from src.base_attackers.terrain_features import FuelTower

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


log = logging.getLogger(__name__)


# Ship must stay inside this fraction of the window width / height before
# the world camera moves.
_DEADZONE_LEFT = 0.25
_DEADZONE_RIGHT = 0.65
_DEADZONE_TOP = 0.80
_DEADZONE_BOTTOM = 0.20

# Phase 5 power-up textures (effect_type -> asset path).  Registered with
# PowerUpSprite once during RunLevelView.__init__.
_POWERUP_TEXTURES: dict[str, str] = {
    "health": "assets/images/PNG/Power-ups/pill_red.png",
    "fuel_canister": "assets/images/PNG/Power-ups/bolt_gold.png",
    "rapid_fire": "assets/images/PNG/Power-ups/bolt_silver.png",
    "big_gun": "assets/images/PNG/Power-ups/bolt_bronze.png",
    "multi_shot": "assets/images/PNG/Power-ups/star_gold.png",
    "shield": "assets/images/PNG/Power-ups/powerupBlue_shield.png",
}
_POWERUP_FLASH_DURATION = 2.0
_MULTI_SHOT_SPREAD_DEG = (-10.0, 0.0, 10.0)

# SFX paths and SoundManager throttle limits.
_SND_PLAYER_SHOOT = "assets/sounds/laserSmall_000.wav"
_SND_ENEMY_SHOOT = "assets/sounds/laserLarge_000.wav"
_SND_ENEMY_BOOM = "assets/sounds/explosionCrunch_000.wav"
_SND_PLAYER_BOOM = "assets/sounds/explosionCrunch_004.wav"
_SND_EXTRA_LIFE = "assets/sounds/extraLife.wav"

# Death sequence + dock indicator timings.
_DEATH_DURATION = 1.5
_DOCK_BLINK_PERIOD = 0.4

# Undock liftoff: instantaneous Y kick (px/s) away from the tower, plus a
# dock-check cooldown so the ship clears `snap_distance` before the dock
# scanner runs again.  Direction is +Y for floor towers, -Y for ceiling
# towers (chosen via tower.surface).
_LIFTOFF_SPEED = 200.0
_DOCK_COOLDOWN = 1.0

# Height (px) of the solid HUD band at the top of the screen.  The HUD
# text rows span sh-20 .. sh-80, so 80 px backs them all.  The mask is
# clamped to at least this band so tall levels (world_height > window
# height) still get a backdrop and never invert the draw rectangle.
_HUD_BAND_HEIGHT = 80.0

# HUD bar geometry (screen space; offsets from sh = window.height).
# Bars are positioned to sit on the same row as their accompanying text
# inside the existing HUD mask band.
_BAR_HEIGHT = 10.0
_HP_BAR_X = 120.0
_HP_BAR_W = 120.0
_FUEL_BAR_X = 120.0
_FUEL_BAR_W = 180.0
_TOWER_BAR_X = 320.0
_TOWER_BAR_W = 140.0
_BAR_BG_COLOR = (60, 60, 60, 200)
_FUEL_COLOR = (80, 200, 255)
_FUEL_COLOR_LOW = (255, 80, 80)
_FUEL_LOW_FRAC = 0.25
_HP_COLOR = (80, 220, 80)
_TOWER_COLOR = (255, 160, 60)

# HUD text rows (screen-Y offsets from sh = window.height).  Four rows
# inside the _HUD_BAND_HEIGHT band.  Row 1 holds SCORE / LEVEL / lives;
# row 2 holds the boss bar + effects line; rows 3/4 hold the HP/FUEL
# text + bars.
_ROW1_Y = 20.0
_ROW2_Y = 44.0
_ROW3_Y = 60.0
_ROW4_Y = 80.0

# Lives icon sprites.
_LIVES_ICON_SCALE = 0.25
_LIVES_ICON_PATH = "assets/images/PNG/playerShip1.png"
_LIVES_ICON_MAX = 6

# Defender-style radar strip (drawn in GUI-camera space, immediate mode).
_RADAR_HEIGHT = 28.0  # px height of the radar strip
_RADAR_MARGIN_X = 12.0  # px from window left/right edges
_RADAR_MARGIN_BOT = 6.0  # px from window bottom
_RADAR_BG_COLOR = (20, 30, 20, 200)
_RADAR_BORDER_COLOR = (60, 100, 60, 255)
_RADAR_PLAYER_COLOR = (255, 255, 100, 255)  # bright yellow dot
_RADAR_ENEMY_COLOR = (255, 80, 80, 200)  # red dots
_RADAR_TOWER_COLOR = (80, 200, 255, 200)  # cyan dots
_RADAR_BOSS_COLOR = (255, 100, 30, 255)  # orange dot
_RADAR_CAM_COLOR = (255, 255, 255, 60)  # white tint for visible area
_RADAR_DOT_R = 2.0  # radius of entity dots
_EFFECTS_COLOR = (180, 220, 255, 255)


def _build_terrain(
    cfg: GameConfig,
    level_cfg: LevelSettings,
    screen_w: int,
    seed_override: int | None = None,
) -> tuple[TerrainBase, TerrainConfig]:
    """Instantiate the configured renderer for *level_cfg*.

    An explicit non-zero ``level_cfg.terrain_seed`` always wins (per-level
    reproducible shape); otherwise ``seed_override`` (the per-game derived
    level seed) is used so a level is identical across a respawn but varies
    between games.  ``None`` means a random profile.
    """
    if level_cfg.terrain_seed != 0:
        seed: int | None = level_cfg.terrain_seed
    else:
        seed = seed_override
    tcfg = TerrainConfig(
        world_width=level_cfg.world_width,
        world_height=level_cfg.world_height,
        chunk_width=cfg.terrain.chunk_width,
        cull_buffer_chunks=cfg.terrain.cull_buffer_chunks,
        amplitude=level_cfg.terrain_amplitude,
        frequency=level_cfg.terrain_frequency,
        half_width=level_cfg.terrain_half_width,
        ceiling_present=level_cfg.ceiling_present,
    )
    profile = generate_corridor_profile(tcfg, seed=seed)
    if level_cfg.terrain_renderer == "polygon":
        return PolygonTerrainRenderer(profile, tcfg, screen_w), tcfg
    return TileTerrainRenderer(profile, tcfg, screen_w), tcfg


class RunLevelView(arcade.View):
    def __init__(self, manager: "GameStateManager") -> None:
        super().__init__()
        self._manager = manager
        cfg: GameConfig = manager.context.get("config") or GameConfig.load()
        self._cfg = cfg
        # Active level number: prefer the active player's current_level
        # (inited from cfg.starting_level by _handle_game_init); fall back
        # to cfg.starting_level for entry paths that bypass the state
        # machine (e.g. terrain-test).  Defaults to 1 if neither exists.
        players = manager.context.get("players") or []
        idx = manager.context.get("active_player_index", 0)
        if players and 0 <= idx < len(players):
            self._level_num: int = int(players[idx].current_level)
        else:
            self._level_num = int(cfg.starting_level)
        # Explicit [level_N] config if present, else procedural from the
        # difficulty curve (infinite levels).
        self._level_cfg: LevelSettings = cfg.level_settings_for(self._level_num)
        # Per-level terrain/layout seed: stable across a respawn (run_seed
        # + level_num both unchanged), random between games.
        run_seed = int(manager.context.get("run_seed", 0))
        self._level_seed: int = derive_seed(run_seed, self._level_num)
        self._held_keys: set[int] = set()
        self._min_camera_left: float = 0.0
        # Boss zone (set from the layout in on_show_view).
        self._boss_zone_x: float = 0.0
        self._boss_triggered: bool = False

        # Terrain (built in on_show_view once window dims are known).
        self._terrain: TerrainBase | None = None
        self._terrain_cfg: TerrainConfig | None = None

        # Ship + render list.
        mcfg = MomentumConfig(
            accel=cfg.ship.accel,
            friction=cfg.ship.friction,
            max_speed_x=cfg.ship.max_speed_x,
            max_speed_y=cfg.ship.max_speed_y,
        )
        self._ship = PlayerShip(mcfg, cfg.ship, cfg.combat, scale=cfg.sprite_scale)
        self._ship.load_scratch_textures()
        self._ship_list = arcade.SpriteList()
        self._ship_list.append(self._ship)
        self._scratch_list = arcade.SpriteList()
        if self._ship.scratch_sprite is not None:
            self._scratch_list.append(self._ship.scratch_sprite)

        # Towers (populated in on_show_view).
        self._tower_list = arcade.SpriteList()
        self._towers: list[FuelTower] = []

        # Enemies + projectiles (populated in on_show_view).
        self._silo_list = arcade.SpriteList()
        self._silos: list[MissileSilo] = []
        self._turret_base_list = arcade.SpriteList()
        self._turret_barrel_list = arcade.SpriteList()
        self._turrets: list[GunTurret] = []
        self._laser_base_list = arcade.SpriteList()
        self._laser_barrel_list = arcade.SpriteList()
        self._laser_turrets: list[LaserTurret] = []
        self._patrol_list = arcade.SpriteList()  # PatrolShip sprites
        self._patrols: list[PatrolShip] = []
        self._bullet_list = arcade.SpriteList()  # player bullets
        self._enemy_bullet_list = arcade.SpriteList()
        self._missile_list = arcade.SpriteList()
        # Boss (spawned on boss-zone entry).  Dedicated lists — NOT the
        # shared turret lists — so boss hardpoints are driven by the boss
        # and resolved by a dedicated collision pass.
        self._boss: BaseBoss | None = None
        self._boss_body_list = arcade.SpriteList()
        self._boss_gun_list = arcade.SpriteList()  # BossGun sprites (no base)
        self._boss_death_timer: float = 0.0
        self._boss_explosion_timer: float = 0.0

        # Combat state.  Score carries the player's running total across
        # levels and respawns (persisted in PlayerState.score).
        self._fire_cooldown: float = 0.0
        self._collision_frame: int = 0
        self._score: int = (
            int(players[idx].score) if players and 0 <= idx < len(players) else 0
        )
        # Autonomous patrol-ship spawn cadence.  Seeded short so the first
        # enemy appears soon after the level starts.
        self._patrol_spawn_timer: float = 2.0

        # Sound: one arcade.Sound + one SoundManager per effect type
        # (CLAUDE.md pattern).  Volume passed to play() as 0.0-1.0.
        self._snd_player_shoot = arcade.Sound(resource_path(_SND_PLAYER_SHOOT))
        self._snd_enemy_shoot = arcade.Sound(resource_path(_SND_ENEMY_SHOOT))
        self._snd_enemy_boom = arcade.Sound(resource_path(_SND_ENEMY_BOOM))
        self._snd_player_boom = arcade.Sound(resource_path(_SND_PLAYER_BOOM))
        # Missile launches reuse the enemy-shoot sample but throttle
        # independently so a flurry of missiles + turret shots don't
        # starve each other.
        self._snd_missile = self._snd_enemy_shoot
        self._sm_player_shoot = SoundManager(max_simultaneous=3)
        self._sm_enemy_shoot = SoundManager(max_simultaneous=3)
        self._sm_missile = SoundManager(max_simultaneous=2)
        self._sm_enemy_boom = SoundManager(max_simultaneous=4)
        self._sm_player_boom = SoundManager(max_simultaneous=2)
        # Positive-feedback chime played on level complete.
        self._snd_extra_life = arcade.Sound(resource_path(_SND_EXTRA_LIFE))
        self._sm_extra_life = SoundManager(max_simultaneous=1)

        # Explosion + death timer.
        self._explosion_list = arcade.SpriteList()
        self._death_timer: float = 0.0

        # Docking state.
        self._undock_requested: bool = False
        self._last_delta: float = 0.0
        self._dock_blink_timer: float = 0.0
        self._dock_blink_visible: bool = True
        self._dock_cooldown: float = 0.0

        # Pause state (Space Attackers pattern — view-local, no GameState).
        self._paused: bool = False
        self._pause_overlay_list = arcade.SpriteList()
        self._paused_text: arcade.Text | None = None

        # HUD (built lazily once window dims are known).
        self._hud_built: bool = False
        self._hud_fps: arcade.Text | None = None
        self._hud_world_x: arcade.Text | None = None
        self._hud_hp: arcade.Text | None = None
        self._hud_fuel_label: arcade.Text | None = None
        self._hud_docked: arcade.Text | None = None
        self._hud_score: arcade.Text | None = None
        self._hud_level: arcade.Text | None = None
        self._hud_effects: arcade.Text | None = None
        self._hud_boss_label: arcade.Text | None = None
        self._hud_powerup_flash: arcade.Text | None = None
        self._hud_god_mode: arcade.Text | None = None
        self._hud_debug_hints: arcade.Text | None = None
        # Lives rendered as ship-icon sprites (one fewer than the live
        # count — the active ship is the one you fly).  SpriteList drawn
        # in GUI-camera space; visibility toggled on change.
        self._hud_lives_list: arcade.SpriteList = arcade.SpriteList()
        self._hud_lives_icons: list[arcade.Sprite] = []
        # Cache sentinels — only rewrite Text/visibility when the value
        # actually changes (cache-on-change pattern).
        self._last_score: int = -1
        self._last_hp: int = -1
        self._last_fuel: float = -1.0
        self._last_lives: int = -1
        self._last_level: int = -1
        self._last_effects_str: str = ""

        # Power-ups.  Manager + spawner are built in on_show_view once
        # window dims are bound; texture registration is window-free so
        # it lives here.
        for et, path in _POWERUP_TEXTURES.items():
            PowerUpSprite.register(et, resource_path(path))
        self._powerup_spawner: WorldSpacePowerUpSpawner | None = None
        self._powerup_manager: BAPowerUpManager | None = None
        self._powerup_ctx: dict = {}
        self._powerup_flash_label: str = ""
        self._powerup_flash_timer: float = 0.0
        # Shield (OverlayEffect) — kept in a dedicated SpriteList so it
        # can render with SpriteList.draw().  _shield_sprite_ref caches
        # the current overlay sprite so we only touch the list when the
        # effect actually changes (collected / depleted / cleared).
        self._overlay_list: arcade.SpriteList = arcade.SpriteList()
        self._shield_sprite_ref: arcade.Sprite | None = None

    # ---- lifecycle -------------------------------------------------

    def on_show_view(self) -> None:
        if self._terrain is None:
            self._terrain, self._terrain_cfg = _build_terrain(
                self._cfg, self._level_cfg, self.window.width, self._level_seed
            )
            self._spawn_ship()
            self.window.world_camera.position = Vec2(
                self.window.width / 2.0, self.window.height / 2.0
            )
            self._terrain.update(0.0)
            layout = LevelGenerator(self._cfg).generate(
                level_num=self._level_num,
                world_width=self._terrain_cfg.world_width,
                ceiling_present=self._level_cfg.ceiling_present,
                run_seed=self._level_seed,
            )
            self._boss_zone_x = layout.boss_zone_x
            self._place_from_layout(layout)
            self._build_powerup_system()
            self._start_level_music()
        if not self._hud_built:
            self._build_hud()
            self._hud_built = True

    # ---- main loop -------------------------------------------------

    def on_update(self, delta_time: float) -> None:
        if self._terrain is None or self._terrain_cfg is None:
            return
        # Clamp pathologically long frames (e.g. window drag) to avoid
        # tunneling through terrain.
        delta_time = min(delta_time, 1 / 15)
        self._last_delta = delta_time

        # Pause freezes everything.  Run a gen-0 GC sweep each frame so
        # orphaned GL buffer objects from any leftover draw allocations
        # don't accumulate into a slow gen-2 collection when gameplay
        # resumes (Space Attackers pattern).
        if self._paused:
            gc.collect(0)
            return

        # Tick the post-undock dock-suspension cooldown.
        if self._dock_cooldown > 0.0:
            self._dock_cooldown = max(0.0, self._dock_cooldown - delta_time)
        # Tick the player fire cooldown.
        if self._fire_cooldown > 0.0:
            self._fire_cooldown = max(0.0, self._fire_cooldown - delta_time)

        # Death sequence — play out the explosion before transitioning.
        # PlayerKilledView owns the lives decrement + GAME_OVER/respawn
        # branch, so death always routes there.
        if self._death_timer > 0.0:
            self._death_timer -= delta_time
            self._explosion_list.update(delta_time)
            if self._death_timer <= 0.0:
                from src.base_attackers.state import GameState

                self._manager.transition(GameState.PLAYER_KILLED)
            return

        # Normal flight movement (skipped if docked or fuel-empty).
        self._update_ship(delta_time)

        # Fuel drain.
        self._ship.drain_fuel(delta_time)

        # Fuel-empty drift / gravity.  Routes to _destroy_ship on contact.
        if (
            self._ship.fuel_empty
            and not self._ship.is_docked
            and not self._cfg.god_mode
        ):
            self._apply_fuel_gravity(delta_time)
            if self._death_timer > 0.0:
                return  # collision fired mid-frame

        # Camera tracking + chunk loading.
        self._update_camera()
        cam_left = self.window.world_camera.position.x - self.window.width / 2.0
        self._terrain.update(cam_left)

        # Boss zone — single-fire when the ship reaches the reserved band.
        if (
            not self._boss_triggered
            and self._boss_zone_x > 0.0
            and self._ship.center_x >= self._boss_zone_x
        ):
            self._boss_triggered = True
            self._on_boss_zone_reached()
            return

        # Docking.
        self._check_docking()

        # Patrol ships (mobile enemies) — periodic spawn, then move/cull.
        # Auto-spawns pause while the boss fight is active (dock pressure
        # spawns are unaffected and still fire from _on_dock_pressure_spawn).
        self._patrol_spawn_timer -= delta_time
        if self._patrol_spawn_timer <= 0.0:
            self._patrol_spawn_timer = self._cfg.combat.patrol_spawn_interval
            if self._boss is None:
                self._spawn_patrol_ship()
        self._update_patrol_ships(delta_time)

        # Power-ups: spawn + pickup, then tick active effects (which
        # repositions any active overlay sprite via OverlayEffect.update).
        if self._powerup_spawner is not None:
            self._powerup_spawner.update(delta_time)
            self._check_powerup_pickup()
        if self._powerup_manager is not None:
            self._powerup_manager.update_effects(
                delta_time, self._ship, self._powerup_ctx
            )
        self._sync_overlay_list(delta_time)
        self._tick_powerup_flash(delta_time)

        # Combat updates.
        self._update_missiles(delta_time)
        self._update_turrets(delta_time)
        self._update_laser_turrets(delta_time)
        if self._death_timer > 0.0:
            return  # laser beam killed the player this frame
        boss_dying = self._boss_death_timer > 0.0
        self._update_boss(delta_time)
        if boss_dying:
            return  # death sequence (incl. its finishing frame) owns the update
        self._update_player_bullets(delta_time)
        self._check_combat_collisions()
        if self._death_timer > 0.0:
            # Player died mid-frame; let the death-timer guard pick up
            # next frame to play the explosion and transition.
            return

        # Ship-state-driven visuals.
        self._explosion_list.update(delta_time)
        self._ship.update_scratch_overlay()
        self._tick_dock_blink(delta_time)

        self._refresh_hud()

    def on_draw(self) -> None:
        self.clear()
        self.window.use_world_camera()
        # Power-up pickups render BEHIND terrain so they appear to fall
        # behind rocks / structures as they descend.
        if self._powerup_spawner is not None:
            self._powerup_spawner.sprite_list.draw()
        if self._terrain is not None:
            self._terrain.draw()
        self._tower_list.draw()
        self._patrol_list.draw()
        self._silo_list.draw()
        self._turret_base_list.draw()
        self._turret_barrel_list.draw()  # barrels above bases
        self._laser_base_list.draw()
        self._laser_barrel_list.draw()  # barrels above bases
        self._draw_laser_beams()  # immediate-mode lines, ephemeral
        self._missile_list.draw()
        self._enemy_bullet_list.draw()
        # Boss body + guns draw AFTER the enemy-bullet list (which holds the
        # boss bullets) so its shots emerge from under the body/guns.  Guns
        # draw above the body.
        self._boss_body_list.draw()
        self._boss_gun_list.draw()
        self._bullet_list.draw()  # player bullets above enemy bullets
        self._ship_list.draw()
        self._scratch_list.draw()
        # Shield overlay (or any other OverlayEffect): managed as a
        # SpriteList in _sync_overlay_list.  Belt-and-braces position
        # sync each frame so the shield never lags the ship.
        if self._shield_sprite_ref is not None:
            self._shield_sprite_ref.center_x = self._ship.center_x
            self._shield_sprite_ref.center_y = self._ship.center_y
        self._overlay_list.draw()
        self._explosion_list.draw()  # always on top

        self.window.use_gui_camera()
        self._draw_hud()

        # Pause overlay on top of everything.
        if self._paused:
            self._pause_overlay_list.draw()
            if self._paused_text is not None:
                self._paused_text.draw()

    # ---- input -----------------------------------------------------

    def on_key_press(self, key: int, modifiers: int) -> None:
        # P toggles pause.  Pauses music on entry, resumes on exit, and
        # runs a full GC sweep on entry so nothing accumulates during
        # the freeze (Space Attackers pattern).  Shift+P is reserved
        # for the debug power-up spawner — let it through.
        if key == arcade.key.P and not (modifiers & arcade.key.MOD_SHIFT):
            self._paused = not self._paused
            if self._paused:
                gc.collect()
                self.window.music.pause()
            else:
                self.window.music.resume()
            return
        # While paused, swallow all other keypresses.
        if self._paused:
            return
        # Debug-mode shortcuts (cfg.debug = true).  Placed before the
        # SPACE / _held_keys.add block so Shift-modified keys don't
        # bleed into the held-key set or fire a normal action.
        if self._cfg.debug and (modifiers & arcade.key.MOD_SHIFT):
            if key == arcade.key.G:
                self._toggle_god_mode()
                return
            if key == arcade.key.P:
                self._debug_spawn_powerup()
                return
            if key == arcade.key.E:
                self._debug_complete_level()
                return
            if key == arcade.key.K:
                self._destroy_ship()
                return
            if key == arcade.key.F:
                self._debug_refuel()
                return
        # SPACE: undock if docked, otherwise fire a player bullet.
        # The is_docked check is the gate — same key cannot do both.
        if key == arcade.key.SPACE:
            if self._ship.is_docked:
                self._undock_requested = True
            else:
                self._try_fire()
        self._held_keys.add(key)

    def on_key_release(self, key: int, modifiers: int) -> None:
        self._held_keys.discard(key)

    # ---- debug -----------------------------------------------------

    def _toggle_god_mode(self) -> None:
        """Flip cfg.god_mode in place.  HUD picks it up next frame."""
        self._cfg.god_mode = not self._cfg.god_mode

    def _debug_complete_level(self) -> None:
        """Shift+E — finish the level via the same path as the boss zone."""
        self._trigger_level_complete()

    def _debug_refuel(self) -> None:
        """Shift+F — top the fuel tank back up to capacity for playtesting."""
        self._ship.fuel = self._ship.fuel_capacity

    def _debug_spawn_powerup(self) -> None:
        """Drop one uniformly-random power-up into the visible window.

        Bypasses the spawner's per-level weight table so level 1 (empty
        table) can still be used for playtesting.  Reuses the spawner's
        private ``_spawn_sprite`` for sprite + parallel-list bookkeeping.
        """
        import random

        if self._powerup_spawner is None or self._terrain_cfg is None:
            return
        effect_type = random.choice(list(_POWERUP_TEXTURES))
        sw = self.window.width
        cx = self.window.world_camera.position.x
        cam_left = cx - sw / 2.0
        cam_right = cx + sw / 2.0
        # Spawn just under the HUD black bar — same band the auto-spawner
        # uses (see _build_powerup_system camera_rect clamp).
        world_h = float(self._terrain_cfg.world_height)
        spawn_x = random.uniform(cam_left + 32.0, cam_right - 32.0)
        spawn_y = random.uniform(world_h - 40.0, world_h - 8.0)
        self._powerup_spawner._spawn_sprite(effect_type, spawn_x, spawn_y)

    # ---- ship + camera --------------------------------------------

    def _update_ship(self, delta_time: float) -> None:
        # Skip entirely when control is disabled (docked or fuel-empty);
        # movement in those states is handled elsewhere.  God mode keeps
        # the ship steerable through fuel-empty so the fuel-death
        # consequence is fully neutralised (gauge still drains visibly).
        if self._ship.is_docked or (self._ship.fuel_empty and not self._cfg.god_mode):
            return

        # Read input.
        self._ship.input_x = 0.0
        self._ship.input_y = 0.0
        if arcade.key.RIGHT in self._held_keys or arcade.key.D in self._held_keys:
            self._ship.input_x = 1.0
        if arcade.key.LEFT in self._held_keys or arcade.key.A in self._held_keys:
            self._ship.input_x = -1.0
        if arcade.key.UP in self._held_keys or arcade.key.W in self._held_keys:
            self._ship.input_y = 1.0
        if arcade.key.DOWN in self._held_keys or arcade.key.S in self._held_keys:
            self._ship.input_y = -1.0

        dx, dy = self._ship.update_ship(delta_time)
        new_x = self._ship.center_x + dx
        new_y = self._ship.center_y + dy

        new_x, new_y = self._apply_position_bounds(new_x, new_y)

        # Terrain collision = destruction sequence.  God mode bypasses
        # the kill — the position-bound clamp above still keeps the
        # ship inside the window/world.
        assert self._terrain is not None
        if not self._cfg.god_mode and self._ship.collides_with_terrain(
            self._terrain, new_x, new_y
        ):
            self._on_terrain_collision()
            return

        self._ship.center_x = new_x
        self._ship.center_y = new_y

    def _apply_position_bounds(self, new_x: float, new_y: float) -> tuple[float, float]:
        """Clamp a tentative ship position into window/world bounds.

        Left:   ~1 chunk_width from the window's left edge.
        Right:  ~1 chunk_width from the world's right edge.
        Top:    world_height - ship.height/2 (keep below the HUD band).
        Bottom: ship.height/2 (keep the whole sprite on-screen).
        Zeroes the relevant velocity component on contact.
        """
        assert self._terrain_cfg is not None
        sw = self.window.width
        cam_left = self.window.world_camera.position.x - sw / 2.0
        cw = float(self._terrain_cfg.chunk_width)
        ship_left_bound = cam_left + cw
        ship_right_bound = self._terrain_cfg.world_width - cw
        if new_x < ship_left_bound:
            new_x = ship_left_bound
            self._ship.velocity_x = 0.0
        elif new_x > ship_right_bound:
            new_x = ship_right_bound
            self._ship.velocity_x = 0.0

        half_h = self._ship.height / 2.0
        ship_top_bound = self._terrain_cfg.world_height - half_h
        ship_bot_bound = half_h
        if new_y > ship_top_bound:
            new_y = ship_top_bound
            self._ship.velocity_y = 0.0
        elif new_y < ship_bot_bound:
            new_y = ship_bot_bound
            self._ship.velocity_y = 0.0
        return new_x, new_y

    def _apply_fuel_gravity(self, delta_time: float) -> None:
        """Fuel-empty drift: gravity downward, friction-damped X coast.

        Bypasses ``MomentumShipMixin.apply_momentum`` so the configured
        ``fuel_gravity`` isn't damped away each frame.  Terrain contact
        triggers the destruction sequence.
        """
        assert self._terrain is not None and self._terrain_cfg is not None
        self._ship.velocity_y -= self._cfg.ship.fuel_gravity * delta_time
        decay = self._cfg.ship.friction**delta_time
        self._ship.velocity_x *= decay

        new_x = self._ship.center_x + self._ship.velocity_x * delta_time
        new_y = self._ship.center_y + self._ship.velocity_y * delta_time
        new_x, new_y = self._apply_position_bounds(new_x, new_y)

        if not self._cfg.god_mode and self._ship.collides_with_terrain(
            self._terrain, new_x, new_y
        ):
            self._on_terrain_collision()
            return

        self._ship.center_x = new_x
        self._ship.center_y = new_y

    def _update_camera(self) -> None:
        sw = self.window.width
        sh = self.window.height
        cam_left = self.window.world_camera.position.x - sw / 2.0
        cam_bottom = self.window.world_camera.position.y - sh / 2.0

        ship_x = self._ship.center_x
        ship_y = self._ship.center_y

        # Horizontal deadzone — push right only.
        left_bound = cam_left + sw * _DEADZONE_LEFT
        right_bound = cam_left + sw * _DEADZONE_RIGHT
        if ship_x < left_bound:
            cam_left = ship_x - sw * _DEADZONE_LEFT
        elif ship_x > right_bound:
            cam_left = ship_x - sw * _DEADZONE_RIGHT
        # Monotonic clamp — camera X never decreases.
        cam_left = max(cam_left, self._min_camera_left)
        # Right-edge clamp — stop scrolling once the world's right edge
        # reaches the right edge of the window.
        assert self._terrain_cfg is not None
        cam_left = min(cam_left, max(0.0, self._terrain_cfg.world_width - sw))
        self._min_camera_left = cam_left

        # Vertical deadzone — free within world bounds.
        bottom_bound = cam_bottom + sh * _DEADZONE_BOTTOM
        top_bound = cam_bottom + sh * _DEADZONE_TOP
        if ship_y < bottom_bound:
            cam_bottom = ship_y - sh * _DEADZONE_BOTTOM
        elif ship_y > top_bound:
            cam_bottom = ship_y - sh * _DEADZONE_TOP
        world_h = self._terrain_cfg.world_height
        cam_bottom_max = max(0.0, world_h - sh)
        cam_bottom = max(0.0, min(cam_bottom, cam_bottom_max))

        self.window.world_camera.position = Vec2(
            cam_left + sw / 2.0,
            cam_bottom + sh / 2.0,
        )

    # ---- level flow ------------------------------------------------

    def _on_boss_zone_reached(self) -> None:
        """Spawn the boss when the ship reaches the boss zone.  The boss's
        death (``_finish_boss_death``) is what completes the level now.
        """
        log.info("Boss zone reached on level %d — spawning boss", self._level_num)
        self._spawn_boss()

    def _spawn_boss(self) -> None:
        """Construct + place the boss at the centre of the boss zone."""
        assert self._terrain is not None and self._terrain_cfg is not None
        cfg = self._cfg.combat
        boss_x = self._terrain_cfg.world_width * 0.92
        boss = BaseBoss(
            world_x=boss_x,
            level_num=self._level_num,
            cfg=cfg,
            sprite_scale=self._cfg.sprite_scale,
        )
        # Two-step: set Y once body.height is known.  The boss bobs slowly
        # within the vertical band between the floor and the ceiling (or the
        # world top when open).  Centre it in that band and clamp the bob
        # amplitude to whatever room is left after the body height; if the
        # band is too tight, it stays put (amplitude 0).
        floor_y = self._terrain.floor_y_at(boss_x)
        ceil_y = self._terrain.ceiling_y_at(boss_x)
        top_y = ceil_y if ceil_y is not None else float(self._terrain_cfg.world_height)
        half_h = boss.body.height / 2.0
        clearance = 16.0  # keep the body off the surfaces
        bottom_limit = floor_y + half_h + clearance
        top_limit = top_y - half_h - clearance
        band = top_limit - bottom_limit
        if band >= cfg.boss_oscillation_min_room:
            center_y = (bottom_limit + top_limit) / 2.0
            amplitude = min(cfg.boss_oscillation_amplitude, band / 2.0)
        else:
            # No room — fall back to the original stationary placement.
            center_y = (
                (floor_y + top_y) / 2.0
                if ceil_y is not None
                else floor_y + half_h + 20.0
            )
            amplitude = 0.0
        boss.place(center_y)
        boss.set_oscillation(amplitude, cfg.boss_oscillation_speed)

        self._boss_body_list.append(boss.body)
        for hp in boss.hardpoints:
            self._boss_gun_list.append(hp.sprite)
        self._boss = boss

    def _trigger_level_complete(self) -> None:
        """Persist score, then hand off to LevelCompleteView.

        The level increment lives in LevelCompleteView._on_complete — this
        is the ONLY path into GameState.LEVEL_COMPLETE; do not transition
        there directly from elsewhere.
        """
        from src.base_attackers.state import GameState

        self._sync_score_to_player()
        self._play_sfx(self._sm_extra_life, self._snd_extra_life)
        self._manager.transition(GameState.LEVEL_COMPLETE)

    def _sync_score_to_player(self) -> None:
        """Write the running score back into the active PlayerState so the
        LevelComplete / GameOver / ScoreEntry views read the right value.
        """
        players = self._manager.context.get("players") or []
        idx = self._manager.context.get("active_player_index", 0)
        if players and 0 <= idx < len(players):
            players[idx].score = self._score

    def _start_level_music(self) -> None:
        """Play this level's track (cycles agf's 6 bundled tracks).  No-op
        if already playing; stops the menu track automatically.
        """
        self.window.music.play(track_key_for_level(self._level_num))

    # ---- boss ------------------------------------------------------

    def _update_boss(self, delta_time: float) -> None:
        """Tick the boss: death sequence if dying, else fire hardpoints."""
        if self._boss is None:
            return

        # Death sequence — spawn scattered explosions, then finish.
        if self._boss_death_timer > 0.0:
            self._boss_death_timer -= delta_time
            self._boss_explosion_timer -= delta_time
            if self._boss_explosion_timer <= 0.0:
                self._boss_explosion_timer = (
                    self._cfg.combat.boss_death_explosion_interval
                )
                self._spawn_boss_death_explosion()
            self._explosion_list.update(delta_time)
            if self._boss_death_timer <= 0.0:
                self._finish_boss_death()
            return

        if not self._boss.is_alive:
            return

        # Normal update — hardpoints track + fire.
        for bullet in self._boss.update(
            self._ship.center_x, self._ship.center_y, delta_time
        ):
            self._enemy_bullet_list.append(bullet)
            self._play_sfx(self._sm_enemy_shoot, self._snd_enemy_shoot)

    def _start_boss_death(self) -> None:
        """Hide the boss + guns and begin the explosion sequence."""
        assert self._boss is not None
        self._boss.body.visible = False
        for hp in self._boss.hardpoints:
            hp.sprite.visible = False
        self._boss_death_timer = self._cfg.combat.boss_death_duration
        self._boss_explosion_timer = 0.0  # first explosion immediately

    def _spawn_boss_death_explosion(self) -> None:
        """One explosion at a random offset within the boss body."""
        import random

        assert self._boss is not None
        hw = self._boss.body.width / 2.0
        hh = self._boss.body.height / 2.0
        ex = self._boss.body.center_x + random.uniform(-hw * 0.8, hw * 0.8)
        ey = self._boss.body.center_y + random.uniform(-hh * 0.8, hh * 0.8)
        self._explosion_list.append(
            ExplosionSprite(x=ex, y=ey, scale=max(1.0, self._cfg.sprite_scale * 3.0))
        )
        self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)

    def _finish_boss_death(self) -> None:
        """Remove boss sprites, award score, and complete the level."""
        assert self._boss is not None
        self._boss.body.remove_from_sprite_lists()
        for hp in self._boss.hardpoints:
            hp.sprite.remove_from_sprite_lists()
        self._boss = None
        self._score += self._level_num * 500
        self._trigger_level_complete()

    def _on_hardpoint_destroyed(self, hardpoint: BossGun) -> None:
        """Explode + remove a destroyed boss gun (body survives)."""
        self._explosion_list.append(
            ExplosionSprite(
                x=hardpoint.center_x,
                y=hardpoint.center_y,
                scale=max(1.0, self._cfg.sprite_scale * 2.0),
            )
        )
        hardpoint.sprite.remove_from_sprite_lists()
        self._score += 150
        self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)

    def _on_terrain_collision(self) -> None:
        """Ship hit terrain — start the destruction sequence."""
        self._ship.hp = 0
        self._destroy_ship()

    def _destroy_ship(self) -> None:
        """Spawn an explosion, hide the ship, and start the death timer.

        ``on_update`` ticks ``_death_timer`` down and transitions to
        PLAYER_KILLED once it expires (that view decrements lives and
        routes to GAME_OVER or respawn).  Score is persisted here so the
        downstream views read the final value; lives are NOT touched here.
        """
        if self._death_timer > 0.0:
            return  # already dying
        self._sync_score_to_player()
        explosion = ExplosionSprite(
            x=self._ship.center_x,
            y=self._ship.center_y,
            scale=max(1.0, self._cfg.sprite_scale * 2.0),
        )
        self._explosion_list.append(explosion)
        self._ship.visible = False
        self._ship.is_docked = False
        self._ship.dock_tower = None
        if self._ship.scratch_sprite is not None:
            self._ship.scratch_sprite.visible = False
        if self._powerup_spawner is not None:
            self._powerup_spawner.clear()
        if self._powerup_manager is not None:
            self._powerup_manager.clear_all(self._ship, self._powerup_ctx)
            self._powerup_flash_label = ""
            self._powerup_flash_timer = 0.0
        self._overlay_list.clear()
        self._shield_sprite_ref = None
        self._death_timer = _DEATH_DURATION

    def _spawn_ship(self) -> None:
        assert self._terrain is not None and self._terrain_cfg is not None
        entry_x = float(self._terrain_cfg.chunk_width)
        entry_floor = self._terrain.floor_y_at(entry_x)
        entry_ceil = self._terrain.ceiling_y_at(entry_x)
        if entry_ceil is not None:
            spawn_y = (entry_floor + entry_ceil) / 2.0
        else:
            spawn_y = entry_floor + 200.0
        self._ship.center_x = 160.0
        self._ship.center_y = spawn_y
        self._min_camera_left = 0.0

    # ---- placement -------------------------------------------------

    def _place_from_layout(self, layout: "LevelLayout") -> None:
        """Construct all terrain-mounted objects from a procedural layout.

        Phase 8 boss spawns follow this same per-item-helper pattern.
        """
        for p in layout.towers:
            self._place_tower(p.x, p.surface)
        for p in layout.silos:
            self._place_silo(p.x, p.surface)
        for p in layout.turrets:
            self._place_turret(p.x, p.surface)
        for p in layout.lasers:
            self._place_laser(p.x, p.surface)

    def _place_tower(self, x: float, surface: str) -> None:
        """Two-step construct + position (texture height known after load)."""
        assert self._terrain is not None
        tower = FuelTower(
            world_x=x,
            world_y=0.0,
            surface=surface,
            cfg=self._cfg.fuel_tower,
            scale=1.0,
        )
        if surface == "floor":
            floor_y = self._terrain.floor_y_at(x)
            tower.center_y = floor_y + tower.height / 2.0
            tower.dock_y = tower.center_y + tower.height / 2.0 + 12.0
        else:
            ceil_y = self._terrain.ceiling_y_at(x)
            if ceil_y is None:
                return  # no ceiling at this x — skip
            tower.center_y = ceil_y - tower.height / 2.0
            tower.dock_y = tower.center_y - tower.height / 2.0 - 12.0
        self._tower_list.append(tower)
        self._towers.append(tower)

    def _place_silo(self, x: float, surface: str) -> None:
        assert self._terrain is not None
        silo = MissileSilo(
            world_x=x,
            surface=surface,
            cfg=self._cfg.combat,
            scale=self._cfg.sprite_scale,
        )
        if surface == "floor":
            silo.center_y = self._terrain.floor_y_at(x) + silo.height / 2.0
        else:
            ceil_y = self._terrain.ceiling_y_at(x)
            if ceil_y is None:
                return  # no ceiling at this x — skip
            silo.center_y = ceil_y - silo.height / 2.0
        self._silo_list.append(silo)
        self._silos.append(silo)

    def _place_turret(self, x: float, surface: str) -> None:
        assert self._terrain is not None
        if surface == "floor":
            surface_y: float | None = self._terrain.floor_y_at(x)
        else:
            surface_y = self._terrain.ceiling_y_at(x)
            if surface_y is None:
                return
        turret = GunTurret(
            world_x=x,
            surface=surface,
            cfg=self._cfg.combat,
            scale=self._cfg.sprite_scale,
        )
        turret.position_on_terrain(surface_y)
        self._turret_base_list.append(turret.base)
        self._turret_barrel_list.append(turret.barrel)
        self._turrets.append(turret)

    def _place_laser(self, x: float, surface: str) -> None:
        assert self._terrain is not None
        if surface == "floor":
            surface_y: float | None = self._terrain.floor_y_at(x)
        else:
            surface_y = self._terrain.ceiling_y_at(x)
            if surface_y is None:
                return
        lt = LaserTurret(
            world_x=x,
            surface=surface,
            cfg=self._cfg.combat,
            scale=self._cfg.sprite_scale,
        )
        lt.position_on_terrain(surface_y)
        self._laser_base_list.append(lt.base)
        self._laser_barrel_list.append(lt.barrel)
        self._laser_turrets.append(lt)

    # ---- docking ---------------------------------------------------

    def _check_docking(self) -> None:
        if self._ship.is_docked:
            self._handle_docked()
            return
        if self._ship.fuel_empty:
            return  # cannot dock during the death spiral
        if self._dock_cooldown > 0.0:
            return  # liftoff window — give the ship time to clear snap range
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
        self._ship.center_x = tower.center_x
        self._ship.center_y = tower.dock_y
        self._ship.velocity_x = 0.0
        self._ship.velocity_y = 0.0
        self._undock_requested = False
        # Reset the blink so "DOCKED" appears immediately on dock.
        self._dock_blink_timer = 0.0
        self._dock_blink_visible = True

    def _handle_docked(self) -> None:
        tower = self._ship.dock_tower
        if tower is None:
            self._ship.is_docked = False
            return

        # Transfer fuel from tower to ship.
        tower.update_transfer(self._ship, self._last_delta)

        # Undock conditions.
        if self._undock_requested or tower.is_depleted or not self._ship.is_alive:
            self._perform_undock(tower)
            return

        # Pressure tick — Phase 4 wires real enemies into this hook.
        if tower.update_pressure(self._last_delta):
            self._on_dock_pressure_spawn()

    def _perform_undock(self, tower: FuelTower) -> None:
        """Release the dock with a Y kick + dock-check cooldown.

        Without the kick, the ship sits at ``dock_y`` and `_check_docking`
        next frame finds the same tower well within ``snap_distance``,
        instantly re-snapping.  The cooldown is a belt-and-braces
        suspension while the liftoff velocity carries the ship clear.
        """
        self._ship.is_docked = False
        self._ship.dock_tower = None
        self._undock_requested = False
        # Direction: away from the tower.  Floor towers push the ship
        # up (+Y); ceiling towers push it down (-Y).
        direction = -1.0 if tower.surface == "ceiling" else 1.0
        self._ship.velocity_y = direction * _LIFTOFF_SPEED
        self._dock_cooldown = _DOCK_COOLDOWN

    def _on_dock_pressure_spawn(self) -> None:
        """Spawn a patrol ship from the right when the player lingers at a
        tower.  Phase 6 replacement for the Phase 4 enemy-bullet wave.
        """
        self._spawn_patrol_ship(behaviour=BEHAVIOUR_INTERCEPT)
        log.info("dock pressure: spawned intercept patrol ship")

    # ---- patrol ships ----------------------------------------------

    def _spawn_patrol_ship(self, behaviour: str | None = None) -> None:
        """Spawn one patrol ship off the right edge of the camera view.

        Y position is randomised within the visible corridor at the spawn
        X, clamped above floor_y and below ceiling_y (or world_height).
        """
        import random

        assert self._terrain is not None and self._terrain_cfg is not None

        cfg = self._cfg.combat
        sw = self.window.width
        spawn_x = (
            self.window.world_camera.position.x + sw / 2.0 + cfg.patrol_spawn_margin
        )

        if behaviour is None:
            behaviour = self._pick_patrol_behaviour()

        # Y: random position in the open corridor at spawn_x.
        floor_y = self._terrain.floor_y_at(spawn_x)
        ceil_y = self._terrain.ceiling_y_at(spawn_x)
        y_min = floor_y + 30.0
        y_max = (
            ceil_y - 30.0
            if ceil_y is not None
            else self._terrain_cfg.world_height - 30.0
        )
        if y_min >= y_max:
            y_min = floor_y + 10.0
            y_max = y_min + 40.0
        spawn_y = random.uniform(y_min, y_max)

        # Speed varies by behaviour.
        if behaviour == BEHAVIOUR_KAMIKAZE:
            speed = random.uniform(cfg.patrol_speed_max * 0.8, cfg.patrol_speed_max)
        elif behaviour == BEHAVIOUR_INTERCEPT:
            speed = random.uniform(
                cfg.patrol_speed_min * 1.2, cfg.patrol_speed_max * 0.8
            )
        else:
            speed = random.uniform(cfg.patrol_speed_min, cfg.patrol_speed_max * 0.6)

        ship = PatrolShip(
            world_x=spawn_x,
            world_y=spawn_y,
            behaviour=behaviour,
            speed=speed,
            cfg=cfg,
            scale=self._cfg.sprite_scale,
        )
        self._patrol_list.append(ship)
        self._patrols.append(ship)

    def _pick_patrol_behaviour(self) -> str:
        """Weight behaviours by level — higher levels get more kamikazes."""
        import random

        level = self._level_num
        weights = {
            BEHAVIOUR_STRAIGHT: max(1, 5 - level),
            BEHAVIOUR_INTERCEPT: 3,
            BEHAVIOUR_KAMIKAZE: min(5, level),
        }
        names = list(weights.keys())
        wts = list(weights.values())
        return random.choices(names, weights=wts, k=1)[0]

    def _update_patrol_ships(self, delta_time: float) -> None:
        """Steer + move each patrol ship; explode on terrain, fire, cull."""
        assert self._terrain is not None and self._terrain_cfg is not None
        cull = self._cfg.combat.bullet_cull_margin
        cam_left = self.window.world_camera.position.x - self.window.width / 2.0
        world_w = self._terrain_cfg.world_width
        world_h = self._terrain_cfg.world_height

        for ship in list(self._patrols):
            if not ship.is_alive:
                continue
            ship.update_patrol(
                self._ship.center_x, self._ship.center_y, delta_time, self._terrain
            )
            # Terrain contact destroys the patrol (no score — not a kill).
            if self._terrain.point_in_terrain(ship.center_x, ship.center_y):
                self._explode_patrol(ship)
                continue
            # Fire at the player (non-kamikaze only) while on screen.
            if self._is_on_screen(ship.center_x) and ship.try_fire():
                self._fire_patrol_bullet(ship)
            # Cull off-world.
            if (
                ship.center_x < cam_left - cull
                or ship.center_x > world_w + cull
                or ship.center_y < -cull
                or ship.center_y > world_h + cull
            ):
                ship.remove_from_sprite_lists()
                self._patrols.remove(ship)

    def _fire_patrol_bullet(self, ship: PatrolShip) -> None:
        """Spawn an enemy bullet: straight ships fire forward (left),
        intercept ships aim at the player's current position.
        """
        import math

        if ship.behaviour == BEHAVIOUR_INTERCEPT:
            dx = self._ship.center_x - ship.center_x
            dy = self._ship.center_y - ship.center_y
            angle = math.atan2(dy, dx)
        else:  # straight — fire forward, right-to-left
            angle = math.pi
        bullet = EnemyBullet(
            x=ship.center_x,
            y=ship.center_y,
            angle_rad=angle,
            speed=self._cfg.combat.enemy_bullet_speed,
            scale=self._cfg.sprite_scale,
            lifetime=self._cfg.combat.enemy_bullet_lifetime,
        )
        self._enemy_bullet_list.append(bullet)
        self._play_sfx(self._sm_enemy_shoot, self._snd_enemy_shoot)

    # ---- power-ups -------------------------------------------------

    def _build_powerup_system(self) -> None:
        """Construct the world-space spawner and effect manager."""
        assert self._terrain is not None
        sw = self.window.width
        sh = self.window.height
        # Power-up pickups render at native size (sprite_scale is for
        # ship + enemies only); the shield overlay is the exception —
        # it wraps the ship so it scales with ship_scale.
        self._powerup_manager = BAPowerUpManager(
            self._cfg.powerups,
            self._cfg.ship.fuel_canister_restore,
            sw,
            sh,
            ship_scale=self._cfg.sprite_scale,
        )
        self._powerup_ctx = {
            "window_width": sw,
            "window_height": sh,
            "sprite_scale": 1.0,
        }
        weight_table = self._cfg.powerups.weight_table_for_level(self._level_num)
        interval = self._cfg.powerups.spawn_interval_for_level(self._level_num)
        assert self._terrain_cfg is not None
        world_h = float(self._terrain_cfg.world_height)

        def camera_rect() -> tuple[float, float, float, float]:
            """Returns (cam_left, cam_bottom, cam_right, cam_top) — but
            ``cam_top`` is clamped to (world_height - 24) so the agf
            spawner places pickups at ``world_height - 8`` (just under
            the HUD black bar) instead of high above the camera.  Only
            ``cam_left`` is used for culling, so this clamp is safe.
            """
            cx = self.window.world_camera.position.x
            cy = self.window.world_camera.position.y
            cam_top_real = cy + sh / 2.0
            cam_top_clamped = min(cam_top_real, world_h - 24.0)
            return (
                cx - sw / 2.0,
                cy - sh / 2.0,
                cx + sw / 2.0,
                cam_top_clamped,
            )

        self._powerup_spawner = WorldSpacePowerUpSpawner(
            weight_table=weight_table,
            camera_rect=camera_rect,
            floor_y_at=self._terrain.floor_y_at,
            spawn_interval=interval,
            fall_speed_min=self._cfg.powerups.fall_speed_min,
            fall_speed_max=self._cfg.powerups.fall_speed_max,
            sprite_scale=1.0,
        )

    def _check_powerup_pickup(self) -> None:
        if self._powerup_spawner is None or self._powerup_manager is None:
            return
        hits = arcade.check_for_collision_with_list(
            self._ship, self._powerup_spawner.sprite_list
        )
        for sprite in hits:
            effect_type = self._powerup_spawner.collect(sprite)
            if effect_type is None:
                continue
            effect = self._powerup_manager.create_effect(effect_type)
            self._powerup_manager.apply_effect(effect, self._ship, self._powerup_ctx)
            self._on_powerup_collected(effect_type)

    def _on_powerup_collected(self, effect_type: str) -> None:
        self._play_sfx(self._sm_player_shoot, self._snd_player_shoot)
        self._powerup_flash_label = effect_type.replace("_", " ").upper()
        self._powerup_flash_timer = _POWERUP_FLASH_DURATION

    def _tick_powerup_flash(self, delta_time: float) -> None:
        if self._powerup_flash_timer > 0.0:
            self._powerup_flash_timer -= delta_time
            if self._powerup_flash_timer <= 0.0:
                self._powerup_flash_label = ""

    def _sync_overlay_list(self, delta_time: float) -> None:
        """Keep _overlay_list in lock-step with the active OverlayEffect.

        Adds the sprite on collection, removes it on expire/depletion,
        and ticks the shield alpha pulse each frame.  Cache-on-change so
        we don't churn the SpriteList every frame.
        """
        overlay = (
            self._powerup_manager.get_active_overlay()
            if self._powerup_manager is not None
            else None
        )
        new_ref = overlay.get_overlay_sprite() if overlay is not None else None
        if new_ref is not self._shield_sprite_ref:
            self._overlay_list.clear()
            if new_ref is not None:
                self._overlay_list.append(new_ref)
            self._shield_sprite_ref = new_ref
        if isinstance(self._shield_sprite_ref, ShieldSprite):
            self._shield_sprite_ref.pulse(delta_time)

    # ---- combat ----------------------------------------------------

    def _try_fire(self) -> None:
        """Fire a player bullet if control is enabled and cooldown has elapsed.

        Cooldown and damage live on PlayerShip so StatModifierEffect
        instances (rapid_fire, big_gun) can mutate them in place.  When
        a MultiShotEffect is active, the spread variant fires instead.
        """
        if not self._ship.control_enabled:
            return
        if self._fire_cooldown > 0.0:
            return
        if self._is_multi_shot_active():
            self._fire_multi_shot()
        else:
            self._fire_single_shot()
        self._fire_cooldown = self._ship.player_fire_cooldown
        self._play_sfx(self._sm_player_shoot, self._snd_player_shoot)

    def _is_multi_shot_active(self) -> bool:
        if self._powerup_manager is None:
            return False
        behavior = self._powerup_manager.get_active_behavior()
        return behavior is not None and behavior.effect_type == "multi_shot"

    def _fire_single_shot(self) -> None:
        bullet = PlayerBullet(
            x=self._ship.center_x + self._ship.width / 2.0,
            y=self._ship.center_y,
            speed=self._cfg.combat.player_bullet_speed,
            scale=self._cfg.sprite_scale,
        )
        self._bullet_list.append(bullet)

    def _fire_multi_shot(self) -> None:
        """Three bullets at -10°/0°/+10° from the ship nose."""
        import math

        speed = self._cfg.combat.player_bullet_speed
        x0 = self._ship.center_x + self._ship.width / 2.0
        y0 = self._ship.center_y
        for angle_deg in _MULTI_SHOT_SPREAD_DEG:
            rad = math.radians(angle_deg)
            self._bullet_list.append(
                PlayerBullet(
                    x=x0,
                    y=y0,
                    speed=speed * math.cos(rad),
                    scale=self._cfg.sprite_scale,
                    vy=speed * math.sin(rad),
                )
            )

    def _update_player_bullets(self, delta_time: float) -> None:
        """Move player bullets right; cull past world width or on terrain."""
        assert self._terrain is not None and self._terrain_cfg is not None
        cull = self._cfg.combat.bullet_cull_margin
        right_limit = self._terrain_cfg.world_width + cull
        for bullet in list(self._bullet_list):
            assert isinstance(bullet, PlayerBullet)
            bullet.update_bullet(delta_time)
            if bullet.center_x > right_limit or self._terrain.point_in_terrain(
                bullet.center_x, bullet.center_y
            ):
                bullet.remove_from_sprite_lists()

    def _is_on_screen(self, world_x: float) -> bool:
        """True if a world-X column is within the visible camera band.

        Stationary enemies only fire / activate while on screen, so the
        player never takes shots from turrets they can't see.  In-flight
        projectiles are unaffected — they move and cull independently.
        """
        sw = self.window.width
        cam_left = self.window.world_camera.position.x - sw / 2.0
        return cam_left <= world_x <= cam_left + sw

    def _update_missiles(self, delta_time: float) -> None:
        """Fire from proximity-triggered silos, then move + cull missiles."""
        assert self._terrain_cfg is not None
        cull = self._cfg.combat.bullet_cull_margin
        world_h = self._terrain_cfg.world_height

        for silo in self._silos:
            if not silo.is_alive:
                continue
            if not self._is_on_screen(silo.center_x):
                continue
            if silo.check_proximity(self._ship.center_x, self._ship.center_y):
                direction = -1.0 if silo.surface == "ceiling" else 1.0
                missile = Missile(
                    x=silo.center_x,
                    y=silo.center_y + (silo.height / 2.0) * direction,
                    speed=self._cfg.combat.missile_speed,
                    direction=direction,
                    scale=self._cfg.sprite_scale,
                )
                self._missile_list.append(missile)
                self._play_sfx(self._sm_missile, self._snd_missile)

        assert self._terrain is not None
        for missile in list(self._missile_list):
            assert isinstance(missile, Missile)
            missile.update_missile(delta_time)
            off_world = missile.center_y > world_h + cull or missile.center_y < -cull
            hit_terrain = self._terrain.point_in_terrain(
                missile.center_x, missile.center_y
            )
            if off_world or hit_terrain:
                # Re-arm the closest owning silo (X-coordinate match) so it
                # can fire again now this missile is gone.
                for silo in self._silos:
                    if (
                        not silo._fire_ready
                        and abs(silo.center_x - missile.center_x) < 10.0
                    ):
                        silo.reset_fire()
                        break
                missile.remove_from_sprite_lists()

    def _update_turrets(self, delta_time: float) -> None:
        """Rotate barrels, fire bullets, then move + cull enemy bullets."""
        assert self._terrain_cfg is not None
        cull = self._cfg.combat.bullet_cull_margin
        world_w = self._terrain_cfg.world_width
        world_h = self._terrain_cfg.world_height

        for turret in self._turrets:
            if not turret.is_alive:
                continue
            if not self._is_on_screen(turret.base.center_x):
                continue
            if turret.update(self._ship.center_x, self._ship.center_y, delta_time):
                bullet = turret.fire_bullet(
                    self._cfg.combat.enemy_bullet_speed,
                    self._cfg.sprite_scale,
                )
                self._enemy_bullet_list.append(bullet)
                self._play_sfx(self._sm_enemy_shoot, self._snd_enemy_shoot)

        assert self._terrain is not None
        # Camera viewport bounds — boss bullets cull on leaving the visible
        # view rather than expiring on a timer (see below).
        sw = self.window.width
        sh = self.window.height
        cam_left = self.window.world_camera.position.x - sw / 2.0
        cam_bottom = self.window.world_camera.position.y - sh / 2.0
        cam_right = cam_left + sw
        cam_top = cam_bottom + sh
        for bullet in list(self._enemy_bullet_list):
            assert isinstance(bullet, EnemyBullet)
            bullet.update_bullet(delta_time)
            in_terrain = self._terrain.point_in_terrain(
                bullet.center_x, bullet.center_y
            )
            if isinstance(bullet, BossBullet):
                # Boss bullets are NOT time-limited: the boss sits at the end
                # of the level, so its shots persist until they leave the
                # visible view (or hit terrain).  This stops the player from
                # simply backing out of range and waiting them out.
                if (
                    in_terrain
                    or bullet.center_x < cam_left - cull
                    or bullet.center_x > cam_right + cull
                    or bullet.center_y < cam_bottom - cull
                    or bullet.center_y > cam_top + cull
                ):
                    bullet.remove_from_sprite_lists()
            elif (
                bullet.expired
                or bullet.center_x < -cull
                or bullet.center_x > world_w + cull
                or bullet.center_y < -cull
                or bullet.center_y > world_h + cull
                or in_terrain
            ):
                bullet.remove_from_sprite_lists()

    def _update_laser_turrets(self, delta_time: float) -> None:
        """Tick each laser turret; apply beam damage on the FIRING frame."""
        for lt in self._laser_turrets:
            if not lt.is_alive:
                continue
            if not self._is_on_screen(lt.base.center_x):
                continue
            state = lt.update(self._ship.center_x, self._ship.center_y, delta_time)
            # Apply damage on the first frame of the FIRING state.
            if state == "firing" and not lt._damage_dealt:
                lt._damage_dealt = True
                if self._ship_in_laser_beam(lt):
                    self._damage_player(self._cfg.combat.laser_beam_damage)
                    if self._death_timer > 0.0:
                        return

    def _ship_in_laser_beam(self, lt: LaserTurret) -> bool:
        """True if the ship center is within beam_width/2 of the laser line."""
        import math

        x0, y0 = lt.barrel.center_x, lt.barrel.center_y
        x1, y1 = lt.beam_end()
        px, py = self._ship.center_x, self._ship.center_y
        # Perpendicular distance from point to line segment.
        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return False
        t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length_sq))
        closest_x = x0 + t * dx
        closest_y = y0 + t * dy
        dist = math.hypot(px - closest_x, py - closest_y)
        half_w = (self._cfg.combat.laser_beam_width / 2.0) + self._ship.width / 4.0
        return dist <= half_w

    def _draw_laser_beams(self) -> None:
        """Immediate-mode beam lines in world-camera space (ephemeral)."""
        cfg = self._cfg.combat
        for lt in self._laser_turrets:
            if not lt.is_alive:
                continue
            if not self._is_on_screen(lt.base.center_x):
                continue
            if lt.is_telegraphing:
                color = tuple(cfg.laser_telegraph_color)
                width = max(1, int(cfg.laser_beam_width * 0.5))
            elif lt.is_firing:
                color = tuple(cfg.laser_beam_color)
                width = int(cfg.laser_beam_width)
            else:
                continue
            end_x, end_y = lt.beam_end()
            arcade.draw_line(
                lt.barrel.center_x,
                lt.barrel.center_y,
                end_x,
                end_y,
                color,
                width,
            )

    def _check_combat_collisions(self) -> None:
        """Frame-staggered collision detection.

        Player bullets vs enemies: every frame (must feel responsive).
        Enemy projectiles vs player: every other frame (CLAUDE.md guidance).
        """
        self._check_player_bullet_hits()
        if self._collision_frame % 2 == 0:
            self._check_enemy_hits()
        self._collision_frame += 1

    def _check_player_bullet_hits(self) -> None:
        damage = self._ship.player_bullet_damage
        for bullet in list(self._bullet_list):
            hits = arcade.check_for_collision_with_list(bullet, self._silo_list)
            if hits:
                bullet.remove_from_sprite_lists()
                silo = hits[0]
                assert isinstance(silo, MissileSilo)
                if silo.take_damage(damage):
                    self._on_enemy_destroyed(silo)
                continue
            base_hits = arcade.check_for_collision_with_list(
                bullet, self._turret_base_list
            )
            if base_hits:
                bullet.remove_from_sprite_lists()
                base_sprite = base_hits[0]
                turret = next((t for t in self._turrets if t.base is base_sprite), None)
                if turret is not None and turret.take_damage(damage):
                    self._on_turret_destroyed(turret)

        # vs patrol ships
        for bullet in list(self._bullet_list):
            if not bullet.sprite_lists:
                continue
            hits = arcade.check_for_collision_with_list(bullet, self._patrol_list)
            if hits:
                bullet.remove_from_sprite_lists()
                patrol = hits[0]
                assert isinstance(patrol, PatrolShip)
                if patrol.take_damage(damage):
                    self._on_patrol_destroyed(patrol)

        # vs laser turret bases
        for bullet in list(self._bullet_list):
            if not bullet.sprite_lists:
                continue
            hits = arcade.check_for_collision_with_list(bullet, self._laser_base_list)
            if hits:
                bullet.remove_from_sprite_lists()
                base_sprite = hits[0]
                lt = next(
                    (t for t in self._laser_turrets if t.base is base_sprite), None
                )
                if lt is not None and lt.take_damage(damage):
                    self._on_laser_turret_destroyed(lt)

        # vs boss — guns first (so a shot over both hits the gun), then the
        # body.  Skipped during the death sequence.
        if self._boss is None or self._boss_death_timer > 0.0:
            return
        for bullet in list(self._bullet_list):
            if not bullet.sprite_lists:
                continue
            hits = arcade.check_for_collision_with_list(bullet, self._boss_gun_list)
            if hits:
                bullet.remove_from_sprite_lists()
                gun_sprite = hits[0]
                hp = next(
                    (h for h in self._boss.hardpoints if h.sprite is gun_sprite), None
                )
                if hp is not None and hp.take_damage(damage):
                    self._on_hardpoint_destroyed(hp)
        if not self._boss.is_alive:
            return
        for bullet in list(self._bullet_list):
            if not bullet.sprite_lists:
                continue
            hits = arcade.check_for_collision_with_list(bullet, self._boss_body_list)
            if hits:
                bullet.remove_from_sprite_lists()
                if self._boss.take_damage(damage):
                    self._start_boss_death()
                    return

    def _check_enemy_hits(self) -> None:
        if not self._ship.is_alive or self._ship.is_docked:
            # While docked the brief still allows damage in theory, but
            # the dock pos sits well above terrain so bullets/missiles
            # rarely land — keep the gate simple for now.
            pass
        missile_hits = arcade.check_for_collision_with_list(
            self._ship, self._missile_list
        )
        for missile in missile_hits:
            missile.remove_from_sprite_lists()
            self._damage_player(1)
            if self._death_timer > 0.0:
                return
        bullet_hits = arcade.check_for_collision_with_list(
            self._ship, self._enemy_bullet_list
        )
        for bullet in bullet_hits:
            bullet.remove_from_sprite_lists()
            self._damage_player(1)
            if self._death_timer > 0.0:
                return
        # Patrol ship ram — destroys the patrol, damages the player.
        patrol_hits = arcade.check_for_collision_with_list(
            self._ship, self._patrol_list
        )
        for patrol in patrol_hits:
            assert isinstance(patrol, PatrolShip)
            patrol.remove_from_sprite_lists()
            if patrol in self._patrols:
                self._patrols.remove(patrol)
            self._damage_player(self._cfg.combat.patrol_ram_damage)
            if self._death_timer > 0.0:
                return
        # Boss body contact — flying into the boss costs HP (no instakill;
        # the every-other-frame cadence keeps it survivable).
        if (
            self._boss is not None
            and self._boss.is_alive
            and self._boss_death_timer <= 0.0
            and arcade.check_for_collision_with_list(self._ship, self._boss_body_list)
        ):
            self._damage_player(1)
            if self._death_timer > 0.0:
                return

    def _damage_player(self, amount: int) -> None:
        """Single gate for all enemy-side damage.

        Respects ``god_mode``, lets an active ShieldEffect absorb the
        hit first, and routes 0-HP into the destruction sequence (which
        has its own double-trigger guard).
        """
        if self._cfg.god_mode:
            return
        if self._powerup_manager is not None:
            overlay = self._powerup_manager.get_active_overlay()
            if overlay is not None and overlay.effect_type == "shield":
                depleted = overlay.on_hit_absorbed()
                if depleted:
                    self._powerup_manager.remove_effect(
                        overlay, self._ship, self._powerup_ctx
                    )
                return  # hit absorbed by shield
        if self._ship.take_damage(amount):
            self._destroy_ship()
            self._play_sfx(self._sm_player_boom, self._snd_player_boom)

    def _on_enemy_destroyed(self, silo: MissileSilo) -> None:
        explosion = ExplosionSprite(
            x=silo.center_x,
            y=silo.center_y,
            scale=max(1.0, self._cfg.sprite_scale * 2.0),
        )
        self._explosion_list.append(explosion)
        silo.remove_from_sprite_lists()
        self._score += 100
        self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)

    def _on_turret_destroyed(self, turret: GunTurret) -> None:
        explosion = ExplosionSprite(
            x=turret.base.center_x,
            y=turret.base.center_y,
            scale=max(1.0, self._cfg.sprite_scale * 2.0),
        )
        self._explosion_list.append(explosion)
        turret.base.remove_from_sprite_lists()
        turret.barrel.remove_from_sprite_lists()
        self._score += 150
        self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)

    def _explode_patrol(self, patrol: PatrolShip) -> None:
        """Spawn the explosion + remove the patrol (no score).  Shared by
        player-kill and terrain-contact paths.
        """
        explosion = ExplosionSprite(
            x=patrol.center_x,
            y=patrol.center_y,
            scale=max(1.0, self._cfg.sprite_scale * 2.0),
        )
        self._explosion_list.append(explosion)
        patrol.remove_from_sprite_lists()
        if patrol in self._patrols:
            self._patrols.remove(patrol)
        self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)

    def _on_patrol_destroyed(self, patrol: PatrolShip) -> None:
        """Player destroyed the patrol — explode and award score."""
        self._explode_patrol(patrol)
        self._score += 200

    def _on_laser_turret_destroyed(self, lt: LaserTurret) -> None:
        explosion = ExplosionSprite(
            x=lt.base.center_x,
            y=lt.base.center_y,
            scale=max(1.0, self._cfg.sprite_scale * 2.0),
        )
        self._explosion_list.append(explosion)
        lt.base.remove_from_sprite_lists()
        lt.barrel.remove_from_sprite_lists()
        self._score += 250
        self._play_sfx(self._sm_enemy_boom, self._snd_enemy_boom)

    def _play_sfx(self, sm: SoundManager, sound: arcade.Sound) -> None:
        """Volume conversion in one place — effects_volume is 0-100."""
        sm.play(sound, volume=self._cfg.effects_volume / 100.0)

    # ---- dock indicator -------------------------------------------

    def _tick_dock_blink(self, delta_time: float) -> None:
        if not self._ship.is_docked:
            self._dock_blink_visible = False
            self._dock_blink_timer = 0.0
            return
        self._dock_blink_timer += delta_time
        if self._dock_blink_timer >= _DOCK_BLINK_PERIOD:
            self._dock_blink_timer = 0.0
            self._dock_blink_visible = not self._dock_blink_visible

    # ---- HUD -------------------------------------------------------

    def _build_hud(self) -> None:
        sw = self.window.width
        sh = self.window.height
        common = dict(font_name=FONT_THIN, font_size=14, color=arcade.color.WHITE)

        # Row 1 — SCORE (left), LEVEL (centre), lives icons (right).
        self._hud_score = arcade.Text("SCORE  000000", 12, sh - _ROW1_Y, **common)
        self._hud_level = arcade.Text(
            "LEVEL  1",
            sw / 2,
            sh - _ROW1_Y,
            font_name=FONT_THIN,
            font_size=14,
            color=arcade.color.WHITE,
            anchor_x="center",
        )
        self._hud_docked = arcade.Text(
            "DOCKED",
            260,
            sh - _ROW1_Y,
            font_name=FONT_THIN,
            font_size=14,
            color=arcade.color.YELLOW,
        )
        # Lives icons — up to _LIVES_ICON_MAX ship sprites anchored to the
        # right edge, one fewer than the live count is shown each refresh.
        self._hud_lives_list = arcade.SpriteList()
        self._hud_lives_icons = []
        icon_tex = arcade.load_texture(resource_path(_LIVES_ICON_PATH))
        for i in range(_LIVES_ICON_MAX):
            icon = arcade.Sprite(icon_tex, scale=_LIVES_ICON_SCALE)
            icon.center_y = sh - _ROW1_Y + 4.0
            icon.center_x = sw - 18.0 - i * (icon.width + 4.0)
            icon.visible = False
            self._hud_lives_list.append(icon)
            self._hud_lives_icons.append(icon)

        # Rows 3/4 — HP / FUEL text labels (bars drawn beside them).
        self._hud_hp = arcade.Text("HP --", 12, sh - _ROW3_Y, **common)
        self._hud_fuel_label = arcade.Text("FUEL --", 12, sh - _ROW4_Y, **common)

        # Row 2 — "BOSS" label at the left end of the centred boss health
        # bar, plus the active power-up effects line (left-aligned so it
        # clears the centred boss bar).
        self._hud_boss_label = arcade.Text(
            "BOSS",
            sw * 0.25 - 50.0,
            sh - _ROW2_Y,
            arcade.color.RED,
            font_size=12,
            font_name=FONT_THIN,
            anchor_y="bottom",
        )
        self._hud_effects = arcade.Text(
            "",
            12,
            sh - _ROW2_Y,
            _EFFECTS_COLOR,
            font_size=12,
            font_name=FONT_THIN,
        )

        self._hud_powerup_flash = arcade.Text(
            "",
            sw / 2,
            sh / 2 + 60,
            arcade.color.YELLOW,
            font_size=22,
            font_name=FONT_THIN,
            anchor_x="center",
            anchor_y="center",
        )

        # Debug HUD: FPS / world-X / hints and a "GOD MODE" tag — drawn
        # only when cfg.debug / cfg.god_mode.  Parked on the right of the
        # band (FPS/X) and centre row 2 (hints) so the production HUD
        # stays clean when they are gated off.
        self._hud_fps = arcade.Text(
            "FPS: --",
            sw - 180.0,
            sh - _ROW3_Y,
            (160, 160, 160),
            11,
            font_name=FONT_THIN,
        )
        self._hud_world_x = arcade.Text(
            "X: 0", sw - 180.0, sh - _ROW4_Y, (160, 160, 160), 11, font_name=FONT_THIN
        )
        self._hud_god_mode = arcade.Text(
            "GOD MODE",
            sw / 2,
            sh - _ROW3_Y,
            arcade.color.YELLOW,
            font_size=14,
            font_name=FONT_THIN,
            anchor_x="center",
        )
        self._hud_debug_hints = arcade.Text(
            "DEBUG  Shift+G god  Shift+P p-up  Shift+E level+  Shift+K kill  Shift+F fuel",
            sw / 2,
            sh - _ROW2_Y,
            (180, 180, 180),
            font_size=11,
            font_name=FONT_THIN,
            anchor_x="center",
        )

        # Pre-bake the pause dim overlay as a sprite so on_draw never has
        # to call immediate-mode draw functions for it (which orphan a
        # GPU buffer every frame).
        overlay = arcade.SpriteSolidColor(
            sw,
            sh,
            center_x=sw / 2,
            center_y=sh / 2,
            color=(0, 0, 0, 120),
        )
        self._pause_overlay_list.clear()
        self._pause_overlay_list.append(overlay)
        self._paused_text = arcade.Text(
            "PAUSED",
            sw / 2,
            sh / 2,
            arcade.color.WHITE,
            font_size=48,
            font_name=FONT_THIN,
            anchor_x="center",
            anchor_y="center",
        )

    def _refresh_hud(self) -> None:
        if self._hud_score is None:
            return

        # Score (zero-padded to 6 digits).
        if self._score != self._last_score:
            self._hud_score.text = f"SCORE  {self._score:06d}"
            self._last_score = self._score

        # Level.
        if self._level_num != self._last_level and self._hud_level is not None:
            self._hud_level.text = f"LEVEL  {self._level_num}"
            self._last_level = self._level_num

        # HP / FUEL labels (bars are drawn separately each frame).
        if self._ship.hp != self._last_hp and self._hud_hp is not None:
            self._hud_hp.text = f"HP {self._ship.hp} / {self._ship.MAX_HP}"
            self._last_hp = self._ship.hp
        fuel_int = int(self._ship.fuel)
        if fuel_int != self._last_fuel and self._hud_fuel_label is not None:
            self._hud_fuel_label.text = f"FUEL {fuel_int}"
            self._last_fuel = fuel_int

        # Lives icons — one fewer than the live count (the active ship is
        # the one in play).
        players = self._manager.context.get("players") or []
        idx = self._manager.context.get("active_player_index", 0)
        lives = players[idx].lives if players and 0 <= idx < len(players) else 0
        if lives != self._last_lives:
            self._last_lives = lives
            for i, icon in enumerate(self._hud_lives_icons):
                icon.visible = i < (lives - 1)

        # Active power-up effects line.
        effects_str = self._build_effects_str()
        if effects_str != self._last_effects_str and self._hud_effects is not None:
            self._hud_effects.text = effects_str
            self._last_effects_str = effects_str

        # Power-up flash text.
        if self._hud_powerup_flash is not None:
            self._hud_powerup_flash.text = self._powerup_flash_label

        # Debug-only readouts.
        if self._cfg.debug and self._hud_fps is not None:
            self._hud_fps.text = f"FPS: {arcade.get_fps():.0f}"
            self._hud_world_x.text = f"X: {self._ship.center_x:.0f}"

    def _build_effects_str(self) -> str:
        """Summarise active timed power-up effects for the HUD effects line.

        Iterates ``PowerUpManager.get_active_effects()`` (the public getter
        — there is no ``active_effects`` property).  Only StatModifierEffect
        subclasses expose ``display_label``; behaviour/overlay effects fall
        back to a title-cased ``effect_type``.
        """
        if self._powerup_manager is None:
            return ""
        parts = []
        for effect in self._powerup_manager.get_active_effects():
            label = (
                getattr(effect, "display_label", "")
                or effect.effect_type.replace("_", " ").upper()
            )
            dur = getattr(effect, "remaining_duration", 0.0)
            parts.append(f"[{label} {dur:.1f}s]" if dur > 0.0 else f"[{label}]")
        return "  ".join(parts)

    def _draw_hud(self) -> None:
        assert self._terrain_cfg is not None
        sw = self.window.width
        sh = self.window.height
        cam_bottom = self.window.world_camera.position.y - sh / 2.0
        # Screen-Y at which the world ceiling sits — everything above is
        # the HUD area and is masked solid black so the tile renderer's
        # ceiling overstack stays hidden.  Clamp to a fixed band so tall
        # levels (world_height > window height) still back the HUD and
        # never feed bottom > top into draw_lrbt_rectangle_filled.
        hud_bottom = float(self._terrain_cfg.world_height) - cam_bottom
        hud_bottom = max(0.0, min(hud_bottom, float(sh) - _HUD_BAND_HEIGHT))
        arcade.draw_lrbt_rectangle_filled(
            0.0, float(sw), hud_bottom, float(sh), arcade.color.BLACK
        )

        # HP bar on the HP-text row (sh - 60).
        self._draw_bar(
            _HP_BAR_X,
            _HP_BAR_W,
            sh - 60 + 2.0,
            self._ship.hp / self._ship.MAX_HP if self._ship.MAX_HP else 0.0,
            _HP_COLOR,
        )

        # FUEL bar on the FUEL-text row (sh - 80).
        fuel_frac = (
            self._ship.fuel / self._ship.fuel_capacity
            if self._ship.fuel_capacity
            else 0.0
        )
        fuel_color = _FUEL_COLOR_LOW if fuel_frac < _FUEL_LOW_FRAC else _FUEL_COLOR
        self._draw_bar(
            _FUEL_BAR_X,
            _FUEL_BAR_W,
            sh - 80 + 2.0,
            fuel_frac,
            fuel_color,
        )

        # TOWER bar — only while docked, sits next to the fuel bar.
        if self._ship.is_docked and self._ship.dock_tower is not None:
            tower = self._ship.dock_tower
            t_frac = (
                tower.fuel_remaining / tower.cfg.tower_capacity
                if tower.cfg.tower_capacity
                else 0.0
            )
            self._draw_bar(
                _TOWER_BAR_X,
                _TOWER_BAR_W,
                sh - 80 + 2.0,
                t_frac,
                _TOWER_COLOR,
            )

        # HUD text — always-on production elements.
        if self._hud_hp:
            self._hud_hp.draw()
        if self._hud_fuel_label:
            self._hud_fuel_label.draw()
        if self._hud_score:
            self._hud_score.draw()
        if self._hud_level:
            self._hud_level.draw()
        self._hud_lives_list.draw()
        if self._hud_effects and self._last_effects_str:
            self._hud_effects.draw()
        if self._hud_docked and self._ship.is_docked and self._dock_blink_visible:
            self._hud_docked.draw()
        if self._hud_powerup_flash and self._powerup_flash_label:
            self._hud_powerup_flash.draw()

        # Debug-only HUD — gated so the production build stays clean.
        if self._cfg.debug:
            if self._hud_fps:
                self._hud_fps.draw()
            if self._hud_world_x:
                self._hud_world_x.draw()
            if self._hud_debug_hints is not None:
                self._hud_debug_hints.draw()
        if self._cfg.god_mode and self._hud_god_mode is not None:
            self._hud_god_mode.draw()

        self._draw_boss_health_bar()
        self._draw_radar()

    def _draw_boss_health_bar(self) -> None:
        """Wide centred boss health bar, only while the boss is alive."""
        if self._boss is None or not self._boss.is_alive:
            return
        sw = self.window.width
        sh = self.window.height
        bar_w = sw * 0.5
        bar_h = 14.0
        bar_x = (sw - bar_w) / 2.0
        bar_y = sh - 44.0
        frac = self._boss.hp_fraction
        arcade.draw_lrbt_rectangle_filled(
            bar_x, bar_x + bar_w, bar_y, bar_y + bar_h, (60, 60, 60, 200)
        )
        if frac > 0.0:
            color = (255, 100, 30) if frac < 0.3 else (220, 40, 40)
            arcade.draw_lrbt_rectangle_filled(
                bar_x, bar_x + bar_w * frac, bar_y, bar_y + bar_h, color
            )
        if self._hud_boss_label is not None:
            self._hud_boss_label.draw()

    def _draw_bar(
        self,
        x: float,
        width: float,
        y_bottom: float,
        fraction: float,
        color: tuple,
    ) -> None:
        fraction = max(0.0, min(1.0, fraction))
        y_top = y_bottom + _BAR_HEIGHT
        # Background.
        arcade.draw_lrbt_rectangle_filled(x, x + width, y_bottom, y_top, _BAR_BG_COLOR)
        # Foreground.
        if fraction > 0.0:
            arcade.draw_lrbt_rectangle_filled(
                x, x + width * fraction, y_bottom, y_top, color
            )

    def _draw_radar(self) -> None:
        """Defender-style radar strip at the bottom of the screen.

        Drawn entirely in gui_camera space with immediate-mode calls — no
        sprites, no ShapeElementList.  The radar maps world_x -> radar_x
        linearly; world_y is ignored (everything appears on a single
        horizontal strip).
        """
        if self._terrain_cfg is None:
            return

        sw = float(self.window.width)
        ww = float(self._terrain_cfg.world_width)
        if ww <= 0.0:
            return

        # Radar strip geometry (screen space).
        rx = _RADAR_MARGIN_X
        ry = _RADAR_MARGIN_BOT
        rw = sw - 2 * _RADAR_MARGIN_X
        rh = _RADAR_HEIGHT

        def to_rx(world_x: float) -> float:
            """Map a world X coordinate to a radar X pixel."""
            return rx + (world_x / ww) * rw

        # Background + border.
        arcade.draw_lrbt_rectangle_filled(rx, rx + rw, ry, ry + rh, _RADAR_BG_COLOR)
        arcade.draw_lrbt_rectangle_outline(
            rx, rx + rw, ry, ry + rh, _RADAR_BORDER_COLOR, 1
        )

        # Camera viewport tint — shows what fraction of the world is visible.
        cam_left = self.window.world_camera.position.x - sw / 2.0
        cam_right = cam_left + sw
        vx0 = max(rx, to_rx(cam_left))
        vx1 = min(rx + rw, to_rx(cam_right))
        if vx1 > vx0:
            arcade.draw_lrbt_rectangle_filled(vx0, vx1, ry, ry + rh, _RADAR_CAM_COLOR)

        mid_y = ry + rh / 2.0

        # Fuel towers — cyan dots.
        for tower in self._towers:
            arcade.draw_circle_filled(
                to_rx(tower.center_x), mid_y, _RADAR_DOT_R, _RADAR_TOWER_COLOR
            )

        # Stationary enemies — red dots.
        for silo in self._silos:
            if silo.is_alive:
                arcade.draw_circle_filled(
                    to_rx(silo.center_x), mid_y, _RADAR_DOT_R, _RADAR_ENEMY_COLOR
                )
        for turret in self._turrets:
            if turret.is_alive:
                arcade.draw_circle_filled(
                    to_rx(turret.base.center_x), mid_y, _RADAR_DOT_R, _RADAR_ENEMY_COLOR
                )
        for lt in self._laser_turrets:
            if lt.is_alive:
                arcade.draw_circle_filled(
                    to_rx(lt.base.center_x), mid_y, _RADAR_DOT_R, _RADAR_ENEMY_COLOR
                )

        # Patrol ships — red dots (moving).
        for patrol in self._patrols:
            if patrol.is_alive:
                arcade.draw_circle_filled(
                    to_rx(patrol.center_x), mid_y, _RADAR_DOT_R, _RADAR_ENEMY_COLOR
                )

        # Boss — larger orange dot.
        if self._boss is not None and self._boss.is_alive:
            arcade.draw_circle_filled(
                to_rx(self._boss.body.center_x),
                mid_y,
                _RADAR_DOT_R * 2.5,
                _RADAR_BOSS_COLOR,
            )

        # Player — bright yellow dot, drawn last so it stays on top.
        arcade.draw_circle_filled(
            to_rx(self._ship.center_x), mid_y, _RADAR_DOT_R * 1.5, _RADAR_PLAYER_COLOR
        )
