"""
Main menu scene setup and registration.

Overview
--------
This module constructs the primary main menu scene for the application.
It utilizes the UI component system to display the game title, the 
best speedrun time (retrieved from the :class:`SaveManager`), and interactive 
buttons to start the game or quit the application.

The scene is registered into the global :class:`SceneManager` via a 
decorator during the application's initialization phase.
"""

import pygame
import sys
from components.backgroundPanel import BackgroundPanel
from core.ui.ui_anchor import UIAnchor
from managers.sceneManager import SceneManager, SceneContext
from managers.saveManager import SaveManager
from core.gameObject import GameObject
from core.gameManager import GameManager
from core.ui.canvas import Canvas
from core.ui.components.tmp_text import TMP_Text, TextAnchor
from core.ui.components.button import Button, ButtonColors
from tools import Console

import constants


def register_menu_scene(sm: SceneManager) -> None:
    """Registers the main menu scene with the provided SceneManager.

    This function should be called exactly once during the application's 
    startup sequence. It binds the internal scene builder logic to the 
    ``'menu'`` scene identifier.

    Parameters
    ----------
    sm : SceneManager
        The primary instance of the scene manager where the menu scene 
        will be registered.
    """

    @sm.scene('menu')
    def menu_scene(_: SceneContext) -> None:
        """Constructs the menu scene layout and instantiates UI elements."""
        renderer = GameManager.instance().renderer

        # ------------------------------------------------------------------
        # Canvas Root
        # ------------------------------------------------------------------
        canvas_obj = GameObject('MenuCanvas')
        canvas_obj.AddComponent(Canvas, sort_layer=100)
        renderer.register_object(canvas_obj)

        # ------------------------------------------------------------------
        # Background Panel (Semi-transparent overlay)
        # ------------------------------------------------------------------
        bg_obj = GameObject('MenuBG')
        bg_obj.AddComponent(
            BackgroundPanel,
            anchor=UIAnchor(
                anchor_x=0.5,
                anchor_y=0.5,
                offset_x=0.0,
                offset_y=0.0,
                width=constants.WindowConfig.REFERENCE_WIDTH,
                height=constants.WindowConfig.REFERENCE_HEIGHT
            ),
            color=(15, 15, 30, 210),
            corner_radius=16,
            border_color=(80, 80, 150, 180),
            border_width=2,
            ui_layer=0,
        )
        # renderer.register_object(bg_obj)

        # ------------------------------------------------------------------
        # Title Text
        # ------------------------------------------------------------------
        title_obj = GameObject('TitleText')
        title_obj.AddComponent(
            TMP_Text,
            anchor=UIAnchor(anchor_x=0.5, anchor_y=0, offset_x=0.0, offset_y=60+50, width=460, height=120),
            text='PROJECT\nDOOMSDAY',
            font_name='Arial',
            font_size=52,
            bold=True,
            color=(220, 80, 80, 255),
            alignment=TextAnchor.UPPER_CENTER,
            outline_width=2,
            outline_color=(80, 0, 0, 255),
            shadow_offset=(3, 3),
            shadow_color=(0, 0, 0, 180),
            ui_layer=1,
        )
        renderer.register_object(title_obj)

        # ------------------------------------------------------------------
        # Best Speedrun Time Display
        # ------------------------------------------------------------------
        best = SaveManager.Get('best_time', None)
        best_str = _format_time(best) if best is not None else '--:--.--'

        best_time_obj = GameObject('BestTimeValue')
        best_time_obj.AddComponent(
            TMP_Text,
            anchor=UIAnchor(anchor_x=1, anchor_y=0, offset_x=-230-20, offset_y=22.5+20, width=460, height=55),
            text=best_str,
            font_name='Arial',
            font_size=32,
            bold=True,
            color=(80, 255, 160, 255),
            alignment=TextAnchor.MIDDLE_RIGHT,
            outline_width=1,
            outline_color=(0, 80, 40, 255),
            ui_layer=1,
        )
        renderer.register_object(best_time_obj)

        # ------------------------------------------------------------------
        # Start Game Button
        # ------------------------------------------------------------------
        def on_start() -> None:
            SceneManager.instance().load_scene('game')

        start_btn_obj = GameObject('StartButton')
        start_btn_obj.AddComponent(
            Button,
            anchor=UIAnchor(anchor_x=0.5, anchor_y=0.5, offset_x=0.0, offset_y=0, width=260, height=55),
            text='START GAME',
            font_name='Arial',
            font_size=20,
            bold=True,
            colors=ButtonColors(
                normal=(40, 100, 60, 220),
                hovered=(60, 160, 90, 240),
                pressed=(20, 60, 40, 255),
                disabled=(50, 50, 50, 150),
                text_normal=(200, 255, 220, 255),
                text_hovered=(255, 255, 255, 255),
                text_pressed=(180, 220, 200, 255),
                border=(80, 200, 120, 180),
                border_width=2,
                corner_radius=10,
            ),
            on_click=on_start,
            ui_layer=2,
        )
        renderer.register_object(start_btn_obj)

        # ------------------------------------------------------------------
        # Quit Button
        # ------------------------------------------------------------------
        def on_quit() -> None:
            pygame.quit()
            sys.exit(0)

        quit_btn_obj = GameObject('QuitButton')
        quit_btn_obj.AddComponent(
            Button,
            anchor=UIAnchor(anchor_x=0.5, anchor_y=0.5, offset_x=0.0, offset_y=70, width=260, height=45),
            text='QUIT',
            font_name='Arial',
            font_size=20,
            bold=True,
            colors=ButtonColors(
                normal=(80, 30, 30, 210),
                hovered=(140, 50, 50, 240),
                pressed=(50, 15, 15, 255),
                text_normal=(220, 160, 160, 255),
                text_hovered=(255, 200, 200, 255),
                border=(180, 80, 80, 160),
                border_width=1,
                corner_radius=8,
            ),
            on_click=on_quit,
            ui_layer=2,
        )
        renderer.register_object(quit_btn_obj)


def _format_time(t: float) -> str:
    """Formats a raw float time value into a digital clock string.

    Parameters
    ----------
    t : float
        The time in seconds to format.

    Returns
    -------
    str
        A formatted string in the ``'MM:SS.ms'`` format.
    """
    minutes = int(t) // 60
    seconds = int(t) % 60
    millis  = int((t - int(t)) * 100)
    return f'{minutes:02d}:{seconds:02d}.{millis:02d}'