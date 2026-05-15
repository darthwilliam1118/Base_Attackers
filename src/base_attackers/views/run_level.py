"""RunLevelView — main gameplay view.

Builds the level's terrain from ``GameConfig.levels[N]`` (renderer kind
selected by ``terrain_renderer``), spawns the player ship at the level
entry, runs momentum physics via ``MomentumShipMixin``, follows the
ship with a deadzone-tracking world camera (X monotonically clamped,
Y degenerates while ``world_height <= window_height``), and renders a
minimal HUD stub in GUI-camera space.

Terrain collision is instant death: the ship's position is computed
each frame and tested via :meth:`TerrainBase.point_in_terrain` *before*
being committed, so a contact frame never has the ship inside terrain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import arcade
from pyglet.math import Vec2

from agf.paths import resource_path  # noqa: F401  (kept for future sfx)
from agf.ships.momentum import MomentumConfig
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

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


# Ship must stay inside this fraction of the window width / height before
# the world camera moves.
_DEADZONE_LEFT = 0.25
_DEADZONE_RIGHT = 0.65
_DEADZONE_TOP = 0.80
_DEADZONE_BOTTOM = 0.20


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

        # Terrain + bounds (window dims aren't known at construction time
        # on all platforms, so defer screen-width-dependent setup until
        # on_show_view).
        self._terrain: TerrainBase | None = None
        self._terrain_cfg: TerrainConfig | None = None

        # Ship + render list.
        mcfg = MomentumConfig(
            accel=cfg.ship.accel,
            friction=cfg.ship.friction,
            max_speed_x=cfg.ship.max_speed_x,
            max_speed_y=cfg.ship.max_speed_y,
        )
        self._ship = PlayerShip(mcfg, max_hp=cfg.ship.hp, gravity=cfg.ship.gravity)
        self._ship_list = arcade.SpriteList()
        self._ship_list.append(self._ship)

        # HUD (built lazily in on_show_view once window dims are known).
        self._hud_built: bool = False
        self._hud_fps: arcade.Text | None = None
        self._hud_world_x: arcade.Text | None = None
        self._hud_hp: arcade.Text | None = None
        self._hud_fuel_label: arcade.Text | None = None

    # ---- lifecycle -------------------------------------------------

    def on_show_view(self) -> None:
        if self._terrain is None:
            self._terrain, self._terrain_cfg = _build_terrain(
                self._cfg, self._level_cfg, self.window.width
            )
            self._spawn_ship()
            # Centre the camera on the spawn zone.
            self.window.world_camera.position = Vec2(
                self.window.width / 2.0, self.window.height / 2.0
            )
            self._terrain.update(0.0)
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
        self._update_ship(delta_time)
        self._update_camera()
        # Feed the terrain renderer the world-X of the camera's left edge.
        cam_left = self.window.world_camera.position.x - self.window.width / 2.0
        self._terrain.update(cam_left)
        self._refresh_hud()

    def on_draw(self) -> None:
        self.clear()
        self.window.use_world_camera()
        if self._terrain is not None:
            self._terrain.draw()
        self._ship_list.draw()
        self.window.use_gui_camera()
        self._draw_hud()

    # ---- input -----------------------------------------------------

    def on_key_press(self, key: int, modifiers: int) -> None:
        self._held_keys.add(key)

    def on_key_release(self, key: int, modifiers: int) -> None:
        self._held_keys.discard(key)

    # ---- ship + camera --------------------------------------------

    def _update_ship(self, delta_time: float) -> None:
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

        # Horizontal bounds:
        #   - Left: ~1 chunk_width from the window's left edge.
        #   - Right: ~1 chunk_width from the world's right edge (the world
        #     end, not the screen edge — once the camera is right-clamped
        #     these coincide).
        # On contact, zero horizontal velocity so the ship parks cleanly.
        sw = self.window.width
        cam_left = self.window.world_camera.position.x - sw / 2.0
        assert self._terrain_cfg is not None
        cw = float(self._terrain_cfg.chunk_width)
        ship_left_bound = cam_left + cw
        ship_right_bound = self._terrain_cfg.world_width - cw
        if new_x < ship_left_bound:
            new_x = ship_left_bound
            self._ship.velocity_x = 0.0
        elif new_x > ship_right_bound:
            new_x = ship_right_bound
            self._ship.velocity_x = 0.0

        # Vertical bounds: keep the whole sprite visible — top must not
        # cross the world ceiling (HUD band) and bottom must not slip
        # below y=0.  Zero vy on contact for a clean park.
        half_h = self._ship.height / 2.0
        ship_top_bound = self._terrain_cfg.world_height - half_h
        ship_bot_bound = half_h
        if new_y > ship_top_bound:
            new_y = ship_top_bound
            self._ship.velocity_y = 0.0
        elif new_y < ship_bot_bound:
            new_y = ship_bot_bound
            self._ship.velocity_y = 0.0

        # Terrain collision = instant death.  Tested against the ship's
        # tight (algo_detailed) hitbox so any wing/nose contact counts,
        # not just the centre point.
        assert self._terrain is not None
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
        assert self._terrain_cfg is not None
        world_h = self._terrain_cfg.world_height
        cam_bottom_max = max(0.0, world_h - sh)
        cam_bottom = max(0.0, min(cam_bottom, cam_bottom_max))

        self.window.world_camera.position = Vec2(
            cam_left + sw / 2.0,
            cam_bottom + sh / 2.0,
        )

    def _on_terrain_collision(self) -> None:
        """Ship hit terrain — instant death regardless of HP."""
        from src.base_attackers.state import GameState

        self._ship.hp = 0
        self._manager.transition(GameState.GAME_OVER)

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

    # ---- HUD -------------------------------------------------------

    def _build_hud(self) -> None:
        sh = self.window.height
        common = dict(font_name=FONT_THIN, font_size=14, color=arcade.color.WHITE)
        self._hud_fps = arcade.Text("FPS: --", 12, sh - 20, **common)
        self._hud_world_x = arcade.Text("X: 0", 12, sh - 40, **common)
        self._hud_hp = arcade.Text("HP: ---", 12, sh - 60, **common)
        self._hud_fuel_label = arcade.Text("FUEL: ---", 12, sh - 80, **common)

    def _refresh_hud(self) -> None:
        if self._hud_fps is None:
            return
        self._hud_fps.text = f"FPS: {arcade.get_fps():.0f}"
        self._hud_world_x.text = f"X: {self._ship.center_x:.0f}"
        self._hud_hp.text = f"HP: {self._ship.hp} / {self._ship.MAX_HP}"
        self._hud_fuel_label.text = "FUEL: ---"

    def _draw_hud(self) -> None:
        assert self._terrain_cfg is not None
        sw = self.window.width
        sh = self.window.height
        cam_bottom = self.window.world_camera.position.y - sh / 2.0
        # Screen-Y at which the world ceiling sits — everything above it
        # is the future HUD area and is masked solid black so the tile
        # renderer's ceiling overstack stays hidden.
        hud_bottom = float(self._terrain_cfg.world_height) - cam_bottom
        arcade.draw_lrbt_rectangle_filled(
            0.0, float(sw), hud_bottom, float(sh), arcade.color.BLACK
        )
        if self._hud_fps:
            self._hud_fps.draw()
        if self._hud_world_x:
            self._hud_world_x.draw()
        if self._hud_hp:
            self._hud_hp.draw()
        if self._hud_fuel_label:
            self._hud_fuel_label.draw()
