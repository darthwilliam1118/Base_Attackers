"""Main game window for Base Attackers."""

from __future__ import annotations

import arcade
from agf.background import ProceduralStarField, StaticBackground
from agf.paths import resource_path
from agf.window import ScrollingGameWindow

from src.base_attackers.game_config import GameConfig
from src.base_attackers.state import GameState, GameStateManager

SCREEN_TITLE = "Base Attackers"

# Single project font — KenVector Future2 Thin
GAME_FONT = "KenVector Future2 Thin"


class GameWindow(ScrollingGameWindow):
    TITLE = SCREEN_TITLE

    def __init__(self) -> None:
        cfg = GameConfig.load()
        super().__init__(cfg, cfg.background, SCREEN_TITLE)

        # agf's GameWindowBase sizes the window from max_window_height at a
        # fixed ~1.25 aspect (near-square).  This is a horizontal scroller,
        # so override to the explicit [window] dimensions and rebuild the
        # size-dependent pieces (background, star field, cameras).  Every
        # view reads self.window.width/height, so the rest adapts for free.
        self._apply_window_size(cfg)

        # arcade.get_fps() returns 0 unless timings are enabled.
        arcade.enable_timings()

        self.music.set_volume(cfg.music_volume)
        # Preload and start the "ending" track — used on the splash, menu,
        # and every between-level screen.
        self.music.load_track("ending")
        self.music.play("ending")

        self._manager = GameStateManager(self, GameState.SPLASH)
        self._manager.context["config"] = cfg
        self._manager.transition(GameState.SPLASH)

    def _apply_window_size(self, cfg: GameConfig) -> None:
        """Resize the window to the explicit [window] dimensions and rebuild
        the size-dependent pieces agf built at its default size.
        """
        target_w, target_h = cfg.window.width, cfg.window.height
        if (self.width, self.height) == (target_w, target_h):
            return
        self.set_size(target_w, target_h)
        self.center_window()
        bg = cfg.background
        self.background = StaticBackground(bg.background_image, target_w, target_h)
        self.star_field = ProceduralStarField(
            target_w,
            target_h,
            bg.star_count,
            bg.star_speed_min,
            bg.star_speed_max,
        )
        self._refresh_cameras()

    def _refresh_cameras(self) -> None:
        """Rebuild the world + GUI cameras so their viewport/projection
        match the current window size.

        Built with an explicit viewport from ``self.width/height`` (which
        ``set_size`` updates synchronously) rather than relying on the
        default ``Camera2D()`` viewport, which reads the GL screen viewport
        that may not have refreshed yet when this runs during __init__.
        Projection defaults to the viewport size (1:1 px mapping) and
        position to centre, matching what ScrollingGameWindow built.
        """
        rect = arcade.LBWH(0.0, 0.0, float(self.width), float(self.height))
        center = (self.width / 2.0, self.height / 2.0)
        self.world_camera = arcade.Camera2D(viewport=rect, position=center)
        self.gui_camera = arcade.Camera2D(viewport=rect, position=center)

    def on_resize(self, width: int, height: int) -> None:
        """Keep the cameras matched to the framebuffer on any resize.

        Arcade's internal ``_on_resize`` refreshes the GL viewport before
        this runs.  Guarded because on_resize can fire during base-class
        construction, before the cameras exist.
        """
        super().on_resize(width, height)
        if getattr(self, "gui_camera", None) is not None:
            self._refresh_cameras()

    def _load_fonts(self) -> None:
        """Load TTFs and force every agf module that references FONT_MAIN
        to resolve to the thin font, so all rendered text uses
        KenVector Future2 Thin."""
        arcade.load_font(resource_path("assets/fonts/kenvector_future2.ttf"))
        arcade.load_font(resource_path("assets/fonts/kenvector_future_thin2.ttf"))

        import agf.ui.text_utils as _tu

        _tu.FONT_MAIN = GAME_FONT
        _tu.FONT_THIN = GAME_FONT

        # Modules that did `from agf.ui.text_utils import FONT_MAIN` cached
        # the name locally — rebind those too.
        import importlib

        for mod_name in (
            "agf.views.splash",
            "agf.views.main_menu",
            "agf.views.game_over",
            "agf.views.level_complete",
            "agf.views.score_entry",
        ):
            try:
                mod = importlib.import_module(mod_name)
            except Exception:
                continue
            if hasattr(mod, "FONT_MAIN"):
                mod.FONT_MAIN = GAME_FONT
            if hasattr(mod, "FONT_THIN"):
                mod.FONT_THIN = GAME_FONT


def main() -> None:
    GameWindow()
    arcade.run()
