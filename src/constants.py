"""
Global configuration and immutable constants for the engine.

Overview
--------
This module centralizes all hardcoded values, configuration parameters, 
and global states used across the game engine. Grouping these values 
into static classes ensures that "magic numbers" are avoided and makes 
it easy to tweak global settings (such as window resolution or base 
colors) from a single location.

Usage
-----
    >>> from constants import WindowConfig, Colors
    >>> print(WindowConfig.WIDTH)
    1280
    >>> bg = WindowConfig.BG_FILL_COLOR
"""

from utils import Color


class Colors:
    """Standardized predefined color palette.

    Provides quick access to commonly used instances of the :class:`Color` 
    object to avoid redundant memory allocations across the application.

    Attributes
    ----------
    WHITE : Color
        Pure white color with full opacity (255, 255, 255, 255).
    BLACK : Color
        Pure black color with full opacity (0, 0, 0, 255).
    """
    WHITE = Color(255, 255, 255, 255)
    BLACK = Color(0, 0, 0, 255)


class WindowConfig:
    """Core configuration settings for the main application window.

    Defines the spatial resolution, reference scaling constraints, 
    and rendering pipeline configurations (such as VSync and refresh rate).

    Attributes
    ----------
    WIDTH : int
        The actual physical width of the application window in pixels.
    HEIGHT : int
        The actual physical height of the application window in pixels.
    REFERENCE_WIDTH : int
        The base width used by UI canvas scalers to calculate dynamic layout proportions.
    REFERENCE_HEIGHT : int
        The base height used by UI canvas scalers to calculate dynamic layout proportions.
    MATCH_WIDTH_HEIGHT : float
        A blending factor (0.0 to 1.0) used by canvas scalers to determine 
        whether to scale UI elements based more on width (0.0) or height (1.0).
    BG_FILL_COLOR : Color
        The default background color used to clear the screen at the start of each frame.
    REFRESH_RATE : int
        The target frames-per-second (FPS) cap for the main game loop.
    VSYNC : int
        Vertical synchronization flag (1 to enable, 0 to disable).
    TITLE : str
        The text string displayed in the window's title bar.
    """
    WIDTH: int = 1280
    HEIGHT: int = 720
    REFERENCE_WIDTH: int = 1920
    REFERENCE_HEIGHT: int = 1080
    MATCH_WIDTH_HEIGHT: float = 0.5
    BG_FILL_COLOR: Color = Colors.BLACK
    REFRESH_RATE: int = 60
    VSYNC: int = 1
    TITLE: str = "Project Doomsday"


class World:
    """Global spatial and environmental constants.

    Attributes
    ----------
    GLOBAL_SCALE : int
        A universal multiplier applied to world-space coordinates or 
        rendering dimensions, ensuring consistent baseline scaling 
        for all entities within the game world.
    """
    GLOBAL_SCALE = 2