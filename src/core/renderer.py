"""
Renderer — main loop, scene object management, and layered rendering pipeline.

Overview
--------
This module provides the :class:`Renderer` class, which owns the pygame
display surface, drives the main game loop, and orchestrates the full
per-frame pipeline: event handling, world update, physics, UI update, world
render, debug overlays, and UI render.

Responsibilities
----------------
* **Display initialisation** — creates the pygame window and clock from the
  supplied configuration parameters.
* **Object management** — maintains the authoritative list of scene
  :class:`~core.gameObject.GameObject` instances via a deferred add/remove
  queue that is flushed once per frame, preventing mutation of the scene list
  during iteration.
* **Render list** — builds and caches a sorted flat list of
  :class:`~core.spriteRenderer.SpriteRenderer` and
  :class:`~core.tilemapRenderer.TilemapRenderer` components, rebuilt lazily
  whenever the scene changes.
* **Camera management** — discovers the active :class:`~core.camera.Camera`
  automatically from registered objects and falls back to a pass-through
  dummy camera when none is present.
* **Canvas / UI rendering** — maintains a sorted list of
  :class:`~core.ui.canvas.Canvas` components and renders them after all world
  objects so that UI is always drawn on top.
* **Debug overlay** — optionally renders collider outlines over the world layer
  when the :class:`~core.gameManager.GameManager` debug flag is set.
* **Scene lifecycle** — exposes :meth:`clear_scene` for scene managers to tear
  down all objects, canvases, and physics state atomically at the end of a
  frame.

Main loop pipeline
------------------
Each iteration of the loop in :meth:`run` executes the following stages in
order:

1. **Clock tick** — caps the frame rate to :attr:`refresh_rate`.
2. **Flush pending** — processes deferred object additions and removals.
3. **Event handling** — dispatches pygame events; returns ``False`` on quit.
4. **World update** — calls ``Update()`` on every active scene object.
5. **Physics** — triggers the :class:`~physics.physicsManager.PhysicsManager`
   to process collider overlap callbacks.
6. **LateUpdate** — calls ``LateUpdate()`` on every active scene object.
7. **Canvas update** — calls ``Update()`` on every enabled canvas so that UI
   widgets can process input events.
8. **World render** — fills the background, rebuilds the render list if dirty,
   then draws each visible render component through the main camera.
9. **Debug colliders** — draws collider outlines when the debug flag is active.
10. **UI render** — draws all enabled canvases on top of the world layer.
11. **Display flip** — presents the composed frame.
12. **Scene transitions** — flushes any pending scene switch queued during the
    frame.

Deferred object management
---------------------------
:meth:`register_object` and :meth:`unregister_object` do not mutate the scene
list immediately; instead they append to ``_pending_add`` and
``_pending_remove``.  :meth:`_flush_pending` processes both queues at the
start of each frame.  This guarantees that objects destroyed or spawned during
``Update`` do not corrupt the iteration in progress.

Render list caching
-------------------
``_render_components`` is a sorted flat list of renderer components built by
:meth:`_rebuild_render_list`.  It is marked dirty (``_render_list_dirty =
True``) whenever the scene object list changes, and rebuilt lazily at the
start of the world-render stage.  Components are sorted by ``sorting_layer``
so that tilemap backgrounds (layer ``-10``) are drawn before sprites (layer
``0`` and above).

Canvas sorting
--------------
Canvases are kept sorted by ``sort_layer`` at insertion time.  They are
updated and rendered in that order every frame, ensuring predictable stacking
of overlapping UI panels.

Usage
-----
    >>> renderer = Renderer(
    ...     width=1280,
    ...     height=720,
    ...     refresh_rate=60,
    ...     vsync=1,
    ...     title='My Game',
    ...     flags=0,
    ... )
    >>> renderer.register_object(player_game_object)
    >>> renderer.register_object(camera_game_object)
    >>> renderer.run()           # blocks until the window is closed

    >>> # Scene transition — called by SceneManager, not directly:
    >>> renderer.clear_scene()
    >>> renderer.register_object(new_scene_root)
"""

from __future__ import annotations

import sys
from typing import List, Optional

import pygame

import constants
from core.camera import Camera
from core.gameObject import GameObject
from core.spriteRenderer import SpriteRenderer
from core.tilemapRenderer import TilemapRenderer
from geometry import Vector2
from tools import Console


class Renderer:
    """Owns the pygame display and drives the per-frame update and render pipeline.

    :class:`Renderer` is typically instantiated once at application startup and
    its :meth:`run` method called to enter the blocking game loop.  All scene
    objects are registered through :meth:`register_object`; the renderer
    discovers cameras, canvases, and render components automatically.

    .. note::
        :meth:`run` does not return under normal operation.  It calls
        :func:`sys.exit` when the pygame ``QUIT`` event is received.

    Parameters
    ----------
    width : int
        Width of the display surface in pixels.
    height : int
        Height of the display surface in pixels.
    refresh_rate : int
        Target frame rate in frames per second, enforced via
        :meth:`pygame.time.Clock.tick`.
    vsync : int
        Vertical sync flag passed to :func:`pygame.display.set_mode`.
        ``1`` enables vsync; ``0`` disables it.
    title : str
        Window caption shown in the title bar.
    flags : int
        Additional pygame display flags (e.g. ``pygame.RESIZABLE``) OR-ed
        together and forwarded to :func:`pygame.display.set_mode`.

    Attributes
    ----------
    width : int
        Current display width in pixels.  Updated on ``VIDEORESIZE`` events.
    height : int
        Current display height in pixels.  Updated on ``VIDEORESIZE`` events.
    refresh_rate : int
        Target frame rate in frames per second.
    vsync : int
        Vertical sync flag used when recreating the display surface.
    title : str
        Window caption.
    flags : int
        Pygame display flags used when recreating the display surface.
    clock : pygame.time.Clock
        Clock instance used to enforce :attr:`refresh_rate`.
    """

    def __init__(
        self,
        *,
        width: int,
        height: int,
        refresh_rate: int,
        vsync: int,
        title: str,
        flags: int,
    ) -> None:
        self.width = width
        self.height = height
        self.refresh_rate = refresh_rate
        self.vsync = vsync
        self.title = title
        self.flags = flags

        if not pygame.get_init():
            pygame.init()

        self.__screen = pygame.display.set_mode(
            (self.width, self.height), vsync=vsync, flags=flags)
        pygame.display.set_caption(self.title)
        self.clock = pygame.time.Clock()

        self.__scene_objects: List[GameObject] = []
        self._render_components: list = []
        self._render_list_dirty: bool = True
        self._main_camera: Optional[Camera] = None
        self._pending_add: List[GameObject] = []
        self._pending_remove: List[GameObject] = []
        self._canvases: list = []

    # ---------------------------------------------------------------------- #
    #  Object management                                                       #
    # ---------------------------------------------------------------------- #

    def register_object(self, obj: GameObject) -> None:
        """Enqueue a game object to be added to the scene.

        The object is not added immediately; it is appended to a pending queue
        and inserted into the scene list at the start of the next frame by
        :meth:`_flush_pending`.  Camera and :class:`~core.ui.canvas.Canvas`
        components attached to *obj* are detected and registered automatically
        during the flush.

        Does nothing (and logs an error) if *obj* is not a
        :class:`~core.gameObject.GameObject`.

        Parameters
        ----------
        obj : GameObject
            The game object to add to the scene.
        """
        if isinstance(obj, GameObject):
            self._pending_add.append(obj)
        else:
            Console.error(f'Cannot register {type(obj).__name__}.')

    def unregister_object(self, obj: GameObject) -> None:
        """Enqueue a game object to be removed from the scene.

        The object is not removed immediately; it is appended to a pending
        removal queue and removed from the scene list at the start of the next
        frame by :meth:`_flush_pending`.

        Parameters
        ----------
        obj : GameObject
            The game object to remove from the scene.
        """
        self._pending_remove.append(obj)

    def mark_render_dirty(self) -> None:
        """Signal that the render component list must be rebuilt next frame.

        Call this whenever a renderer component is enabled, disabled, or its
        ``sorting_layer`` changes outside of a scene-object add/remove
        operation.  :meth:`_rebuild_render_list` will be invoked lazily at
        the start of the next world-render stage.
        """
        self._render_list_dirty = True

    # ---------------------------------------------------------------------- #
    #  Canvas management                                                       #
    # ---------------------------------------------------------------------- #

    def register_canvas(self, canvas) -> None:
        """Register a :class:`~core.ui.canvas.Canvas` component for UI rendering.

        Inserts *canvas* into the internal canvas list if it is not already
        present, re-sorts the list by ``sort_layer`` to maintain draw order,
        and registers the canvas with the global
        :class:`~core.ui.components.ui_component.CanvasRegistry`.

        Parameters
        ----------
        canvas : Canvas
            The canvas component to register.
        """
        from core.ui.components.ui_component import CanvasRegistry
        if canvas not in self._canvases:
            self._canvases.append(canvas)
            self._canvases.sort(key=lambda c: c.sort_layer)
            CanvasRegistry.register(canvas)

    def unregister_canvas(self, canvas) -> None:
        """Remove a :class:`~core.ui.canvas.Canvas` component from UI rendering.

        Removes *canvas* from the internal canvas list and unregisters it from
        the global :class:`~core.ui.components.ui_component.CanvasRegistry`.
        Does nothing if *canvas* is not currently registered.

        Parameters
        ----------
        canvas : Canvas
            The canvas component to unregister.
        """
        from core.ui.components.ui_component import CanvasRegistry
        if canvas in self._canvases:
            self._canvases.remove(canvas)
            CanvasRegistry.unregister(canvas)

    def clear_canvases(self) -> None:
        """Unregister and discard all canvases.

        Unregisters every canvas from the global
        :class:`~core.ui.components.ui_component.CanvasRegistry` and clears
        the internal canvas list.  Called by :meth:`clear_scene` during scene
        transitions.
        """
        from core.ui.components.ui_component import CanvasRegistry
        for c in list(self._canvases):
            CanvasRegistry.unregister(c)
        self._canvases.clear()

    # ---------------------------------------------------------------------- #
    #  Internal helpers                                                        #
    # ---------------------------------------------------------------------- #

    def _flush_pending(self) -> None:
        """Process deferred object additions and removals.

        Removes all objects in ``_pending_remove`` from the scene list, then
        adds all objects in ``_pending_add``.  Auto-detects
        :class:`~core.camera.Camera` and :class:`~core.ui.canvas.Canvas`
        components on newly added objects and registers them.

        Sets ``_render_list_dirty`` to ``True`` if the scene list changed so
        that the render component list is rebuilt at the start of the next
        world-render stage.
        """
        changed = False
        for obj in self._pending_remove:
            if obj in self.__scene_objects:
                self.__scene_objects.remove(obj)
                changed = True
        self._pending_remove.clear()

        for obj in self._pending_add:
            if obj not in self.__scene_objects:
                self.__scene_objects.append(obj)
                changed = True
                cam = obj.GetComponent(Camera)
                if cam and cam.enabled and self._main_camera is None:
                    self._main_camera = cam
                from core.ui.canvas import Canvas
                canvas = obj.GetComponent(Canvas)
                if canvas and canvas.enabled:
                    self.register_canvas(canvas)
        self._pending_add.clear()

        if changed:
            self._render_list_dirty = True

    def _rebuild_render_list(self) -> None:
        """Rebuild and sort the flat list of active renderer components.

        Iterates all active scene objects and collects enabled
        :class:`~core.tilemapRenderer.TilemapRenderer` and
        :class:`~core.spriteRenderer.SpriteRenderer` components (in that
        priority order per object).  The resulting list is sorted by
        ``sorting_layer`` in ascending order so that lower-layer components
        (e.g. tilemaps at ``-10``) are drawn before higher-layer ones.

        Clears ``_render_list_dirty`` on completion.
        """
        components = []
        for obj in self.__scene_objects:
            if not obj.activeSelf:
                continue
            tr = obj.GetComponent(TilemapRenderer)
            if tr and tr.enabled:
                components.append(tr)
                continue
            sr = obj.GetComponent(SpriteRenderer)
            if sr and sr.enabled:
                components.append(sr)
        components.sort(key=lambda c: getattr(c, 'sorting_layer', 0))
        self._render_components = components
        self._render_list_dirty = False

    def _get_main_camera(self) -> Camera:
        """Return the active main camera, falling back to a dummy if none exists.

        Returns the cached :attr:`_main_camera` if it is still enabled and its
        owner is active.  Otherwise, scans the scene for the first enabled
        :class:`~core.camera.Camera` component and caches it.  If no camera
        is found, returns a :class:`DummyCamera` that applies no transform
        (``zoom = 1.0``, identity ``WorldToScreen``).

        Returns
        -------
        Camera
            An active camera (or dummy camera) suitable for passing to
            renderer ``Render`` calls.
        """
        if (self._main_camera and self._main_camera.enabled
                and self._main_camera.gameObject.activeSelf):
            return self._main_camera
        for obj in self.__scene_objects:
            if not obj.activeSelf:
                continue
            cam = obj.GetComponent(Camera)
            if cam and cam.enabled:
                self._main_camera = cam
                return cam
        return self._make_dummy_camera()

    @staticmethod
    def _make_dummy_camera():
        """Construct a pass-through camera substitute.

        Returns a lightweight anonymous object with ``zoom = 1.0`` and a
        ``WorldToScreen`` method that returns world coordinates unchanged.
        Used as a safe fallback when no :class:`~core.camera.Camera` is
        present in the scene.

        Returns
        -------
        DummyCamera
            A minimal camera-interface-compatible object.
        """
        class DummyCamera:
            zoom = 1.0
            def WorldToScreen(self, pos: Vector2) -> Vector2:
                return pos
        return DummyCamera()

    def _is_visible(self, component, camera) -> bool:
        """Check whether a render component's bounds intersect the screen.

        :class:`~core.tilemapRenderer.TilemapRenderer` components are always
        considered visible because their atlas may extend well beyond the
        camera-space equivalent of any single tile position.

        For :class:`~core.spriteRenderer.SpriteRenderer` components, converts
        the component's world-space position to screen space and tests whether
        the scaled surface rectangle overlaps the display rectangle, with a
        1-pixel tolerance to avoid popping at the exact edge.

        Parameters
        ----------
        component : TilemapRenderer or SpriteRenderer
            The render component to test.
        camera : Camera
            The active camera, used for the world-to-screen conversion and
            zoom factor.

        Returns
        -------
        bool
            ``True`` if the component should be drawn this frame; ``False``
            if it is entirely off-screen and can be skipped.
        """
        if isinstance(component, TilemapRenderer):
            return True
        surf = getattr(component, '_scaled_surface', None)
        if surf is None:
            return False
        pos = camera.WorldToScreen(component.transform.position)
        zoom = getattr(camera, 'zoom', 1.0)
        hw = surf.get_width() * zoom / 2 + 1
        hh = surf.get_height() * zoom / 2 + 1
        return (pos.x + hw > 0 and pos.x - hw < self.width
                and pos.y + hh > 0 and pos.y - hh < self.height)

    def _handle_events(self) -> bool:
        """Poll and dispatch all pending pygame events.

        Forwards the full event list to
        :class:`~core.gameManager.GameManager` for game-side polling.
        Handles ``QUIT`` (returns ``False`` to signal loop termination) and
        ``VIDEORESIZE`` (recreates the display surface at the new size,
        notifies all canvases via ``on_resize``, and updates any
        :class:`~core.canvasScaler.CanvasScaler` components in the scene).

        Returns
        -------
        bool
            ``True`` if the loop should continue; ``False`` if a ``QUIT``
            event was received and the application should exit.
        """
        from core.gameManager import GameManager
        events = pygame.event.get()
        if GameManager._instance:
            GameManager.instance().current_events = events
        for event in events:
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.VIDEORESIZE:
                self.width, self.height = event.w, event.h
                self.__screen = pygame.display.set_mode(
                    (self.width, self.height), vsync=self.vsync, flags=self.flags
                )
                for canvas in self._canvases:
                    canvas.on_resize(self.width, self.height)
        return True

    # ---------------------------------------------------------------------- #
    #  Main loop                                                               #
    # ---------------------------------------------------------------------- #

    def run(self) -> None:
        """Enter the blocking main game loop.

        Executes the full per-frame pipeline (see module docstring for the
        ordered stage list) until a ``QUIT`` event is received, at which point
        :func:`pygame.quit` is called and the process exits via
        :func:`sys.exit`.

        The background fill colour is read from
        ``constants.WindowConfig.BG_FILL_COLOR`` at the start of the loop;
        if that value exposes a ``to_tuple()`` method it is called, otherwise
        black ``(0, 0, 0)`` is used as a fallback.

        .. note::
            This method never returns under normal operation.
        """
        fill_color = (
            constants.WindowConfig.BG_FILL_COLOR.to_tuple()
            if hasattr(constants.WindowConfig.BG_FILL_COLOR, 'to_tuple')
            else (0, 0, 0)
        )

        while True:
            self.clock.tick(self.refresh_rate)
            self._flush_pending()

            if not self._handle_events():
                pygame.quit()
                sys.exit(0)

            # --- World update ---
            for obj in self.__scene_objects:
                if obj.activeSelf:
                    obj.Update()

            # --- Physics ---
            from physics.physicsManager import PhysicsManager
            PhysicsManager.instance().process_triggers()

            # --- LateUpdate ---
            for obj in self.__scene_objects:
                if obj.activeSelf:
                    obj.LateUpdate()

            # --- Canvas update (UI input processing) ---
            for canvas in self._canvases:
                if canvas.enabled and canvas.gameObject.activeSelf:
                    canvas.Update()

            # --- World render ---
            self.__screen.fill(fill_color)
            if self._render_list_dirty:
                self._rebuild_render_list()

            main_camera = self._get_main_camera()
            for rc in self._render_components:
                if not rc.enabled or not rc.gameObject.activeSelf:
                    continue
                if self._is_visible(rc, main_camera):
                    rc.Render(self.__screen, main_camera)

            # --- Debug colliders ---
            from core.gameManager import GameManager
            gm = GameManager._instance
            if gm and getattr(gm, '_debug_show_colliders', False):
                from physics.physicsManager import PhysicsManager
                zoom = getattr(main_camera, 'zoom', 1.0)
                for col in PhysicsManager.instance()._colliders:
                    if not col.enabled:
                        continue
                    r = col.rect
                    tl = main_camera.WorldToScreen(Vector2(r.left, r.top))
                    draw_rect = pygame.Rect(
                        int(tl.x), int(tl.y),
                        int(r.width * zoom), int(r.height * zoom))
                    color = (0, 120, 255) if col.is_trigger else (255, 50, 50)
                    pygame.draw.rect(self.__screen, color, draw_rect, 1)

            # --- UI / Canvas render (always on top) ---
            for canvas in self._canvases:
                if canvas.enabled and canvas.gameObject.activeSelf:
                    canvas.Render(self.__screen, main_camera)

            pygame.display.flip()

            # --- Scene transitions (safe: end of frame) ---
            from managers.sceneManager import SceneManager
            if SceneManager._instance:
                SceneManager.instance().flush_pending()

    # ---------------------------------------------------------------------- #
    #  Scene lifecycle helpers                                                 #
    # ---------------------------------------------------------------------- #

    def clear_scene(self) -> None:
        """Tear down all scene objects, canvases, and physics state.

        Destroys every registered game object, clears all internal object and
        render lists, resets the main camera reference, unregisters all
        canvases, and clears the physics collider and spatial grid.

        Intended to be called by :class:`~managers.sceneManager.SceneManager`
        at the end of a frame (during ``flush_pending``) so that no live
        iteration is in progress when the lists are mutated.

        .. warning::
            After this call the scene is empty.  New objects must be
            registered before the next :meth:`run` iteration will render
            anything.
        """
        for obj in list(self.__scene_objects):
            obj.Destroy()
        self.__scene_objects.clear()
        self._pending_add.clear()
        self._pending_remove.clear()
        self._render_components.clear()
        self._render_list_dirty = True
        self._main_camera = None
        self.clear_canvases()
        from physics.physicsManager import PhysicsManager
        pm = PhysicsManager.instance()
        pm._colliders.clear()
        pm._spatial._grid.clear()