"""
Component for rendering 2D sprites on the screen.

Overview
--------
This module provides the :class:`SpriteRenderer` class, which is responsible 
for drawing graphical resources (sprites) attached to game objects. It integrates 
tightly with the object's spatial data (Transform) and the rendering camera.

Two-Tier Scaling Architecture
---------------------------
To optimize performance, the component implements a two-tier surface caching system:

1. Base Scale (``_scaled_surface``): The original sprite scaled by 
   ``transform.size * transform.scale``. This is recalculated strictly only 
   when the object's intrinsic size or scale changes.
2. Camera Zoom (``_zoom_surface``): The base scaled surface further adjusted 
   by the current ``camera.zoom``. This is recalculated strictly only when 
   the camera's zoom level changes.

As a result, zooming the camera visually enlarges or shrinks the sprites 
on the screen efficiently without touching the original source image repeatedly.

Flip Support
------------
``flip_x`` and ``flip_y`` mirror the sprite horizontally or vertically.
Flipping is applied after scaling but before zoom, so it slots naturally
into the two-tier cache: the flip cache is invalidated only when the flip
flags or the base scaled surface change.

Usage
-----
    >>> from core.gameObject import GameObject
    >>> from core.spriteRenderer import SpriteRenderer
    >>> from sprite import Sprite
    >>> obj = GameObject()
    >>> my_sprite = Sprite.load("assets/player.png")
    >>> renderer = obj.AddComponent(SpriteRenderer, sprite=my_sprite, sorting_layer=1)
    >>> renderer.flip_x = True  # mirror horizontally
"""

import pygame
from typing import Optional, Any

from core.component import Component
from core.gameObject import GameObject


class SpriteRenderer(Component):
    """Component for rendering 2D sprites with caching, camera zoom and flip support.

    Parameters
    ----------
    game_object : GameObject
        The game object to which this component is attached.
    sprite : Sprite or Any, optional
        The graphical resource to render. Default is ``None``.
    sorting_layer : int, optional
        The layer index used to determine draw order. Default is 0.

    Attributes
    ----------
    sprite : Sprite or Any
        The current graphical resource assigned to this renderer.
    sorting_layer : int
        The sorting order index for the rendering pipeline.
    color : tuple of int
        Reserved RGB tint. Default is (255, 255, 255).
    flip_x : bool
        Mirror the sprite along the vertical axis (left ↔ right).
    flip_y : bool
        Mirror the sprite along the horizontal axis (top ↔ bottom).
    """

    def __init__(self, game_object: 'GameObject', sprite: Optional[Any] = None,
                 sorting_layer: int = 0) -> None:
        super().__init__(game_object)
        self.sprite = sprite
        self.sorting_layer = sorting_layer
        self.color = (255, 255, 255)

        self._source_surface: Optional[pygame.Surface] = None
        self._scaled_surface: Optional[pygame.Surface] = None  # scaled by Transform
        self._last_scale = None
        self._last_size = None

        self._flipped_surface: Optional[pygame.Surface] = None  # scaled + flipped
        self._last_flip_x: bool = False
        self._last_flip_y: bool = False

        self._zoom_surface: Optional[pygame.Surface] = None     # flipped + zoomed
        self._last_zoom: Optional[float] = None

        self._flip_x: bool = False
        self._flip_y: bool = False

    # ------------------------------------------------------------------
    # flip properties — invalidate caches on change
    # ------------------------------------------------------------------

    @property
    def flip_x(self) -> bool:
        return self._flip_x

    @flip_x.setter
    def flip_x(self, value: bool) -> None:
        if self._flip_x != value:
            self._flip_x = value
            self._rebuild_flipped()

    @property
    def flip_y(self) -> bool:
        return self._flip_y

    @flip_y.setter
    def flip_y(self, value: bool) -> None:
        if self._flip_y != value:
            self._flip_y = value
            self._rebuild_flipped()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def Awake(self) -> None:
        self._update_surface()
        self.transform.on_changed_callbacks.append(self._on_transform_changed)

    # ------------------------------------------------------------------
    # surface pipeline: source → scaled → flipped → zoomed
    # ------------------------------------------------------------------

    def _update_surface(self) -> None:
        """Call when sprite asset is swapped out entirely."""
        if self.sprite:
            raw = self.sprite.get_surface() if hasattr(self.sprite, 'get_surface') else self.sprite
            self._source_surface = raw
            self._last_scale = None
            self._last_size = None
            self._last_zoom = None
            self._rebuild_scaled()

    def _on_transform_changed(self) -> None:
        if self._source_surface is None:
            return
        if self.transform.scale != self._last_scale or self.transform.size != self._last_size:
            self._rebuild_scaled()

    def _rebuild_scaled(self) -> None:
        """Recalculate base scaled surface from source, then rebuild flip cache."""
        if self._source_surface is None:
            return
        w = max(1, int(self.transform.size.x * abs(self.transform.scale.x)))
        h = max(1, int(self.transform.size.y * abs(self.transform.scale.y)))
        self._scaled_surface = pygame.transform.scale(self._source_surface, (w, h))
        self._last_scale = self.transform.scale
        self._last_size = self.transform.size
        self._rebuild_flipped()

    def _rebuild_flipped(self) -> None:
        """Apply flip flags to the scaled surface. Invalidates zoom cache."""
        if self._scaled_surface is None:
            return
        if self._flip_x or self._flip_y:
            self._flipped_surface = pygame.transform.flip(
                self._scaled_surface, self._flip_x, self._flip_y)
        else:
            self._flipped_surface = self._scaled_surface  # no copy needed
        self._last_flip_x = self._flip_x
        self._last_flip_y = self._flip_y
        # invalidate zoom cache — base dimensions/pixels changed
        self._last_zoom = None

    def _get_render_surface(self, zoom: float) -> Optional[pygame.Surface]:
        """Return final surface adjusted for camera zoom (cached)."""
        base = self._flipped_surface or self._scaled_surface
        if base is None:
            return None
        if zoom == 1.0:
            return base
        if zoom != self._last_zoom:
            w = max(1, int(base.get_width() * zoom))
            h = max(1, int(base.get_height() * zoom))
            self._zoom_surface = pygame.transform.scale(base, (w, h))
            self._last_zoom = zoom
        return self._zoom_surface

    # ------------------------------------------------------------------
    # render
    # ------------------------------------------------------------------

    def Render(self, screen: pygame.Surface, camera: Any) -> None:
        if not self.enabled or self._scaled_surface is None:
            return
        zoom = getattr(camera, 'zoom', 1.0)
        surface = self._get_render_surface(zoom)
        if surface is None:
            return
        screen_pos = camera.WorldToScreen(self.transform.position)
        render_rect = surface.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))
        screen.blit(surface, render_rect)