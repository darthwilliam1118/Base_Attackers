"""PlayerShip — the player-controlled ship sprite.

Inherits ``arcade.Sprite`` for rendering and ``MomentumShipMixin``
for physics.  Terrain collision is handled by ``RunLevelView`` after
applying the position delta — the ship never touches terrain itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import arcade

from agf.paths import resource_path
from agf.ships.momentum import MomentumConfig, MomentumShipMixin

if TYPE_CHECKING:
    from src.base_attackers.terrain import TerrainBase


class PlayerShip(arcade.Sprite, MomentumShipMixin):
    def __init__(
        self,
        momentum_config: MomentumConfig,
        max_hp: int = 3,
        gravity: float = 0.0,
    ) -> None:
        # Load with the tightest hitbox algorithm so terrain collision
        # tests against the actual ship silhouette, not its bounding box.
        texture = arcade.load_texture(
            resource_path("assets/images/PNG/playerShip1.png"),
            hit_box_algorithm=arcade.hitbox.algo_detailed,
        )
        arcade.Sprite.__init__(self, texture)
        MomentumShipMixin.__init__(self, momentum_config)
        self.MAX_HP: int = max_hp
        self.hp: int = max_hp
        self.gravity: float = gravity

    def update_ship(self, delta_time: float) -> tuple[float, float]:
        """Compute this frame's position delta without applying it.

        Gravity (if any) is added as a constant downward acceleration
        before the momentum/friction step, so it's damped to a terminal
        velocity by friction the same way thrust input is.
        """
        if self.gravity:
            self.velocity_y -= self.gravity * delta_time
        return self.apply_momentum(delta_time)

    def collides_with_terrain(
        self, terrain: "TerrainBase", at_x: float, at_y: float
    ) -> bool:
        """True if any vertex of the ship's silhouette would be inside
        terrain when the ship is centred at (*at_x*, *at_y*).

        Uses the texture's detailed (pixel-perfect) hit-box polygon.
        Vertex sampling is sufficient because the corridor profile is
        piecewise-constant per ``chunk_width`` (64 px) while the
        detailed algorithm spaces hit-box points roughly per pixel.
        """
        # Raw points are texture-local (centred on the sprite origin) and
        # assume angle=0, scale=1 — both currently true for the player.
        for px, py in self.hit_box.points:
            if terrain.point_in_terrain(at_x + px, at_y + py):
                return True
        return False

    def take_damage(self, amount: int = 1) -> bool:
        """Apply damage.  Returns True if the ship is destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    @property
    def is_alive(self) -> bool:
        return self.hp > 0
