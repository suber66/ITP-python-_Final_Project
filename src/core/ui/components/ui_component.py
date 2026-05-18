"""
UIComponent and CanvasRegistry — base class and global registry for screen-space UI widgets.

Overview
--------
This module provides two cooperating classes:

* :class:`UIComponent` — the abstract base for all screen-space UI widgets.
  It manages anchor-based layout, canvas registration, and the
  ``UIUpdate`` / ``UIRender`` per-frame pipeline.
* :class:`CanvasRegistry` — a process-wide registry of active
  :class:`~core.ui.canvas.Canvas` instances, used as a fallback when a
  :class:`UIComponent` cannot locate a canvas on its own game object.

Responsibilities
----------------
* **Anchor layout** — resolves a :class:`~core.ui.ui_anchor.UIAnchor`
  descriptor to a :class:`pygame.Rect` at construction time and re-resolves
  it on every ``VIDEORESIZE`` event, keeping the element's bounding rect
  up to date without storing raw pixel positions.
* **Canvas auto-discovery** — on ``Start`` and ``OnEnable``, each
  :class:`UIComponent` attempts to find a :class:`~core.ui.canvas.Canvas`
  on its own game object before falling back to the primary canvas in
  :class:`CanvasRegistry`, making explicit canvas wiring optional for
  common single-canvas setups.
* **Canvas lifecycle** — registers and unregisters the component with its
  owning canvas in response to component lifecycle events (``Start``,
  ``OnEnable``, ``OnDisable``, ``OnDestroy``), ensuring the canvas's
  element list stays consistent without manual management.
* **Extensibility** — exposes :meth:`UIComponent.UIUpdate` (no-op default)
  and the abstract :meth:`UIComponent.UIRender` for subclasses to override,
  matching the ``Update`` / ``Render`` convention used throughout the engine.

Canvas discovery order
-----------------------
When :meth:`UIComponent._register_to_canvas` runs it resolves the canvas in
the following priority order:

1. A :class:`~core.ui.canvas.Canvas` component on the **same game object** as
   the :class:`UIComponent`.
2. The **primary canvas** returned by :meth:`CanvasRegistry.get_primary`
   (the first canvas registered globally).
3. No registration if neither source yields a canvas.

Use :meth:`UIComponent.bind_canvas` to bypass auto-discovery and attach the
component to a specific canvas explicitly.

Dirty flag convention
---------------------
If a subclass exposes a ``_dirty`` attribute, :meth:`UIComponent.on_resize`
sets it to ``True`` whenever the resolved rect changes.  Subclasses can use
this flag to defer expensive surface re-renders until the next
``UIRender`` call rather than rebuilding immediately on resize.

Usage
-----
    >>> class MyButton(UIComponent):
    ...     def UIRender(self, screen: pygame.Surface) -> None:
    ...         pygame.draw.rect(screen, (80, 80, 200), self.rect, border_radius=6)

    >>> anchor = UIAnchor(anchor_x=0.5, anchor_y=0.9, width=160.0, height=40.0)
    >>> btn_obj = GameObject('PlayButton')
    >>> btn = btn_obj.AddComponent(MyButton, ui_layer=10, anchor=anchor)

    >>> # Explicit canvas binding (optional — auto-discovery handles the common case):
    >>> btn.bind_canvas(hud_canvas)

    >>> # CanvasRegistry — used internally; also available for lookups:
    >>> primary = CanvasRegistry.get_primary()
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Optional

import pygame

from core.component import Component
from core.ui.ui_anchor import UIAnchor

if TYPE_CHECKING:
    from core.ui.canvas import Canvas


class UIComponent(Component):
    """Abstract base component for all screen-space UI widgets.

    :class:`UIComponent` handles the boilerplate common to every UI element:
    anchor-based rect resolution, automatic canvas discovery and registration,
    and resize propagation.  Concrete widgets subclass it and implement
    :meth:`UIRender` (and optionally override :meth:`UIUpdate`).

    .. note::
        Subclasses must implement :meth:`UIRender`.  All other methods have
        safe defaults and may be overridden as needed.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    ui_layer : int, optional
        Draw-order priority within the owning canvas.  Lower values are drawn
        first (further back); higher values are drawn on top.  Defaults to
        ``0``.
    anchor : UIAnchor or None, optional
        Layout descriptor used to compute :attr:`rect`.  If ``None``, the
        rect is initialised to ``Rect(0, 0, 0, 0)`` and must be set manually
        by the subclass.  Defaults to ``None``.

    Attributes
    ----------
    ui_layer : int
        Draw-order priority within the owning canvas.  The canvas re-sorts its
        element list by this value after each :meth:`~core.ui.canvas.Canvas.register`
        call.
    rect : pygame.Rect
        Read-only bounding rectangle in screen space, resolved from
        :attr:`_anchor` at construction time and updated by :meth:`on_resize`.
        Access via the :attr:`rect` property.
    """

    def __init__(
        self,
        game_object: 'GameObject',
        ui_layer: int = 0,
        anchor: Optional[UIAnchor] = None,
    ) -> None:
        super().__init__(game_object)
        self.ui_layer: int = ui_layer
        self._anchor: Optional[UIAnchor] = anchor
        self._canvas: Optional['Canvas'] = None
        self._rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        screen = pygame.display.get_surface()
        if screen and anchor:
            self._rect = anchor.resolve(screen.get_width(), screen.get_height())

    # ---------------------------------------------------------------------- #
    #  Properties                                                              #
    # ---------------------------------------------------------------------- #

    @property
    def rect(self) -> pygame.Rect:
        """Current bounding rectangle in screen space.

        Derived from :attr:`_anchor` and updated automatically on
        ``VIDEORESIZE`` events via :meth:`on_resize`.  Read-only; modify the
        :class:`~core.ui.ui_anchor.UIAnchor` fields and call
        :meth:`on_resize` to reposition the element.

        :type: :class:`pygame.Rect`
        """
        return self._rect

    # ---------------------------------------------------------------------- #
    #  Layout                                                                  #
    # ---------------------------------------------------------------------- #

    def on_resize(self, screen_w: int, screen_h: int) -> None:
        """Recompute :attr:`rect` for the new window dimensions.

        Resolves :attr:`_anchor` against the supplied screen size.  If the
        resulting rect differs from the current one, updates :attr:`_rect`
        and, if the subclass exposes a ``_dirty`` attribute, sets it to
        ``True`` so that the next :meth:`UIRender` call can rebuild any
        cached surfaces.

        Does nothing if no anchor was provided at construction.

        Parameters
        ----------
        screen_w : int
            New display surface width in pixels.
        screen_h : int
            New display surface height in pixels.
        """
        if self._anchor:
            new_rect = self._anchor.resolve(screen_w, screen_h)
            if new_rect != self._rect:
                self._rect = new_rect
                if hasattr(self, '_dirty'):
                    self._dirty = True

    # ---------------------------------------------------------------------- #
    #  Canvas management                                                       #
    # ---------------------------------------------------------------------- #

    def _register_to_canvas(self) -> None:
        """Discover and register with the appropriate canvas.

        Searches for a :class:`~core.ui.canvas.Canvas` on the same game
        object first; falls back to :meth:`CanvasRegistry.get_primary` if
        none is found.  If a canvas is located and differs from the currently
        registered one, unregisters from the old canvas before registering
        with the new one.

        Does nothing if no canvas can be found through either source.
        """
        from core.ui.canvas import Canvas
        canvas = self.gameObject.GetComponent(Canvas)
        if canvas is None:
            canvas = CanvasRegistry.get_primary()
        if canvas and canvas is not self._canvas:
            if self._canvas:
                self._canvas.unregister(self)
            self._canvas = canvas
            self._canvas.register(self)

    def bind_canvas(self, canvas: 'Canvas') -> None:
        """Explicitly attach this component to a specific canvas.

        Bypasses the auto-discovery logic of :meth:`_register_to_canvas`.
        Unregisters from the current canvas (if any) before registering with
        *canvas*.  Use this when the component's game object does not share a
        canvas with the intended parent, or when the default primary-canvas
        fallback is not appropriate.

        Parameters
        ----------
        canvas : Canvas
            The :class:`~core.ui.canvas.Canvas` to register with.
        """
        if self._canvas:
            self._canvas.unregister(self)
        self._canvas = canvas
        canvas.register(self)

    # ---------------------------------------------------------------------- #
    #  Lifecycle                                                               #
    # ---------------------------------------------------------------------- #

    def Start(self) -> None:
        """Register with a canvas on first activation.

        Called once by the component system after all components on the owner
        game object have been initialised.  Delegates to
        :meth:`_register_to_canvas` so the element is ready to receive
        :meth:`UIUpdate` and :meth:`UIRender` calls from the first frame.
        """
        self._register_to_canvas()

    def OnEnable(self) -> None:
        """Re-register with a canvas when the component or its owner is enabled.

        Called by the component system whenever the component transitions from
        disabled to enabled.  Delegates to :meth:`_register_to_canvas` so
        that the element re-enters the canvas's render pipeline after having
        been absent.
        """
        self._register_to_canvas()

    def OnDisable(self) -> None:
        """Unregister from the canvas when the component or its owner is disabled.

        Called by the component system whenever the component transitions from
        enabled to disabled.  Removes the element from the owning canvas's
        element list so it no longer receives ``UIUpdate`` or ``UIRender``
        calls while inactive.
        """
        if self._canvas:
            self._canvas.unregister(self)

    def OnDestroy(self) -> None:
        """Unregister from the canvas when the owner game object is destroyed.

        Ensures the element is removed from the canvas's element list even
        when the owning :class:`~core.gameObject.GameObject` is destroyed
        directly rather than disabled first, preventing stale references in
        the canvas's render pipeline.
        """
        if self._canvas:
            self._canvas.unregister(self)

    # ---------------------------------------------------------------------- #
    #  Per-frame pipeline                                                      #
    # ---------------------------------------------------------------------- #

    def UIUpdate(self) -> None:
        """Per-frame update hook for input handling and state changes.

        Called once per frame by :meth:`~core.ui.canvas.Canvas.Update` before
        any rendering occurs.  The default implementation is a no-op; subclasses
        override this to handle mouse events, animate values, or update
        internal state.
        """
        pass

    @abstractmethod
    def UIRender(self, screen: pygame.Surface) -> None:
        """Draw this UI element onto *screen*.

        Called once per frame by :meth:`~core.ui.canvas.Canvas.Render` after
        all world rendering is complete.  Implementations should draw into
        :attr:`rect` using standard :mod:`pygame` draw calls or
        :meth:`pygame.Surface.blit`.

        Parameters
        ----------
        screen : pygame.Surface
            The render target, typically the display surface.
        """


class CanvasRegistry:
    """Process-wide registry of active :class:`~core.ui.canvas.Canvas` instances.

    :class:`CanvasRegistry` maintains a flat list of every canvas that has
    been enabled since application startup.  It is used by
    :meth:`UIComponent._register_to_canvas` as a fallback source when a
    :class:`UIComponent` cannot locate a canvas on its own game object,
    removing the need to pass canvas references explicitly in simple
    single-canvas setups.

    All methods are classmethods; :class:`CanvasRegistry` is never
    instantiated.

    Attributes
    ----------
    _canvases : list[Canvas]
        Ordered list of registered canvases.  The first entry is returned by
        :meth:`get_primary`.
    """

    _canvases: list = []

    @classmethod
    def register(cls, canvas: 'Canvas') -> None:
        """Add *canvas* to the registry if it is not already present.

        Parameters
        ----------
        canvas : Canvas
            The :class:`~core.ui.canvas.Canvas` to register.
        """
        if canvas not in cls._canvases:
            cls._canvases.append(canvas)

    @classmethod
    def unregister(cls, canvas: 'Canvas') -> None:
        """Remove *canvas* from the registry if it is present.

        Parameters
        ----------
        canvas : Canvas
            The :class:`~core.ui.canvas.Canvas` to unregister.
        """
        if canvas in cls._canvases:
            cls._canvases.remove(canvas)

    @classmethod
    def get_primary(cls) -> Optional['Canvas']:
        """Return the first registered canvas, or ``None`` if the registry is empty.

        The primary canvas is the one registered earliest — typically the main
        HUD canvas created at scene load.  Used by
        :meth:`UIComponent._register_to_canvas` as a fallback when no canvas
        is found on the component's own game object.

        Returns
        -------
        Canvas or None
            The first entry in the registry, or ``None`` if no canvases are
            registered.
        """
        return cls._canvases[0] if cls._canvases else None