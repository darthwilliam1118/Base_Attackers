"""PolygonTerrainRenderer surface lookups must match its drawn slopes.

Regression: collision used the base-class step value (chunk left edge)
while the trapezoids draw sloped edges, so on steep terrain the ship
exploded up to ~slope*chunk_width below the visible ceiling.
"""

from __future__ import annotations

from src.base_attackers.terrain.polygon_terrain import PolygonTerrainRenderer
from src.base_attackers.terrain.terrain_base import CorridorSlice, TerrainConfig

_CW = 64


def _cfg(ceiling: bool = True) -> TerrainConfig:
    return TerrainConfig(
        world_width=256.0,
        world_height=960.0,
        chunk_width=_CW,
        cull_buffer_chunks=3,
        amplitude=120.0,
        frequency=0.01,
        half_width=200.0,
        ceiling_present=ceiling,
    )


def _profile() -> list[CorridorSlice]:
    # Two chunks with a steep ceiling/floor slope between samples.
    return [
        CorridorSlice(x=0.0, floor_y=100.0, ceiling_y=600.0),
        CorridorSlice(x=64.0, floor_y=200.0, ceiling_y=720.0),
        CorridorSlice(x=128.0, floor_y=200.0, ceiling_y=720.0),
    ]


def test_floor_and_ceiling_interpolate_at_midpoint() -> None:
    r = PolygonTerrainRenderer(_profile(), _cfg(), 1280)
    # Midpoint of chunk 0 -> halfway between the two samples.
    assert r.floor_y_at(32.0) == 150.0  # (100 + 200) / 2
    assert r.ceiling_y_at(32.0) == 660.0  # (600 + 720) / 2


def test_endpoints_match_profile() -> None:
    r = PolygonTerrainRenderer(_profile(), _cfg(), 1280)
    assert r.floor_y_at(0.0) == 100.0
    assert r.ceiling_y_at(0.0) == 600.0
    assert r.floor_y_at(64.0) == 200.0
    assert r.ceiling_y_at(64.0) == 720.0


def test_point_in_terrain_matches_interpolated_ceiling() -> None:
    r = PolygonTerrainRenderer(_profile(), _cfg(), 1280)
    # At the chunk midpoint the drawn ceiling is 660; collision must agree.
    assert r.point_in_terrain(32.0, 659.0) is False  # just below ceiling
    assert r.point_in_terrain(32.0, 661.0) is True  # just inside ceiling


def test_no_ceiling_returns_none() -> None:
    prof = [
        CorridorSlice(x=0.0, floor_y=100.0, ceiling_y=None),
        CorridorSlice(x=64.0, floor_y=120.0, ceiling_y=None),
    ]
    r = PolygonTerrainRenderer(prof, _cfg(ceiling=False), 1280)
    assert r.ceiling_y_at(32.0) is None
