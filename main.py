"""Entry point for Base Attackers."""
from pathlib import Path
from agf.paths import set_project_root

set_project_root(Path(__file__).parent)

from src.base_attackers.game import GameWindow
import arcade


def main() -> None:
    GameWindow()
    arcade.run()


if __name__ == "__main__":
    main()
