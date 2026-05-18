"""
Graphical resource wrapper for component architecture.

Overview
--------
This module provides the :class:`Sprite` class, which encapsulates the 
loading, storage, and basic management of 2D images. The class is based 
on the Pygame library and serves as the primary carrier of graphical 
data for the ``SpriteRenderer`` component within an Entity-Component 
System (ECS) architecture.

The class handles safe file loading with extension validation and 
automatic pixel format conversion (including the alpha channel) to 
optimize rendering performance.

Usage
-----
    >>> from sprite import Sprite
    >>> # Recommended instantiation via the factory method:
    >>> player_sprite = Sprite.load("assets/player.png")
    >>> if player_sprite:
    ...     print(f"Loaded sprite size: {player_sprite.size.x}x{player_sprite.size.y}")
"""

from typing import Optional
import pygame
import os

from tools import Console
from geometry import Vector2


class Sprite:
    """Graphical resource container for rendering.

    Provides loading and caching of a :class:`pygame.Surface`, and 
    grants convenient access to image metadata (dimensions, path). 
    Optimized to work seamlessly with rendering components.

    Parameters
    ----------
    path : str
        The path to the source image file.
    surface : pygame.Surface
        A pre-loaded and prepared Pygame surface.

    Attributes
    ----------
    path : str
        The original path to the image file (read-only).
    surface : pygame.Surface
        The primary surface for rendering. Accessed by the 
        ``SpriteRenderer`` component (read-only).
    source : pygame.Surface
        An alias for :attr:`surface`. Kept for backward compatibility 
        with older code (read-only).
    size : Vector2
        The dimensions of the sprite in pixels (width, height) (read-only).

    Notes
    -----
    For instantiation, it is highly recommended to use the class method 
    :meth:`load` rather than calling the constructor directly. This ensures 
    safe loading and correct pixel format conversion.
    """
    
    #: Supported image file extensions.
    ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp"]
    
    def __init__(self, *, path: str, surface: pygame.Surface) -> None:
        self._path = path
        self._surface = surface

        t_s = self._surface.get_size()
        self._size = Vector2(t_s[0], t_s[1])
    
    # ------------------------------------------------------------------
    # Public API & Properties
    # ------------------------------------------------------------------
    
    @property
    def path(self) -> str:
        """str: The path to the file from which the sprite was loaded."""
        return self._path

    @property
    def surface(self) -> pygame.Surface:
        """pygame.Surface: The primary Pygame surface for rendering."""
        return self._surface

    @property
    def source(self) -> pygame.Surface:
        """pygame.Surface: Deprecated alias for :attr:`surface`."""
        return self._surface

    @property
    def size(self) -> Vector2:
        """Vector2: The image dimensions as a vector (width, height)."""
        return self._size
    
    def get_surface(self) -> pygame.Surface:
        """Returns the sprite's surface.

        An explicit getter providing a safe method to retrieve data 
        for rendering systems that prefer method calls over property access.

        Returns
        -------
        pygame.Surface
            The ready-to-render surface.
        """
        return self._surface
    
    # ------------------------------------------------------------------
    # Factory Methods
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str) -> Optional['Sprite']:
        """Loads a sprite from the specified file on disk.

        This method verifies the file's existence and the validity of its 
        extension. Upon successful loading, it automatically applies the 
        ``convert_alpha()`` method, which is critical for correct and fast 
        hardware transparency blending (especially for PNGs) in Pygame.

        Parameters
        ----------
        path : str
            The relative or absolute path to the image file.

        Returns
        -------
        Optional[Sprite]
            A new :class:`Sprite` instance upon successful loading. 
            Returns ``None`` if the file is not found, the format is 
            unsupported, or a Pygame error occurs.
            
        Notes
        -----
        Loading errors (invalid path, corrupted file) do not raise 
        exceptions; instead, they are logged via the :class:`Console.error` 
        subsystem. This prevents the entire engine from crashing due to 
        a missing texture.
        """
        if os.path.exists(path) and os.path.isfile(path):
            ext = os.path.splitext(path)[-1].lower()
            if ext in cls.ALLOWED_EXTENSIONS:
                try:
                    # convert_alpha() is critical for correct transparency rendering
                    surface = pygame.image.load(path).convert_alpha()
                    return cls(path=path, surface=surface)
                except pygame.error as e:
                    Console.error(f"Failed to load sprite from '{path}': {e}")
            else:
                Console.error(f"Unsupported extension '{ext}' for sprite: '{path}'")
        else:
            Console.error(f"Invalid path: file does not exist -> '{path}'")
            
        return None