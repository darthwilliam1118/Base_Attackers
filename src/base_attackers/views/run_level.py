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

import logging
from typing import TYPE_CHECKING

import arcade
from pyglet.math import Vec2

from agf.paths import resource_path
from agf.ships.momentum import MomentumConfig
from agf.sprites.explosion import ExplosionSprite
from agf.ui.text_utils import FONT_THIN
from src.base_attackers.game_config import GameConfig, LevelSettings
from src.base_attackers.ships import PlayerShip
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

# Hardcoded for Phase 3 — Phase 7 moves these into level config.
_PHASE3_TOWER_POSITIONS = [800.0, 2400.0, 4400.0]
_PHASE3_CANISTER_POSITIONS = [1600.0, 3200.0, 5000.0]

# Death sequence + dock indicator timings.
_DEATH_DURATION = 1.5
_DOCK_BLINK_PERIOD = 0.4

# Undock liftoff: instantaneous Y kick (px/s) away from the tower, plus a
# dock-check cooldown so the ship clears `snap_distance` before the dock
# scanner runs again.  Direction is +Y for floor towers, -Y for ceiling
# towers (chosen via tower.surface).
_LIFTOFF_SPEED = 200.0
_DOCK_COOLDOWN = 1.0

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


def _build_terrain(
    cfg: GameConfig, level_cfg: LevelSettings, screen_w: int
) -> tuple[TerrainBase, TerrainConfig]:
    """Instantiate the configured renderer for *level_cfg*."""
    seed = level_cfg.terrain_seed if level_cfg.terrain_seed != 0 else None
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
        self._level_cfg: LevelSettings = cfg.levels.get(1, LevelSettings())
        self._held_keys: set[int] = set()
        self._min_camera_left: float = 0.0

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
        self._ship = PlayerShip(mcfg, cfg.ship)
        self._ship.load_scratch_textures()
        self._ship_list = arcade.SpriteList()
        self._ship_list.append(self._ship)
        self._scratch_list = arcade.SpriteList()
        if self._ship.scratch_sprite is not None:
            self._scratch_list.append(self._ship.scratch_sprite)

        # Towers + canisters (populated in on_show_view).
        self._tower_list = arcade.SpriteList()
        self._towers: list[FuelTower] = []
        self._canister_list = arcade.SpriteList()

        # Explosion + death timer.
        self._explosion_list = arcade.SpriteList()
        self._death_timer: float = 0.0

        # Docking state.
        self._undock_requested: bool = False
        self._last_delta: float = 0.0
        self._dock_blink_timer: float = 0.0
        self._dock_blink_visible: bool = True
        self._dock_cooldown: float = 0.0

        # HUD (built lazily once window dims are known).
        self._hud_built: bool = False
        self._hud_fps: arcade.Text | None = None
        self._hud_world_x: arcade.Text | None = None
        self._hud_hp: arcade.Text | None = None
        self._hud_fuel_label: arcade.Text | None = None
        self._hud_docked: arcade.Text | None = None

    # ---- lifecycle -------------------------------------------------

    def on_show_view(self) -> None:
        if self._terrain is None:
            self._terrain, self._terrain_cfg = _build_terrain(
                self._cfg, self._level_cfg, self.window.width
            )
            self._spawn_ship()
            self.window.world_camera.position = Vec2(
                self.window.width / 2.0, self.window.height / 2.0
            )
            self._terrain.update(0.0)
            self._place_fuel_towers()
            self._place_fuel_canisters()
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

        # Tick the post-undock dock-suspension cooldown.
        if self._dock_cooldown > 0.0:
            self._dock_cooldown = max(0.0, self._dock_cooldown - delta_time)

        # Death sequence — play out the explosion before transitioning.
        if self._death_timer > 0.0:
            self._death_timer -= delta_time
            self._explosion_list.update(delta_time)
            if self._death_timer <= 0.0:
                from src.base_attackers.state import GameState

                self._manager.transition(GameState.GAME_OVER)
            return

        # Normal flight movement (skipped if docked or fuel-empty).
        self._update_ship(delta_time)

        # Fuel drain.
        self._ship.drain_fuel(delta_time)

        # Fuel-empty drift / gravity.  Routes to _destroy_ship on contact.
        if self._ship.fuel_empty and not self._ship.is_docked:
            self._apply_fuel_gravity(delta_time)
            if self._death_timer > 0.0:
                return  # collision fired mid-frame

        # Camera tracking + chunk loading.
        self._update_camera()
        cam_left = self.window.world_camera.position.x - self.window.width / 2.0
        self._terrain.update(cam_left)

        # Docking + collectibles.
        self._check_docking()
        self._check_canister_pickup()

        # Ship-state-driven visuals.
        self._ship.update_scratch_overlay()
        self._tick_dock_blink(delta_time)

        self._refresh_hud()

    def on_draw(self) -> None:
        self.clear()
        self.window.use_world_camera()
        if self._terrain is not None:
            self._terrain.draw()
        self._tower_list.draw()
        self._canister_list.draw()
        self._ship_list.draw()
        self._scratch_list.draw()
        self._explosion_list.draw()

        self.window.use_gui_camera()
        self._draw_hud()

    # ---- input -----------------------------------------------------

    def on_key_press(self, key: int, modifiers: int) -> None:
        # SPACE undocks the ship if docked.  Phase 4 will reuse SPACE
        # for firing — the is_docked check is the gate.
        if key == arcade.key.SPACE and self._ship.is_docked:
            self._undock_requested = True
        self._held_keys.add(key)

    def on_key_release(self, key: int, modifiers: int) -> None:
        self._held_keys.discard(key)

    # ---- ship + camera --------------------------------------------

    def _update_ship(self, delta_time: float) -> None:
        # Skip entirely when control is disabled (docked or fuel-empty);
        # movement in those states is handled elsewhere.
        if self._ship.is_docked or self._ship.fuel_empty:
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

        # Terrain collision = destruction sequence.
        assert self._terrain is not None
        if self._ship.collides_with_terrain(self._terrain, new_x, new_y):
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

        if self._ship.collides_with_terrain(self._terrain, new_x, new_y):
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

    def _on_terrain_collision(self) -> None:
        """Ship hit terrain — start the destruction sequence."""
        self._ship.hp = 0
        self._destroy_ship()

    def _destroy_ship(self) -> None:
        """Spawn an explosion, hide the ship, and start the death timer.

        ``on_update`` ticks ``_death_timer`` down and transitions to
        GAME_OVER once it expires.
        """
        if self._death_timer > 0.0:
            return  # already dying
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

    def _place_fuel_towers(self) -> None:
        """Construct each FuelTower at a placeholder Y, then position it
        using ``tower.height`` (only known after the texture loads)."""
        assert self._terrain is not None
        for x in _PHASE3_TOWER_POSITIONS:
            # Step 1: construct at dummy y=0 so the texture loads.
            tower = FuelTower(
                world_x=x,
                world_y=0.0,
                surface="floor",
                cfg=self._cfg.fuel_tower,
                scale=1.0,
            )
            # Step 2: now tower.height is known — sit the base on the
            # visible floor surface and put the dock just above the top.
            floor_y = self._terrain.floor_y_at(x)
            tower.center_y = floor_y + tower.height / 2.0
            tower.dock_y = tower.center_y + tower.height / 2.0 + 12.0
            self._tower_list.append(tower)
            self._towers.append(tower)

    def _place_fuel_canisters(self) -> None:
        assert self._terrain is not None
        for x in _PHASE3_CANISTER_POSITIONS:
            canister = arcade.Sprite(
                resource_path("assets/images/PNG/Power-ups/bolt_gold.png"),
                scale=self._cfg.sprite_scale,
            )
            canister.center_x = x
            canister.center_y = self._terrain.floor_y_at(x) + 80.0
            self._canister_list.append(canister)

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
        """Phase-4 hook fired every ``spawn_pressure_interval`` while docked.

        Phase 3 logs only (ASCII per CLAUDE.md).
        """
        log.info("dock pressure spawn tick (no-op in phase 3)")

    # ---- canisters -------------------------------------------------

    def _check_canister_pickup(self) -> None:
        if not self._canister_list:
            return
        hits = arcade.check_for_collision_with_list(self._ship, self._canister_list)
        for canister in hits:
            self._ship.add_fuel(self._cfg.ship.fuel_canister_restore)
            canister.remove_from_sprite_lists()

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
        sh = self.window.height
        common = dict(font_name=FONT_THIN, font_size=14, color=arcade.color.WHITE)
        self._hud_fps = arcade.Text("FPS: --", 12, sh - 20, **common)
        self._hud_world_x = arcade.Text("X: 0", 12, sh - 40, **common)
        self._hud_hp = arcade.Text("HP --", 12, sh - 60, **common)
        self._hud_fuel_label = arcade.Text("FUEL --", 12, sh - 80, **common)
        self._hud_docked = arcade.Text(
            "DOCKED",
            220,
            sh - 20,
            font_name=FONT_THIN,
            font_size=14,
            color=arcade.color.YELLOW,
        )

    def _refresh_hud(self) -> None:
        if self._hud_fps is None:
            return
        self._hud_fps.text = f"FPS: {arcade.get_fps():.0f}"
        self._hud_world_x.text = f"X: {self._ship.center_x:.0f}"
        self._hud_hp.text = f"HP {self._ship.hp} / {self._ship.MAX_HP}"
        self._hud_fuel_label.text = f"FUEL {self._ship.fuel:.0f}"

    def _draw_hud(self) -> None:
        assert self._terrain_cfg is not None
        sw = self.window.width
        sh = self.window.height
        cam_bottom = self.window.world_camera.position.y - sh / 2.0
        # Screen-Y at which the world ceiling sits — everything above is
        # the HUD area and is masked solid black so the tile renderer's
        # ceiling overstack stays hidden.
        hud_bottom = float(self._terrain_cfg.world_height) - cam_bottom
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

        # HUD text.
        if self._hud_fps:
            self._hud_fps.draw()
        if self._hud_world_x:
            self._hud_world_x.draw()
        if self._hud_hp:
            self._hud_hp.draw()
        if self._hud_fuel_label:
            self._hud_fuel_label.draw()
        if self._hud_docked and self._ship.is_docked and self._dock_blink_visible:
            self._hud_docked.draw()

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
