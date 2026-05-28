"""PlayerShip — the player-controlled ship sprite.

Inherits ``arcade.Sprite`` for rendering and ``MomentumShipMixin``
for physics.  Terrain collision is handled by ``RunLevelView`` after
applying the position delta — the ship never touches terrain itself.

Phase 3 additions:
- Fuel state (`fuel`, drain/refuel helpers, `fuel_empty`).
- Dock state (`is_docked`, `dock_tower`).
- `control_enabled` gate used by RunLevelView to skip input + weapons.
- Scratch overlay sprite that swaps texture by HP fraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import arcade

from agf.paths import resource_path
from agf.ships.momentum import MomentumConfig, MomentumShipMixin
from src.base_attackers.game_config import CombatSettings, ShipSettings

if TYPE_CHECKING:
    from src.base_attackers.terrain import TerrainBase
    from src.base_attackers.terrain_features import FuelTower


class PlayerShip(arcade.Sprite, MomentumShipMixin):
    def __init__(
        self,
        momentum_config: MomentumConfig,
        ship_cfg: ShipSettings,
        combat_cfg: CombatSettings | None = None,
        scale: float = 1.0,
    ) -> None:
        # Load with the tightest hitbox algorithm so terrain collision
        # tests against the actual ship silhouette, not its bounding box.
        texture = arcade.load_texture(
            resource_path("assets/images/PNG/playerShip1.png"),
            hit_box_algorithm=arcade.hitbox.algo_detailed,
        )
        arcade.Sprite.__init__(self, texture, scale=scale)
        MomentumShipMixin.__init__(self, momentum_config)
        self.MAX_HP: int = ship_cfg.hp
        self.hp: int = ship_cfg.hp
        self.gravity: float = ship_cfg.gravity

        # Fuel state.
        self.fuel: float = ship_cfg.fuel_capacity
        self.fuel_capacity: float = ship_cfg.fuel_capacity
        self.fuel_drain_rate: float = ship_cfg.fuel_drain_rate
        self.fuel_gravity: float = ship_cfg.fuel_gravity
        self.fuel_canister_restore: float = ship_cfg.fuel_canister_restore

        # Combat stats mirrored from CombatSettings so StatModifierEffects
        # (rapid_fire, big_gun) can mutate them in place.  RunLevelView
        # reads these instead of cfg.combat when firing / dealing damage.
        cc = combat_cfg or CombatSettings()
        self.player_fire_cooldown: float = cc.player_fire_cooldown
        self.player_bullet_damage: int = cc.player_bullet_damage

        # Dock state.
        self.is_docked: bool = False
        self.dock_tower: "FuelTower | None" = None

        # Scratch overlays (lazy-loaded by load_scratch_textures()).
        self._scratch_textures: list[arcade.Texture] = []
        self._scratch_sprite: arcade.Sprite | None = None

    # ---- properties -----------------------------------------------

    @property
    def fuel_empty(self) -> bool:
        return self.fuel <= 0.0

    @property
    def control_enabled(self) -> bool:
        """Input and weapons disabled when fuel is empty OR docked."""
        return not self.fuel_empty and not self.is_docked

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    # ---- physics / momentum ---------------------------------------

    def update_ship(self, delta_time: float) -> tuple[float, float]:
        """Compute this frame's position delta without applying it.

        Gravity (if any) is added as a constant downward acceleration
        before the momentum/friction step, so it's damped to a terminal
        velocity by friction the same way thrust input is.

        When fuel is empty or the ship is docked, ``RunLevelView`` skips
        this call entirely — fuel-empty drift is handled separately so
        friction doesn't damp ``fuel_gravity`` away.
        """
        if self.gravity:
            self.velocity_y -= self.gravity * delta_time
        return self.apply_momentum(delta_time)

    # ---- fuel -----------------------------------------------------

    def drain_fuel(self, delta_time: float) -> None:
        """Deplete fuel during normal flight.  No-op when docked."""
        if not self.is_docked:
            self.fuel = max(0.0, self.fuel - self.fuel_drain_rate * delta_time)

    def add_fuel(self, amount: float) -> None:
        self.fuel = min(self.fuel_capacity, self.fuel + amount)

    # ---- damage ---------------------------------------------------

    def take_damage(self, amount: int = 1) -> bool:
        """Apply damage.  Returns True if the ship is destroyed."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    # ---- collision ------------------------------------------------

    def collides_with_terrain(
        self, terrain: "TerrainBase", at_x: float, at_y: float
    ) -> bool:
        """True if any vertex of the ship's silhouette would be inside
        terrain when the ship is centred at (*at_x*, *at_y*).

        Uses the texture's detailed (pixel-perfect) hit-box polygon
        via ``get_adjusted_points()`` so the scaled silhouette is
        respected.  Vertex sampling is sufficient because the corridor
        profile is piecewise-constant per ``chunk_width`` (64 px) while
        the detailed algorithm spaces hit-box points roughly per pixel.
        Points come back already translated by the sprite's current
        center, so subtract that to get a texture-local offset before
        re-anchoring at the tentative ``(at_x, at_y)``.
        """
        cx = self.center_x
        cy = self.center_y
        for px, py in self.hit_box.get_adjusted_points():
            if terrain.point_in_terrain(at_x + (px - cx), at_y + (py - cy)):
                return True
        return False

    # ---- scratch overlays -----------------------------------------

    def load_scratch_textures(self) -> None:
        """Load the three scratch overlays and create the overlay sprite.

        Called once by ``RunLevelView`` after construction; the overlay
        sprite is added to a SpriteList for drawing.  It carries
        ``scratch1`` initially so the SpriteList has a valid texture to
        bind, but starts invisible at full HP.
        """
        base = "assets/images/PNG/Parts/"
        self._scratch_textures = [
            arcade.load_texture(resource_path(base + "scratch1.png")),
            arcade.load_texture(resource_path(base + "scratch2.png")),
            arcade.load_texture(resource_path(base + "scratch3.png")),
        ]
        sprite = arcade.Sprite(self._scratch_textures[0], scale=self.scale)
        sprite.center_x = self.center_x
        sprite.center_y = self.center_y
        sprite.visible = False
        self._scratch_sprite = sprite

    @property
    def scratch_sprite(self) -> arcade.Sprite | None:
        return self._scratch_sprite

    def update_scratch_overlay(self) -> None:
        """Pick the correct scratch texture for the current HP fraction
        and keep the overlay positioned over the ship.  Call each frame
        before the SpriteList draw.
        """
        sprite = self._scratch_sprite
        if sprite is None or not self._scratch_textures:
            return
        hp_frac = self.hp / self.MAX_HP if self.MAX_HP else 0.0
        if hp_frac > 2.0 / 3.0:
            sprite.visible = False
        elif hp_frac > 1.0 / 3.0:
            sprite.texture = self._scratch_textures[0]
            sprite.visible = True
        else:
            sprite.texture = self._scratch_textures[2]
            sprite.visible = True
        if sprite.visible:
            sprite.center_x = self.center_x
            sprite.center_y = self.center_y
