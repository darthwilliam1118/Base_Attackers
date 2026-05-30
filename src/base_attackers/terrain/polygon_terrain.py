"""PolygonTerrainRenderer — immediate-mode polygon terrain.

Each active chunk pair (i, i+1) is drawn as a trapezoid: floor goes
from y=0 up to floor_y at each end; the optional ceiling goes from
ceiling_y up to world_height.  The active-chunk set is updated in
:meth:`update` as the camera scrolls; :meth:`draw` redraws every
frame with ``arcade.draw_polygon_filled``.

``ShapeElementList`` is intentionally NOT used — it requires a full
GPU buffer rebuild whenever any element is added or removed, which
would stutter visibly as chunks enter and leave the active range
(see CLAUDE.md).
"""

from __future__ import annotations

import arcade

from src.base_attackers.terrain.terrain_base import (
    CorridorSlice,
    TerrainBase,
    TerrainConfig,
)

_FLOOR_COLOR = (60, 100, 140)
_CEILING_COLOR = (60, 100, 140)


class PolygonTerrainRenderer(TerrainBase):
    def __init__(
        self,
        profile: list[CorridorSlice],
        config: TerrainConfig,
        screen_width: int,
    ) -> None:
        super().__init__(profile, config)
        self._screen_width = screen_width
        self._active_indices: set[int] = set()

    # ---- collision -------------------------------------------------
    #
    # The trapezoids are drawn with sloped top/bottom edges that
    # interpolate linearly between adjacent chunk samples, so collision
    # MUST interpolate too.  The base class returns the step value at the
    # chunk's left edge; on steep terrain (high amplitude/frequency at
    # higher levels) that diverges from the drawn edge by up to
    # ``slope * chunk_width`` — enough that the ship explodes well below
    # the visible ceiling.  These overrides match the rendered geometry
    # exactly (the floor edge runs a.floor_y -> b.floor_y; the ceiling
    # edge runs a.ceiling_y -> b.ceiling_y across each chunk pair).

    def _bracket(self, world_x: float) -> tuple[CorridorSlice, CorridorSlice, float]:
        cw = self.config.chunk_width
        n = len(self.profile)
        i = int(world_x // cw)
        i = max(0, min(i, n - 2)) if n >= 2 else 0
        a = self.profile[i]
        b = self.profile[min(i + 1, n - 1)]
        t = (world_x - a.x) / cw if cw else 0.0
        t = max(0.0, min(1.0, t))
        return a, b, t

    def floor_y_at(self, world_x: float) -> float:
        a, b, t = self._bracket(world_x)
        return a.floor_y + (b.floor_y - a.floor_y) * t

    def ceiling_y_at(self, world_x: float) -> float | None:
        a, b, t = self._bracket(world_x)
        if a.ceiling_y is None or b.ceiling_y is None:
            return a.ceiling_y if a.ceiling_y is not None else b.ceiling_y
        return a.ceiling_y + (b.ceiling_y - a.ceiling_y) * t

    # ---- public API ------------------------------------------------

    def update(self, camera_x: float) -> None:
        cw = self.config.chunk_width
        buffer_px = self.config.cull_buffer_chunks * cw
        left = camera_x - buffer_px
        right = camera_x + self._screen_width + buffer_px
        first_idx = max(0, int(left // cw))
        last_idx = min(len(self.profile) - 1, int(right // cw))
        self._active_indices = set(range(first_idx, last_idx + 1))

    def draw(self) -> None:
        if not self._active_indices:
            return
        indices = sorted(self._active_indices)
        wh = self.config.world_height

        for i in indices:
            if i + 1 >= len(self.profile):
                continue
            a: CorridorSlice = self.profile[i]
            b: CorridorSlice = self.profile[i + 1]

            # Floor trapezoid: from y=0 up to floor_y at each end.
            arcade.draw_polygon_filled(
                [(a.x, 0.0), (b.x, 0.0), (b.x, b.floor_y), (a.x, a.floor_y)],
                _FLOOR_COLOR,
            )

            # Optional ceiling trapezoid: from ceiling_y up to world_height.
            if a.ceiling_y is not None and b.ceiling_y is not None:
                arcade.draw_polygon_filled(
                    [
                        (a.x, a.ceiling_y),
                        (b.x, b.ceiling_y),
                        (b.x, wh),
                        (a.x, wh),
                    ],
                    _CEILING_COLOR,
                )

    def active_chunk_count(self) -> int:
        return len(self._active_indices)
