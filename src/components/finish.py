"""
FinishDetector — trigger-based run-completion component placed on the player.

Overview
--------
This module provides the :class:`Finish` component, a single-fire
:class:`~core.monoBehavior.MonoBehavior` that detects when the player
steps onto a finish tile (tile type ``3``), stops the run timer, persists
the best time via :class:`~managers.saveManager.SaveManager`, and
transitions to the menu scene via :class:`~managers.sceneManager.SceneManager`.

Responsibilities
----------------
* **Finish-tile detection** — responds to ``on_trigger_enter`` events and
  filters incoming colliders to those whose owner ``GameObject`` carries an
  ``is_finish == True`` attribute, ignoring all other trigger contacts.
* **One-shot guard** — sets :attr:`_triggered` to ``True`` on the first
  qualifying contact and short-circuits all subsequent calls, preventing the
  finish sequence from being initiated more than once per run even if the
  player lingers on the tile.
* **Timer finalisation** — stops the associated :class:`~components.timer.Timer`
  and captures the elapsed time only when the timer is actively running,
  defaulting to ``0.0`` otherwise.
* **Best-time persistence** — compares the current run's elapsed time
  against the stored best via :class:`~managers.saveManager.SaveManager`
  and overwrites it only when the new time is lower (or no previous best
  exists).
* **Scene transition** — delegates to
  :class:`~managers.sceneManager.SceneManager` to load the ``'menu'`` scene
  immediately after the timer and save operations complete.

Deferred imports
----------------
:mod:`managers.saveManager` and :mod:`managers.sceneManager` are imported
inside :meth:`~Finish._on_finish` rather than at module level to avoid
circular import issues that arise when these managers themselves depend on
components loaded during scene construction.

Usage
-----
    >>> player = GameObject('Player')
    >>> finish = player.AddComponent(
    ...     Finish,
    ...     timer=game_timer,
    ...     dungeon_manager=dm,
    ... )

    >>> # Dependencies may also be injected after construction:
    >>> finish.set_timer(game_timer)
    >>> finish.set_dungeon_manager(dm)
"""

from core.monoBehavior import MonoBehavior
from core.gameObject import GameObject
from physics.physicsManager import PhysicsLayers
from components.boxCollider import BoxCollider


class Finish(MonoBehavior):
    """Single-fire finish-tile detector attached to the player.

    :class:`Finish` listens for ``on_trigger_enter`` events, identifies
    contacts with finish tiles, and executes the end-of-run sequence exactly
    once per instance lifetime.  After :meth:`_on_finish` is called, the
    :attr:`_triggered` flag permanently suppresses further reactions even if
    the player re-enters the finish area.

    .. note::
        Both the timer and the dungeon manager may be ``None`` at
        construction time and injected later via :meth:`set_timer` and
        :meth:`set_dungeon_manager`.  This allows the component to be added
        before all game systems are fully initialised.  However, they must
        be set before the player can reach the finish tile or the timer will
        not be stopped and ``0.0`` will be recorded as the run time.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, supplied automatically
        by the component system.
    timer : Timer or None, optional
        The active :class:`~components.timer.Timer` tracking the current run.
        May be provided at construction time or set later via
        :meth:`set_timer`.  Defaults to ``None``.
    dungeon_manager : DungeonManager or None, optional
        The active :class:`~dungeon.dungeonManager.DungeonManager`.  Accepted
        for forward compatibility; not currently used in the finish sequence.
        May be set later via :meth:`set_dungeon_manager`.  Defaults to
        ``None``.

    Attributes
    ----------
    _timer : Timer or None
        Reference to the run timer.  Stopped in :meth:`_on_finish` if it is
        actively running at the moment the finish tile is contacted.
    _dungeon_manager : DungeonManager or None
        Reference to the dungeon manager.  Stored for use by potential future
        finish logic (e.g. unlocking rooms or recording completion state).
    _triggered : bool
        One-shot guard flag.  Set to ``True`` by :meth:`on_trigger_enter`
        on the first qualifying contact.  All subsequent calls to
        :meth:`on_trigger_enter` are no-ops while this flag is ``True``.
    """

    def __init__(
        self,
        game_object: GameObject,
        timer=None,
        dungeon_manager=None,
    ) -> None:
        super().__init__(game_object)
        self._timer            = timer
        self._dungeon_manager  = dungeon_manager
        self._triggered: bool  = False

    # ---------------------------------------------------------------- #
    #  Dependency injection                                              #
    # ---------------------------------------------------------------- #

    def set_timer(self, timer) -> None:
        """Inject or replace the run timer after construction.

        Parameters
        ----------
        timer : Timer
            The :class:`~components.timer.Timer` instance to associate with
            this component.  Replaces any timer supplied at construction time.
        """
        self._timer = timer

    def set_dungeon_manager(self, dm) -> None:
        """Inject or replace the dungeon manager after construction.

        Parameters
        ----------
        dm : DungeonManager
            The :class:`~dungeon.dungeonManager.DungeonManager` instance to
            associate with this component.  Replaces any manager supplied at
            construction time.
        """
        self._dungeon_manager = dm

    # ---------------------------------------------------------------- #
    #  Trigger handling                                                  #
    # ---------------------------------------------------------------- #

    def on_trigger_enter(self, other: BoxCollider) -> None:
        """Respond to a trigger-enter physics event.

        Called by the physics system whenever a collider overlaps the
        player's trigger zone.  Ignores the event if :attr:`_triggered` is
        already ``True`` or if the colliding object's ``GameObject`` does not
        carry an ``is_finish == True`` attribute.  On the first qualifying
        contact, sets :attr:`_triggered` and delegates to :meth:`_on_finish`.

        Parameters
        ----------
        other : BoxCollider
            The :class:`~components.boxCollider.BoxCollider` that entered
            the player's trigger zone.  Its owner ``GameObject`` is inspected
            for the ``is_finish`` attribute to confirm it is a finish tile.
        """
        if self._triggered:
            return

        obj = other.gameObject
        if not getattr(obj, 'is_finish', False):
            return

        self._triggered = True
        self._on_finish()

    # ---------------------------------------------------------------- #
    #  Finish sequence                                                   #
    # ---------------------------------------------------------------- #

    def _on_finish(self) -> None:
        """Execute the end-of-run sequence.

        Performs the following steps in order:

        1. **Stop the timer** — if :attr:`_timer` is set and currently
           running, calls :meth:`~components.timer.Timer.stop` and captures
           the elapsed time.  Defaults to ``0.0`` if the timer is absent or
           already stopped.
        2. **Persist the best time** — reads the stored ``'best_time'`` key
           via :class:`~managers.saveManager.SaveManager` and overwrites it
           with the current elapsed time only when the current run is faster
           or no previous best exists.
        3. **Load the menu scene** — calls
           :meth:`~managers.sceneManager.SceneManager.load_scene` with
           ``'menu'`` to end the dungeon session.

        .. note::
            :mod:`managers.saveManager` and :mod:`managers.sceneManager` are
            imported locally to avoid circular imports that can occur when
            these managers are initialised as part of the scene that also
            constructs this component.
        """
        from managers.saveManager import SaveManager
        from managers.sceneManager import SceneManager

        # Step 1: stop the timer
        elapsed = 0.0
        if self._timer and self._timer.running:
            elapsed = self._timer.stop()

        # Step 2: persist best time
        best = SaveManager.Get('best_time', None)
        if best is None or elapsed < best:
            SaveManager.Set('best_time', elapsed)

        # Step 3: transition to menu
        SceneManager.instance().load_scene('menu')