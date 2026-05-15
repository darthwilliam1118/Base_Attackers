"""TerrainTestView — Phase 1 testbed for terrain renderers.

Pure terrain showcase: no ship, no HUD, no game state.  T toggles
between TileTerrainRenderer and PolygonTerrainRenderer, R regenerates
the corridor profile with a new seed, 1-5 select difficulty presets,
and arrow keys / WASD scroll the world camera.  ESC returns to the
main menu.
"""

from __future__ import annotations

import random
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import arcade
from pyglet.math import Vec2

from agf.paths import writable_root
from agf.ui.text_utils import FONT_THIN
from src.base_attackers.terrain import (
    PolygonTerrainRenderer,
    TerrainBase,
    TerrainConfig,
    TileTerrainRenderer,
    generate_corridor_profile,
)

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


_SCROLL_SPEED = 600.0  # px/sec
_OVERLAY_COLOR = arcade.color.WHITE
_OVERLAY_FONT_SIZE = 14
_CONFIG_LOAD_ERRORS = (FileNotFoundError, tomllib.TOMLDecodeError, RuntimeError)


@dataclass(frozen=True)
class _Preset:
    amplitude: float
    frequency: float
    half_width: float
    ceiling_present: bool


_PRESETS: dict[int, _Preset] = {
    1: _Preset(60.0, 0.005, 300.0, False),
    2: _Preset(100.0, 0.007, 260.0, False),
    3: _Preset(130.0, 0.010, 220.0, True),
    4: _Preset(160.0, 0.013, 185.0, True),
    5: _Preset(190.0, 0.016, 155.0, True),
}


def _load_base_terrain_config() -> TerrainConfig:
    """Parse [terrain] and [level_1] from game_config.toml into a TerrainConfig.

    Preset overrides are applied on top of this base in _build().  Falls
    back to the brief's defaults if the file is missing or contains
    malformed entries (GameConfig.load() has the same swallow-and-default
    behavior).
    """
    try:
        path = writable_root() / "game_config.toml"
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except _CONFIG_LOAD_ERRORS:
        data = {}
    terrain = data.get("terrain", {})
    level1 = data.get("level_1", {})
    return TerrainConfig(
        world_width=float(level1.get("world_width", 6400.0)),
        world_height=float(level1.get("world_height", 720.0)),
        chunk_width=int(terrain.get("chunk_width", 64)),
        cull_buffer_chunks=int(terrain.get("cull_buffer_chunks", 3)),
        amplitude=float(level1.get("terrain_amplitude", 80.0)),
        frequency=float(level1.get("terrain_frequency", 0.008)),
        half_width=float(level1.get("terrain_half_width", 280.0)),
        ceiling_present=bool(level1.get("ceiling_present", False)),
    )


class TerrainTestView(arcade.View):
    def __init__(self, manager: "GameStateManager") -> None:
        super().__init__()
        self._manager = manager
        self._base_config = _load_base_terrain_config()
        self._kind: str = "tile"
        self._preset_id: int = 1
        self._seed: int = random.randrange(0, 1_000_000)
        self._camera_x: float = 0.0
        self._held: set[int] = set()
        self._renderer: TerrainBase | None = None

        # Debug overlay (built lazily in on_show_view once window dims known).
        self._overlay_built: bool = False
        self._t_renderer: arcade.Text | None = None
        self._t_preset: arcade.Text | None = None
        self._t_seed: arcade.Text | None = None
        self._t_camx: arcade.Text | None = None
        self._t_chunks: arcade.Text | None = None
        self._t_fps: arcade.Text | None = None

    # ---- lifecycle -------------------------------------------------

    def on_show_view(self) -> None:
        if not self._overlay_built:
            self._build_overlay()
            self._overlay_built = True
        self._build()

    # ---- main loop -------------------------------------------------

    def on_update(self, delta_time: float) -> None:
        # Scroll camera based on held keys.
        dx = 0.0
        if arcade.key.RIGHT in self._held or arcade.key.D in self._held:
            dx += 1.0
        if arcade.key.LEFT in self._held or arcade.key.A in self._held:
            dx -= 1.0
        if dx != 0.0:
            self._camera_x += dx * _SCROLL_SPEED * delta_time
            # Testbed: allow scrolling left of origin.
            min_x = -float(self.window.width)
            max_x = self._base_config.world_width
            self._camera_x = max(min_x, min(self._camera_x, max_x))

        # Centre world camera; gui camera stays fixed at (0,0).
        sw = self.window.width
        self.window.world_camera.position = Vec2(
            self._camera_x + sw / 2.0,
            self._base_config.world_height / 2.0,
        )

        if self._renderer is not None:
            self._renderer.update(self._camera_x)

        self._refresh_overlay()

    def on_draw(self) -> None:
        self.clear()
        self.window.use_world_camera()
        if self._renderer is not None:
            self._renderer.draw()
        self.window.use_gui_camera()
        # HUD mask: hides ceiling-tile overstack above world_height and
        # reserves the band where score / lives / level will render.
        win_h = self.window.height
        world_h = self._base_config.world_height
        hud_bottom = (win_h + world_h) / 2.0
        arcade.draw_lrbt_rectangle_filled(
            0.0, float(self.window.width), hud_bottom, float(win_h), arcade.color.BLACK
        )
        if self._t_renderer:
            self._t_renderer.draw()
        if self._t_preset:
            self._t_preset.draw()
        if self._t_seed:
            self._t_seed.draw()
        if self._t_camx:
            self._t_camx.draw()
        if self._t_chunks:
            self._t_chunks.draw()
        if self._t_fps:
            self._t_fps.draw()

    # ---- input -----------------------------------------------------

    def on_key_press(self, key: int, modifiers: int) -> None:
        if key == arcade.key.T:
            self._kind = "polygon" if self._kind == "tile" else "tile"
            self._build()
            return
        if key == arcade.key.R:
            self._seed = random.randrange(0, 1_000_000)
            self._build()
            return
        if key in (
            arcade.key.KEY_1,
            arcade.key.KEY_2,
            arcade.key.KEY_3,
            arcade.key.KEY_4,
            arcade.key.KEY_5,
        ):
            self._preset_id = key - arcade.key.KEY_0
            self._build()
            return
        if key in (arcade.key.LEFT, arcade.key.RIGHT, arcade.key.A, arcade.key.D):
            self._held.add(key)
            return
        if key == arcade.key.ESCAPE:
            from src.base_attackers.state import GameState

            self._manager.transition(GameState.MAIN)

    def on_key_release(self, key: int, modifiers: int) -> None:
        self._held.discard(key)

    # ---- internals -------------------------------------------------

    def _build(self) -> None:
        preset = _PRESETS[self._preset_id]
        base = self._base_config
        cfg = TerrainConfig(
            world_width=base.world_width,
            world_height=base.world_height,
            chunk_width=base.chunk_width,
            cull_buffer_chunks=base.cull_buffer_chunks,
            amplitude=preset.amplitude,
            frequency=preset.frequency,
            half_width=preset.half_width,
            ceiling_present=preset.ceiling_present,
        )
        profile = generate_corridor_profile(cfg, seed=self._seed)
        if self._kind == "tile":
            self._renderer = TileTerrainRenderer(profile, cfg, self.window.width)
        else:
            self._renderer = PolygonTerrainRenderer(profile, cfg, self.window.width)
        # Prime the active chunk set for the current camera position.
        self._renderer.update(self._camera_x)

    def _build_overlay(self) -> None:
        sh = self.window.height
        line_h = 18
        x = 12
        top = sh - 12
        common = dict(
            color=_OVERLAY_COLOR,
            font_size=_OVERLAY_FONT_SIZE,
            font_name=FONT_THIN,
            anchor_y="top",
        )
        self._t_renderer = arcade.Text("", x, top - 0 * line_h, **common)
        self._t_preset = arcade.Text("", x, top - 1 * line_h, **common)
        self._t_seed = arcade.Text("", x, top - 2 * line_h, **common)
        self._t_camx = arcade.Text("", x, top - 3 * line_h, **common)
        self._t_chunks = arcade.Text("", x, top - 4 * line_h, **common)
        self._t_fps = arcade.Text("", x, top - 5 * line_h, **common)

    def _refresh_overlay(self) -> None:
        if self._t_renderer is None:
            return
        self._t_renderer.text = f"RENDERER: {self._kind.upper()}"
        self._t_preset.text = f"PRESET: {self._preset_id}"
        self._t_seed.text = f"SEED: {self._seed}"
        self._t_camx.text = f"CAMERA X: {self._camera_x:.0f}"
        chunks = self._renderer.active_chunk_count() if self._renderer else 0
        self._t_chunks.text = f"ACTIVE CHUNKS: {chunks}"
        self._t_fps.text = f"FPS: {arcade.get_fps():.0f}"
