"""
Tilemap renderer — bakes tile game objects into a single surface for efficient rendering.

Overview
--------
This module provides the :class:`TilemapRenderer` component, which composites
a collection of tile :class:`~core.gameObject.GameObject` instances into a
single pre-rendered :class:`pygame.Surface` (the *baked* surface) and exposes
it through the standard ``Render(screen, camera)`` interface shared by all
renderers in the engine.

Responsibilities
----------------
* **Baking** — iterates over a list of tile objects, reads each tile's
  :class:`~core.spriteRenderer.SpriteRenderer` scaled surface, and composites
  all tiles onto one atlas surface aligned to world-space coordinates.
* **World-space anchoring** — tracks the world-space position of the baked
  surface's top-left corner so that :meth:`Render` can convert it to screen
  space via the camera without knowing anything about individual tiles.
* **Zoom caching** — maintains a zoom-scaled copy of the baked surface and
  regenerates it only when the camera zoom level changes, avoiding a
  ``smoothscale`` call every frame.
* **Seam prevention** — adds a 1-pixel padding border around the composited
  surface to eliminate sub-pixel seam artefacts that appear at non-integer
  zoom levels.

Baking
------
Call :meth:`bake` once after all tile sprites have been assigned and scaled.
The method computes the tightest bounding rectangle that encloses every tile,
composites their scaled surfaces into a single atlas, and caches the result.
Subsequent calls to :meth:`Render` draw only this atlas — no per-tile draw
calls occur at runtime.

Re-baking is required whenever tile positions or sprites change (e.g. after a
room reload).  The zoom cache is invalidated automatically on each :meth:`bake`
call.

Zoom caching
------------
When the camera zoom is anything other than ``1.0``, the baked surface is
scaled via :func:`pygame.transform.smoothscale` to suppress seam artefacts.
The result is stored in ``_baked_zoom`` and reused for all subsequent frames
at the same zoom level.  A new scaled copy is produced only when
``camera.zoom`` changes.

Sorting layer
-------------
``sorting_layer`` defaults to ``-10`` so that the tilemap is drawn beneath
all dynamic game objects, which typically occupy layer ``0`` or above.  The
renderer system is expected to sort renderers by this value before issuing
draw calls.

Usage
-----
    >>> renderer = room_object.AddComponent(TilemapRenderer, sorting_layer=-10)

    >>> # After assigning sprites to all tiles:
    >>> renderer.bake(room.tiles)

    >>> # Called automatically each frame by the renderer system:
    >>> renderer.Render(screen, camera)
"""

from __future__ import annotations

from typing import Any, List, Optional

import pygame

from core.component import Component
from geometry import Vector2


class TilemapRenderer(Component):
    """Component that bakes tile game objects into a single surface for efficient rendering.

    :class:`TilemapRenderer` composites a list of tile
    :class:`~core.gameObject.GameObject` instances into one
    :class:`pygame.Surface` and exposes it through the standard
    ``Render(screen, camera)`` interface, making it a drop-in peer of
    :class:`~core.spriteRenderer.SpriteRenderer` from the renderer system's
    perspective.

    .. note::
        :meth:`bake` must be called (and must complete successfully) before
        :meth:`Render` will produce any output.  Calling :meth:`Render` before
        baking is safe and silently produces no draw calls.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    sorting_layer : int, optional
        Draw-order priority passed to the renderer system.  Lower values are
        drawn first (further back).  Defaults to ``-10`` so the tilemap
        underdraws all dynamic objects.

    Attributes
    ----------
    sorting_layer : int
        Draw-order priority used by the renderer system to sort this component
        relative to others before issuing draw calls.
    """

    def __init__(self, game_object: 'GameObject', sorting_layer: int = -10) -> None:
        super().__init__(game_object)
        self.sorting_layer = sorting_layer
        self._baked: Optional[pygame.Surface] = None
        self._baked_zoom: Optional[pygame.Surface] = None
        self._last_zoom: Optional[float] = None
        self._world_topleft: Vector2 = Vector2(0, 0)

    # ---------------------------------------------------------------------- #
    #  Baking                                                                  #
    # ---------------------------------------------------------------------- #

    def bake(self, tiles: List) -> None:
        """Composite all tile surfaces into a single cached atlas surface.

        Computes the world-space bounding rectangle that encloses every tile,
        then blits each tile's scaled surface onto a single
        :class:`pygame.Surface` aligned to that rectangle.  The result is
        stored internally and used by :meth:`Render` on every subsequent frame.

        A 1-pixel padding border is added on all sides of the atlas to prevent
        sub-pixel seam artefacts at non-integer camera zoom levels.

        Any previously cached zoom-scaled surface is invalidated so that
        :meth:`Render` recomputes it at the current zoom level on the next
        frame.

        The method is a no-op when *tiles* is empty.

        Parameters
        ----------
        tiles : list[GameObject]
            Ordered collection of tile game objects to bake.  Each object is
            expected to carry a :class:`~core.spriteRenderer.SpriteRenderer`
            component whose ``_scaled_surface`` is up to date.  Tiles whose
            renderer is missing or whose scaled surface is ``None`` after the
            forced update are silently skipped during compositing.
        """
        if not tiles:
            return

        from core.spriteRenderer import SpriteRenderer

        # Ensure all scaled surfaces are up to date before sampling dimensions.
        for tile in tiles:
            sr = tile.GetComponent(SpriteRenderer)
            if sr and sr._scaled_surface is None:
                sr._update_surface()

        # Rendered pixel dimensions per tile: size * abs(scale).
        def tw(t): return max(1, int(t.transform.size.x * abs(t.transform.scale.x)))
        def th(t): return max(1, int(t.transform.size.y * abs(t.transform.scale.y)))

        # Top-left world corner of each tile (transform.position is the centre).
        def topleft_x(t): return int(t.transform.position.x) - tw(t) // 2
        def topleft_y(t): return int(t.transform.position.y) - th(t) // 2

        tops = [(topleft_x(t), topleft_y(t)) for t in tiles]

        min_x = min(p[0] for p in tops)
        min_y = min(p[1] for p in tops)
        max_x = max(p[0] + tw(t) for t, p in zip(tiles, tops))
        max_y = max(p[1] + th(t) for t, p in zip(tiles, tops))

        PAD = 1
        surf_w = max_x - min_x + PAD * 2
        surf_h = max_y - min_y + PAD * 2
        surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)

        for tile, (tx, ty) in zip(tiles, tops):
            sr = tile.GetComponent(SpriteRenderer)
            if sr is None or sr._scaled_surface is None:
                continue
            surf.blit(sr._scaled_surface, (tx - min_x + PAD, ty - min_y + PAD))

        self._baked = surf
        # Anchor the world-space origin of the atlas, accounting for the
        # padding border that shifts all content PAD pixels to the right and
        # down relative to the surface's top-left pixel.
        self._world_topleft = Vector2(min_x - PAD, min_y - PAD)
        self._last_zoom = None
        self._baked_zoom = None

    # ---------------------------------------------------------------------- #
    #  Rendering                                                               #
    # ---------------------------------------------------------------------- #

    def Render(self, screen: pygame.Surface, camera: Any) -> None:
        """Draw the baked atlas surface onto *screen* through *camera*.

        Converts :attr:`_world_topleft` from world space to screen space using
        ``camera.WorldToScreen``, then blits the atlas at the resulting
        position.

        When ``camera.zoom`` differs from ``1.0``, the atlas is scaled via
        :func:`pygame.transform.smoothscale` before blitting to suppress seam
        artefacts.  The scaled result is cached in ``_baked_zoom`` and reused
        on subsequent frames at the same zoom level; a new scaled copy is
        produced only when the zoom value changes.

        The method is a no-op when the component is disabled or :meth:`bake`
        has not yet been called successfully.

        Parameters
        ----------
        screen : pygame.Surface
            The render target, typically the display surface.
        camera : Any
            An object that exposes a ``zoom`` attribute (``float``) and a
            ``WorldToScreen(world_pos: Vector2) -> Vector2`` method.
        """
        if not self.enabled or self._baked is None:
            return

        zoom = getattr(camera, 'zoom', 1.0)

        if zoom != 1.0:
            if zoom != self._last_zoom:
                w = max(1, int(self._baked.get_width() * zoom))
                h = max(1, int(self._baked.get_height() * zoom))
                self._baked_zoom = pygame.transform.smoothscale(self._baked, (w, h))
                self._last_zoom = zoom
            draw_surf = self._baked_zoom
        else:
            draw_surf = self._baked

        screen_pos = camera.WorldToScreen(self._world_topleft)
        screen.blit(draw_surf, (int(screen_pos.x), int(screen_pos.y)))