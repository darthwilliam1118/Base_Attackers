"""FuelTower — a refuelling fixture on the floor (or ceiling) of the corridor.

The ship docks by approaching the tower's dock point from the correct
side (above for floor towers, below for ceiling towers).  When within
``cfg.snap_distance`` of the dock point, ``RunLevelView`` snaps the
ship and sets ``ship.is_docked = True``; fuel transfers at
``cfg.transfer_rate`` until the tower is empty or the ship undocks.

**Construction safety pattern.**  ``arcade.Sprite`` only knows the
sprite dimensions after the texture loads, so the caller MUST:

    tower = FuelTower(world_x=x, world_y=0.0, ...)   # dummy y
    floor_y = terrain.floor_y_at(x)
    tower.center_y = floor_y + tower.height / 2.0
    tower.dock_y   = tower.center_y + tower.height / 2.0 + 12.0

The constructor stores ``world_y`` verbatim and initialises ``dock_y``
to the same value — both placeholders that the caller overwrites once
``tower.height`` is available.
"""

from __future__ import annotations

import math

import arcade

from agf.paths import resource_path
from src.base_attackers.game_config import FuelTowerSettings


class FuelTower(arcade.Sprite):
    SPRITE_PATH = "assets/images/PNG/Parts/fuel-tower.png"

    def __init__(
        self,
        world_x: float,
        world_y: float,
        surface: str,
        cfg: FuelTowerSettings,
        scale: float = 1.0,
    ) -> None:
        super().__init__(resource_path(self.SPRITE_PATH), scale=scale)
        self.center_x = world_x
        self.center_y = world_y  # placeholder — caller overwrites
        self.surface: str = surface  # "floor" or "ceiling"
        self.cfg: FuelTowerSettings = cfg
        self.fuel_remaining: float = cfg.tower_capacity
        self._pressure_timer: float = 0.0
        # Dock point — caller overwrites once tower.height is known.
        self.dock_y: float = world_y

    # ---- properties -----------------------------------------------

    @property
    def has_fuel(self) -> bool:
        return self.fuel_remaining > 0.0

    @property
    def is_depleted(self) -> bool:
        return self.fuel_remaining <= 0.0

    # ---- per-frame ------------------------------------------------

    def update_transfer(self, ship, delta_time: float) -> float:
        """Transfer fuel from this tower to *ship*.  Returns the amount
        actually transferred this frame (zero when depleted or the
        ship is full).
        """
        if self.fuel_remaining <= 0.0:
            return 0.0
        amount = min(
            self.cfg.transfer_rate * delta_time,
            self.fuel_remaining,
            ship.fuel_capacity - ship.fuel,
        )
        if amount <= 0.0:
            return 0.0
        self.fuel_remaining -= amount
        ship.add_fuel(amount)
        return amount

    def update_pressure(self, delta_time: float) -> bool:
        """Tick the dock-pressure timer.  Returns True on the frame the
        timer crosses ``spawn_pressure_interval`` (then resets).
        """
        self._pressure_timer += delta_time
        if self._pressure_timer >= self.cfg.spawn_pressure_interval:
            self._pressure_timer = 0.0
            return True
        return False

    # ---- docking helpers ------------------------------------------

    def snap_distance_to(self, ship_x: float, ship_y: float) -> float:
        """Euclidean distance from the ship centre to this tower's dock point."""
        return math.hypot(ship_x - self.center_x, ship_y - self.dock_y)
