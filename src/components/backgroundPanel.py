"""
Background-panel UI component — rounded rectangle fill with optional border.

Overview
--------
This module provides the :class:`BackgroundPanel` component, a
:class:`~core.ui.components.ui_component.UIComponent` that renders a
solid-colour rounded rectangle onto the screen surface.  It is typically used
as a decorative backing layer beneath other UI elements such as labels,
buttons, or inventory grids.

Responsibilities
----------------
* **Surface baking** — pre-renders the filled and bordered rectangle into a
  dedicated :class:`pygame.Surface` with per-pixel alpha (``SRCALPHA``) so
  semi-transparent panels composite correctly over the scene.
* **Resize handling** — rebuilds the baked surface whenever the screen is
  resized, keeping the panel geometry consistent with the resolved anchor
  rect.
* **Rendering** — blits the pre-baked surface to the screen at the correct
  anchor position during the UI render pass.

Design notes
------------
The panel surface is built once at construction time and rebuilt only on
:meth:`on_resize`, rather than redrawn every frame.  This makes
:meth:`UIRender` a single cheap :func:`pygame.Surface.blit` call regardless
of panel size, at the cost of an extra :class:`pygame.Surface` allocation
when the screen dimensions change.

The border, when enabled, is drawn as a separate
:func:`pygame.draw.rect` call on top of the fill.  Both share the same
:attr:`corner_radius` so the curves align perfectly.  If either
:attr:`border_width` is ``0`` or :attr:`border_color` is ``None``, the
border pass is skipped entirely.

Usage
-----
    Opaque dark panel anchored to a fixed rect:

    >>> panel = game_object.AddComponent(
    ...     BackgroundPanel,
    ...     anchor=UIAnchor.TOP_LEFT,
    ...     rect=pygame.Rect(10, 10, 300, 200),
    ...     color=(30, 30, 30, 220),
    ... )

    Panel with a rounded border:

    >>> panel = game_object.AddComponent(
    ...     BackgroundPanel,
    ...     anchor=UIAnchor.CENTER,
    ...     rect=pygame.Rect(0, 0, 400, 250),
    ...     color=(20, 20, 40, 200),
    ...     corner_radius=16,
    ...     border_color=(100, 120, 255, 255),
    ...     border_width=2,
    ...     ui_layer=1,
    ... )
"""

from __future__ import annotations

from typing import Tuple

import pygame

from core.ui.components.ui_component import UIComponent
from core.ui.ui_anchor import UIAnchor


class BackgroundPanel(UIComponent):
    """UI component that renders a rounded-rectangle panel with an optional border.

    :class:`BackgroundPanel` pre-bakes its visual representation into an
    ``SRCALPHA`` :class:`pygame.Surface` at construction time and on every
    subsequent resize event.  During the UI render pass only a single
    :meth:`~pygame.Surface.blit` is issued, keeping per-frame cost minimal.

    .. note::
        The border is only drawn when **both** :attr:`border_width` is greater
        than ``0`` and :attr:`border_color` is not ``None``.  Supplying only
        one of the two has no visible effect.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    anchor : UIAnchor or None, optional
        Anchor preset that controls how the panel is positioned relative to
        the screen.  Passed through to
        :class:`~core.ui.components.ui_component.UIComponent`.  Defaults to
        ``None``.
    rect : pygame.Rect or None, optional
        Size and position of the panel in screen space.  Interpretation
        depends on the chosen :class:`~core.ui.ui_anchor.UIAnchor`.  Defaults
        to ``None``.
    color : tuple
        Fill colour of the panel as an RGB or RGBA tuple
        (e.g. ``(30, 30, 30, 220)``).  Required.
    corner_radius : int, optional
        Radius in pixels applied to all four corners of the rounded rectangle.
        Defaults to ``12``.
    border_color : tuple or None, optional
        Colour of the border stroke as an RGB or RGBA tuple.  If ``None`` no
        border is drawn.  Defaults to ``None``.
    border_width : int, optional
        Thickness of the border stroke in pixels.  If ``0`` no border is
        drawn.  Defaults to ``0``.
    ui_layer : int, optional
        Render-order layer passed to
        :class:`~core.ui.components.ui_component.UIComponent`.  Higher values
        render on top.  Defaults to ``0``.

    Attributes
    ----------
    _color : tuple
        Fill colour supplied at construction time.
    _corner_radius : int
        Corner radius used for both fill and border passes.
    _border_color : tuple or None
        Border colour, or ``None`` if no border is desired.
    _border_width : int
        Border stroke thickness in pixels.
    """

    def __init__(
        self,
        game_object,
        *,
        anchor: UIAnchor = None,
        rect: pygame.Rect = None,
        color: Tuple,
        corner_radius: int = 12,
        border_color: Tuple = None,
        border_width: int = 0,
        ui_layer: int = 0,
    ) -> None:
        super().__init__(game_object, ui_layer=ui_layer, anchor=anchor)
        self._color = color
        self._corner_radius = corner_radius
        self._border_color = border_color
        self._border_width = border_width
        self._surface: pygame.Surface = None
        self._build()

    # ---------------------------------------------------------------------- #
    #  Resize handling                                                         #
    # ---------------------------------------------------------------------- #

    def on_resize(self, screen_w: int, screen_h: int) -> None:
        """Handle a screen-resize event by rebuilding the baked surface.

        Delegates anchor and rect recalculation to the parent
        :class:`~core.ui.components.ui_component.UIComponent`, then calls
        :meth:`_build` so the panel surface matches the updated dimensions.

        Parameters
        ----------
        screen_w : int
            New screen width in pixels.
        screen_h : int
            New screen height in pixels.
        """
        super().on_resize(screen_w, screen_h)
        self._build()

    # ---------------------------------------------------------------------- #
    #  Surface baking                                                          #
    # ---------------------------------------------------------------------- #

    def _build(self) -> None:
        """Pre-render the panel into a cached ``SRCALPHA`` surface.

        Creates a new :class:`pygame.Surface` sized to match the current
        anchor rect, draws the filled rounded rectangle, and — if both
        :attr:`_border_width` and :attr:`_border_color` are set — draws the
        border stroke on top.  The result is stored in :attr:`_surface` and
        reused by :meth:`UIRender` until the next :meth:`_build` call.
        """
        surf = pygame.Surface(self._rect.size, pygame.SRCALPHA)
        r = pygame.Rect(0, 0, *self._rect.size)
        pygame.draw.rect(surf, self._color, r, border_radius=self._corner_radius)
        if self._border_width > 0 and self._border_color:
            pygame.draw.rect(
                surf,
                self._border_color,
                r,
                width=self._border_width,
                border_radius=self._corner_radius,
            )
        self._surface = surf

    # ---------------------------------------------------------------------- #
    #  Rendering                                                               #
    # ---------------------------------------------------------------------- #

    def UIRender(self, screen: pygame.Surface) -> None:
        """Blit the pre-baked panel surface onto the screen.

        Called once per frame by the UI render pipeline.  The operation is a
        single :meth:`~pygame.Surface.blit` of the cached surface produced by
        :meth:`_build`, making per-frame cost independent of panel size or
        corner complexity.

        Parameters
        ----------
        screen : pygame.Surface
            The target display surface onto which the panel is composited.
        """
        if self._surface:
            screen.blit(self._surface, self._rect.topleft)