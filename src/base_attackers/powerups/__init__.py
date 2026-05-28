"""Base Attackers power-up package.

Concrete effect classes and the game-specific PowerUpManager subclass.
"""

from src.base_attackers.powerups.effects import (
    BigGunEffect,
    FuelCanisterEffect,
    HealthRestoreEffect,
    MultiShotEffect,
    RapidFireEffect,
    ShieldEffect,
)
from src.base_attackers.powerups.manager import BAPowerUpManager

__all__ = [
    "BAPowerUpManager",
    "BigGunEffect",
    "FuelCanisterEffect",
    "HealthRestoreEffect",
    "MultiShotEffect",
    "RapidFireEffect",
    "ShieldEffect",
]
