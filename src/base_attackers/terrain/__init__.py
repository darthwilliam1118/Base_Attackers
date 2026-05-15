"""Terrain package — corridor profile and renderers."""

from src.base_attackers.terrain.terrain_base import (
    CorridorSlice,
    TerrainBase,
    TerrainConfig,
    generate_corridor_profile,
)
from src.base_attackers.terrain.tile_terrain import TileTerrainRenderer
from src.base_attackers.terrain.polygon_terrain import PolygonTerrainRenderer

__all__ = [
    "CorridorSlice",
    "TerrainBase",
    "TerrainConfig",
    "generate_corridor_profile",
    "TileTerrainRenderer",
    "PolygonTerrainRenderer",
]
