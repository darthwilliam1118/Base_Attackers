"""Allow running as python -m base_attackers."""
from pathlib import Path
from agf.paths import set_project_root

set_project_root(Path(__file__).parents[3])  # src/<pkg>/__main__.py → project root

from src.base_attackers.game import main

main()
