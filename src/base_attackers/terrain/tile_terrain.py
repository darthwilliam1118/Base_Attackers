"""TileTerrainRenderer — sprite-based chunky terrain.

Terrain never moves, so the SpriteList uses spatial hashing.  Tiles are
added column-by-column as the camera approaches the right edge of the
active range, and culled column-by-column on the left.

A single solid-color Texture is generated in-memory and shared by every
tile; real terrain tile art is selected after the Phase 1 renderer
decision.
"""

from __future__ import annotations

import arcade
from PIL import Image

from src.base_attackers.terrain.terrain_base import (
    CorridorSlice,
    TerrainBase,
    TerrainConfig,
)

_TILE_RGBA = (80, 120, 60, 255)
_TILE_HASH = "ba_terrain_tile_chunky"


def _build_tile_texture(size: int) -> arcade.Texture:
    img = Image.new("RGBA", (size, size), _TILE_RGBA)
    return arcade.Texture(img, hash=f"{_TILE_HASH}_{size}")


class TileTerrainRenderer(TerrainBase):
    def __init__(
        self,
        profile: list[CorridorSlice],
        config: TerrainConfig,
        screen_width: int,
    ) -> None:
        super().__init__(profile, config)
        self._screen_width = screen_width
        self._tile_texture = _build_tile_texture(config.chunk_width)
        self._sprites = arcade.SpriteList(use_spatial_hash=True)
        self._active_columns: dict[int, list[arcade.Sprite]] = {}

    # ---- public API ------------------------------------------------

    def update(self, camera_x: float) -> None:
        cw = self.config.chunk_width
        buffer_px = self.config.cull_buffer_chunks * cw
        left = camera_x - buffer_px
        right = camera_x + self._screen_width + buffer_px
        first_idx = max(0, int(left // cw))
        last_idx = min(len(self.profile) - 1, int(right // cw))

        # Cull columns that fell out of range.
        to_remove = [i for i in self._active_columns if i < first_idx or i > last_idx]
        for i in to_remove:
            for sprite in self._active_columns.pop(i):
                sprite.remove_from_sprite_lists()

        # Add columns that came into range.
        for idx in range(first_idx, last_idx + 1):
            if idx not in self._active_columns:
                self._active_columns[idx] = self._build_column(idx)

    def draw(self) -> None:
        self._sprites.draw()

    def active_chunk_count(self) -> int:
        return len(self._active_columns)

    # ---- internals -------------------------------------------------

    def _build_column(self, idx: int) -> list[arcade.Sprite]:
        cw = self.config.chunk_width
        half = cw / 2.0
        slice_ = self.profile[idx]
        center_x = slice_.x + half
        sprites: list[arcade.Sprite] = []

        # Floor: stack tiles from y=half upward until tile top reaches floor_y.
        y = half
        while y - half < slice_.floor_y:
            sprite = arcade.Sprite(self._tile_texture, center_x=center_x, center_y=y)
            self._sprites.append(sprite)
            sprites.append(sprite)
            y += cw

        # Ceiling: stack tiles from ceiling_y up past world_height so the
        # ceiling surface looks solid across the top.  The portion that
        # extends above world_height is hidden behind the HUD mask drawn
        # in GUI-camera space by the consuming view.
        if slice_.ceiling_y is not None:
            y = slice_.ceiling_y + half
            while y - half < self.config.world_height:
                sprite = arcade.Sprite(
                    self._tile_texture, center_x=center_x, center_y=y
                )
                self._sprites.append(sprite)
                sprites.append(sprite)
                y += cw

        return sprites
