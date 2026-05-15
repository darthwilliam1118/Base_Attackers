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
