"""
Canvas — screen-space UI layer that composites UI elements over the world.

Overview
--------
This module provides the :class:`Canvas` component, which acts as the root
container for a screen-space UI layer.  It owns an ordered list of
:class:`~core.ui.components.ui_component.UIComponent` instances, drives their
per-frame update and render calls, and self-registers with the
:class:`~core.renderer.Renderer` so that UI is always drawn on top of the
world layer without requiring manual wiring at the call site.

Responsibilities
----------------
* **Renderer integration** — registers and unregisters itself with the
  :class:`~core.renderer.Renderer` automatically in response to
  :meth:`OnEnable` and :meth:`OnDisable` lifecycle events.
* **Element management** — maintains an ordered list of
  :class:`~core.ui.components.ui_component.UIComponent` instances sorted by
  ``ui_layer``, updated at each :meth:`register` call.
* **Resize propagation** — forwards ``VIDEORESIZE`` notifications from the
  renderer to every enabled child element via :meth:`on_resize`.
* **Update pipeline** — calls :meth:`~core.ui.components.ui_component.UIComponent.UIUpdate`
  on each active element once per frame so that widgets can process input and
  update internal state.
* **Render pipeline** — calls :meth:`~core.ui.components.ui_component.UIComponent.UIRender`
  on each active element in ``ui_layer`` order, compositing UI on top of the
  world after all world render calls have completed.

Element registration
--------------------
:class:`~core.ui.components.ui_component.UIComponent` subclasses are expected
to call :meth:`register` on their owning canvas when they are enabled, and
:meth:`unregister` when they are disabled or destroyed.  The
:class:`~core.ui.components.ui_component.CanvasRegistry` global lookup table
is updated in parallel so that components can locate their canvas without a
direct reference.

Elements are kept sorted by ``ui_layer`` after every :meth:`register` call.
Lower ``ui_layer`` values are rendered first (further back within the canvas);
higher values are drawn on top.

Lifecycle
---------
:meth:`OnEnable` registers the canvas with the renderer and the
:class:`~core.ui.components.ui_component.CanvasRegistry`.
:meth:`OnDisable` reverses both registrations.
:meth:`OnDestroy` delegates to :meth:`OnDisable` to guarantee clean teardown
even when the owning game object is destroyed directly.

Usage
-----
    >>> hud_obj = GameObject('HUD')
    >>> canvas = hud_obj.AddComponent(Canvas, sort_layer=1000)
    >>> renderer.register_object(hud_obj)

    >>> # UIComponent subclasses register themselves:
    >>> health_bar = health_obj.AddComponent(HealthBar)
    >>> health_bar.canvas.register(health_bar)

    >>> # Called automatically by Renderer each frame:
    >>> canvas.Update()
    >>> canvas.Render(screen, camera)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

import pygame

from core.component import Component
from core.gameObject import GameObject

if TYPE_CHECKING:
    from core.ui.components.ui_component import UIComponent


class Canvas(Component):
    """Screen-space UI container that owns, updates, and renders UI elements.

    :class:`Canvas` is attached to a dedicated game object and registered with
    the :class:`~core.renderer.Renderer` automatically when enabled.  All
    :class:`~core.ui.components.ui_component.UIComponent` instances that
    belong to this canvas call :meth:`register` on construction and
    :meth:`unregister` on teardown.

    .. note::
        The ``_camera`` parameter accepted by :meth:`Render` is intentionally
        ignored.  Canvas elements are positioned in screen space via
        :class:`~core.ui.ui_anchor.UIAnchor` and do not participate in world-
        space projection.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    sort_layer : int, optional
        Draw-order priority used by the :class:`~core.renderer.Renderer` to
        sort multiple canvases relative to one another.  Higher values are
        drawn later (on top).  Defaults to ``1000``.

    Attributes
    ----------
    sort_layer : int
        Draw-order priority among canvases registered with the renderer.
    """

    def __init__(self, game_object: GameObject, sort_layer: int = 1000) -> None:
        super().__init__(game_object)
        self.sort_layer: int = sort_layer
        self._ui_elements: List['UIComponent'] = []

    # ---------------------------------------------------------------------- #
    #  Resize propagation                                                      #
    # ---------------------------------------------------------------------- #

    def on_resize(self, screen_w: int, screen_h: int) -> None:
        """Propagate a window resize event to all enabled child elements.

        Called by the :class:`~core.renderer.Renderer` whenever a
        ``VIDEORESIZE`` event is received.  Forwards the new dimensions to
        every enabled :class:`~core.ui.components.ui_component.UIComponent`
        so that each widget can recompute its layout via its own
        ``on_resize`` implementation.

        Parameters
        ----------
        screen_w : int
            New display surface width in pixels.
        screen_h : int
            New display surface height in pixels.
        """
        for el in self._ui_elements:
            if el.enabled:
                el.on_resize(screen_w, screen_h)

    # ---------------------------------------------------------------------- #
    #  Lifecycle                                                               #
    # ---------------------------------------------------------------------- #

    def OnEnable(self) -> None:
        """Register this canvas with the renderer and the global registry.

        Called automatically by the component system when the canvas or its
        owner game object is enabled.  Registers the canvas with
        :class:`~core.renderer.Renderer` (so it receives :meth:`Update` and
        :meth:`Render` calls each frame) and with
        :class:`~core.ui.components.ui_component.CanvasRegistry` (so UI
        components can locate it by type).

        Does nothing if :class:`~core.gameManager.GameManager` has no renderer
        attached yet.
        """
        from core.gameManager import GameManager
        from core.ui.components.ui_component import CanvasRegistry
        gm = GameManager._instance
        if gm and gm.renderer:
            gm.renderer.register_canvas(self)
        CanvasRegistry.register(self)

    def OnDisable(self) -> None:
        """Unregister this canvas from the renderer and the global registry.

        Called automatically by the component system when the canvas or its
        owner game object is disabled.  Reverses both registrations performed
        by :meth:`OnEnable` so the canvas no longer receives frame callbacks
        or appears in global lookups.

        Does nothing if :class:`~core.gameManager.GameManager` has no renderer
        attached yet.
        """
        from core.gameManager import GameManager
        from core.ui.components.ui_component import CanvasRegistry
        gm = GameManager._instance
        if gm and gm.renderer:
            gm.renderer.unregister_canvas(self)
        CanvasRegistry.unregister(self)

    def OnDestroy(self) -> None:
        """Clean up registrations when the owner game object is destroyed.

        Delegates to :meth:`OnDisable` to guarantee that the canvas is removed
        from the renderer and the global registry even when the owning
        :class:`~core.gameObject.GameObject` is destroyed directly rather than
        disabled first.
        """
        self.OnDisable()

    # ---------------------------------------------------------------------- #
    #  Element management                                                      #
    # ---------------------------------------------------------------------- #

    def register(self, element: 'UIComponent') -> None:
        """Add a UI element to this canvas and maintain ``ui_layer`` sort order.

        Appends *element* to the internal element list if it is not already
        present, then re-sorts the list by ``ui_layer`` in ascending order so
        that elements with lower values are rendered first (further back within
        the canvas).

        Typically called by :class:`~core.ui.components.ui_component.UIComponent`
        subclasses from their own ``OnEnable`` method.

        Parameters
        ----------
        element : UIComponent
            The UI component to add to this canvas.
        """
        if element not in self._ui_elements:
            self._ui_elements.append(element)
            self._ui_elements.sort(key=lambda e: e.ui_layer)

    def unregister(self, element: 'UIComponent') -> None:
        """Remove a UI element from this canvas.

        Removes *element* from the internal element list if it is present.
        Does nothing if *element* is not currently registered.  Typically
        called by :class:`~core.ui.components.ui_component.UIComponent`
        subclasses from their own ``OnDisable`` or ``OnDestroy`` method.

        Parameters
        ----------
        element : UIComponent
            The UI component to remove from this canvas.
        """
        if element in self._ui_elements:
            self._ui_elements.remove(element)

    # ---------------------------------------------------------------------- #
    #  Per-frame pipeline                                                      #
    # ---------------------------------------------------------------------- #

    def Update(self) -> None:
        """Drive the per-frame update of all active UI elements.

        Iterates a snapshot of the element list and calls
        :meth:`~core.ui.components.ui_component.UIComponent.UIUpdate` on each
        element that is both enabled and whose owner game object is active.
        Iterating a snapshot (``list(self._ui_elements)``) allows elements to
        safely register or unregister themselves during their own ``UIUpdate``
        without invalidating the iteration.

        Called automatically by :class:`~core.renderer.Renderer` once per
        frame, after world ``Update`` and before world rendering.
        """
        for el in list(self._ui_elements):
            if el.enabled and el.gameObject.activeSelf:
                el.UIUpdate()

    def Render(self, screen: pygame.Surface, _camera) -> None:
        """Draw all active UI elements onto *screen*.

        Iterates a snapshot of the element list in ``ui_layer`` order and
        calls :meth:`~core.ui.components.ui_component.UIComponent.UIRender`
        on each element that is both enabled and whose owner game object is
        active.  The ``_camera`` argument is accepted for interface
        compatibility with the renderer but is intentionally unused — canvas
        elements are positioned in screen space and require no world-to-screen
        projection.

        Called automatically by :class:`~core.renderer.Renderer` once per
        frame, after all world render components have been drawn.

        Parameters
        ----------
        screen : pygame.Surface
            The render target, typically the display surface.
        _camera : object
            Ignored.  Accepted only to match the renderer's
            ``component.Render(screen, camera)`` call signature.
        """
        for el in list(self._ui_elements):
            if el.enabled and el.gameObject.activeSelf:
                el.UIRender(screen)