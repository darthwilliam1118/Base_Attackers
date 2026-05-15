"""Terrain base — corridor profile data, generator, and abstract renderer.

The corridor profile is the source of truth for both rendering and
collision detection: one CorridorSlice per chunk_width pixels across
the full world width.  Renderers consume the profile; collision is
O(1) via :meth:`TerrainBase.point_in_terrain`.
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

# Minimum vertical clearance (px) between floor and ceiling.  Generator
# enforces this so the ship always has room to fit.
_MIN_CORRIDOR_GAP = 180.0


@dataclass
class CorridorSlice:
    """The terrain profile at a single X position."""

    x: float
    floor_y: float
    ceiling_y: float | None


@dataclass
class TerrainConfig:
    world_width: float
    world_height: float
    chunk_width: int
    cull_buffer_chunks: int
    amplitude: float
    frequency: float
    half_width: float
    ceiling_present: bool


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 == edge0:
        return 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def generate_corridor_profile(
    config: TerrainConfig, seed: int | None = None
) -> list[CorridorSlice]:
    """Generate a corridor profile spanning the full world width.

    Two summed sine waves at different frequencies give an organic feel.
    A smoothstep ramp widens the corridor at the level entry (first 10%)
    and at the boss zone (last 10%).  Floor / ceiling are clamped so the
    clear gap never drops below _MIN_CORRIDOR_GAP.
    """
    rng = random.Random(seed)
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)

    cw = config.chunk_width
    n = max(1, int(math.ceil(config.world_width / cw)) + 1)
    W = config.world_width
    f1 = config.frequency
    f2 = config.frequency * 2.7

    profile: list[CorridorSlice] = []
    for i in range(n):
        x = i * cw
        # Boss-zone widening: corridor opens up over the last 10% of the
        # world (no entry ramp — terrain starts at full amplitude at x=0).
        edge_factor = 1.0 - _smoothstep(0.90 * W, W, x)
        running_amp = config.amplitude * edge_factor
        running_half = config.half_width + (1.0 - edge_factor) * 80.0

        offset = (
            (math.sin(f1 * x + phase_a) + 0.4 * math.sin(f2 * x + phase_b))
            * running_amp
            / 1.4
        )  # normalise so max ~= amplitude

        center_y = config.world_height / 2.0 + offset
        floor_y = center_y - running_half
        ceiling_y: float | None = None

        if config.ceiling_present:
            ceiling_y = center_y + running_half
            # Enforce min gap by widening the corridor symmetrically.
            gap = ceiling_y - floor_y
            if gap < _MIN_CORRIDOR_GAP:
                pad = (_MIN_CORRIDOR_GAP - gap) / 2.0
                floor_y -= pad
                ceiling_y += pad
            # Clamp into world bounds.
            floor_y = max(0.0, floor_y)
            ceiling_y = min(config.world_height, ceiling_y)
            if ceiling_y - floor_y < _MIN_CORRIDOR_GAP:
                ceiling_y = floor_y + _MIN_CORRIDOR_GAP
        else:
            # No ceiling — just keep floor below world height minus gap.
            floor_y = max(0.0, min(floor_y, config.world_height - _MIN_CORRIDOR_GAP))

        profile.append(CorridorSlice(x=x, floor_y=floor_y, ceiling_y=ceiling_y))

    return profile


class TerrainBase(ABC):
    def __init__(self, profile: list[CorridorSlice], config: TerrainConfig) -> None:
        self.profile = profile
        self.config = config

    def floor_y_at(self, world_x: float) -> float:
        idx = int(world_x // self.config.chunk_width)
        idx = max(0, min(idx, len(self.profile) - 1))
        return self.profile[idx].floor_y

    def ceiling_y_at(self, world_x: float) -> float | None:
        idx = int(world_x // self.config.chunk_width)
        idx = max(0, min(idx, len(self.profile) - 1))
        return self.profile[idx].ceiling_y

    def point_in_terrain(self, world_x: float, world_y: float) -> bool:
        floor = self.floor_y_at(world_x)
        if world_y <= floor:
            return True
        ceiling = self.ceiling_y_at(world_x)
        if ceiling is not None and world_y >= ceiling:
            return True
        return False

    @abstractmethod
    def update(self, camera_x: float) -> None: ...

    @abstractmethod
    def draw(self) -> None: ...

    @abstractmethod
    def active_chunk_count(self) -> int: ...
