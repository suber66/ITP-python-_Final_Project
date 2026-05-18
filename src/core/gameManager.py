"""
GameManager — global singleton providing top-level access to core engine systems.

Overview
--------
This module provides the :class:`GameManager` class, a process-wide singleton
that acts as the central registry for the two most-referenced engine systems:
the :class:`~core.renderer.Renderer` and the active
:class:`~components.playerController.PlayerController`.  Any subsystem that
needs either reference can obtain it through :meth:`GameManager.instance`
without holding an explicit dependency on the object that constructed those
systems.

Responsibilities
----------------
* **Singleton enforcement** — guarantees that exactly one :class:`GameManager`
  exists for the lifetime of the process and raises immediately if a second
  construction is attempted.
* **Renderer registry** — stores the :class:`~core.renderer.Renderer`
  instance and exposes it to subsystems such as the physics debug overlay
  and the event pipeline in :meth:`~core.renderer.Renderer._handle_events`.
* **Player registry** — stores the active
  :class:`~components.playerController.PlayerController` so that any system
  can reach the player without scene-graph traversal.
* **Event distribution** — holds the list of pygame events polled in the
  current frame (``current_events``), written by the renderer and consumed by
  input-handling components.
* **Debug flags** — exposes ``_debug_show_colliders`` to toggle the collider
  overlay rendered by :meth:`~core.renderer.Renderer.run`.

Singleton pattern
-----------------
:class:`GameManager` follows the same pattern used throughout the engine: a
class-level ``_instance`` attribute is set on first construction and returned
by the :meth:`instance` classmethod on every subsequent call.  Constructing
the class directly when an instance already exists raises a :exc:`Exception`
to make accidental double-initialisation immediately visible.

Usage
-----
    >>> # Application entry point — construct once:
    >>> gm = GameManager()
    >>> gm.set_renderer(renderer)
    >>> gm.set_player(player_controller)

    >>> # Any subsystem — retrieve the singleton:
    >>> gm = GameManager.instance()
    >>> events = gm.current_events
    >>> gm._debug_show_colliders = True
"""

from __future__ import annotations

from components.playerController import PlayerController
from core.renderer import Renderer
from tools import Console


class GameManager:
    """Process-wide singleton that holds references to core engine systems.

    :class:`GameManager` is intended to be constructed exactly once at
    application startup.  All subsequent access should go through
    :meth:`instance`.  It stores the :class:`~core.renderer.Renderer`, the
    active :class:`~components.playerController.PlayerController`, the
    per-frame pygame event list, and the debug collider flag.

    .. note::
        Construct :class:`GameManager` directly only at the application entry
        point.  Every other call site should use :meth:`GameManager.instance`
        to retrieve the existing singleton.

    Attributes
    ----------
    renderer : Renderer or None
        The active :class:`~core.renderer.Renderer` instance.  ``None`` until
        :meth:`set_renderer` is called.
    player : PlayerController or None
        The active :class:`~components.playerController.PlayerController`.
        ``None`` until :meth:`set_player` is called.
    current_events : list[pygame.event.Event]
        The full list of pygame events polled during the current frame.
        Overwritten at the start of each frame by
        :meth:`~core.renderer.Renderer._handle_events` and consumed by
        input-handling components during ``Update``.
    _debug_show_colliders : bool
        When ``True``, the renderer draws axis-aligned collider outlines over
        the world layer at the end of each frame.  Defaults to ``False``.
    """

    _instance: 'GameManager | None' = None

    # ---------------------------------------------------------------------- #
    #  Singleton access                                                        #
    # ---------------------------------------------------------------------- #

    @classmethod
    def instance(cls) -> 'GameManager':
        """Return the singleton :class:`GameManager`, creating it if necessary.

        On the first call, constructs and caches a new :class:`GameManager`
        instance.  All subsequent calls return the same object.

        Returns
        -------
        GameManager
            The process-wide singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------------------------------------------------------------------- #
    #  Construction                                                            #
    # ---------------------------------------------------------------------- #

    def __init__(self) -> None:
        """Initialise the singleton and register it on the class.

        Raises
        ------
        Exception
            If a :class:`GameManager` instance already exists.  Use
            :meth:`instance` instead of constructing a second object.
        """
        if GameManager._instance is not None:
            raise Exception(
                'GameManager is a singleton! Use GameManager.instance()'
            )
        self.renderer: Renderer | None = None
        self.player: PlayerController | None = None
        self.current_events: list = []
        self._debug_show_colliders: bool = False
        GameManager._instance = self

    # ---------------------------------------------------------------------- #
    #  Registry setters                                                        #
    # ---------------------------------------------------------------------- #

    def set_renderer(self, renderer: Renderer) -> None:
        """Register the active renderer with the manager.

        Stores *renderer* so that subsystems can reach it via
        :attr:`GameManager.instance().renderer <renderer>` without holding a
        direct reference.

        Parameters
        ----------
        renderer : Renderer
            The :class:`~core.renderer.Renderer` instance created at
            application startup.
        """
        self.renderer = renderer

    def set_player(self, player: PlayerController) -> None:
        """Register the active player controller with the manager.

        Stores *player* so that any subsystem can reach the player without
        scene-graph traversal.

        Parameters
        ----------
        player : PlayerController
            The :class:`~components.playerController.PlayerController`
            component attached to the player game object.
        """
        self.player = player