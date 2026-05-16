"""Pytest configuration — set agf project root before any test imports."""

from pathlib import Path
from agf.paths import set_project_root

set_project_root(Path(__file__).parents[1])
