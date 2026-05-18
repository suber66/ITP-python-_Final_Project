"""
Door component — trigger-based room transition for dungeon entrances.

Overview
--------
This module provides the :class:`Door` component, a lightweight
:class:`~core.monoBehavior.MonoBehavior` that listens for physics trigger
events and delegates room transitions to the
:class:`~dungeon.dungeonManager.DungeonManager`.

Responsibilities
----------------
* **Trigger detection** — responds to overlap events fired by
  :class:`~physics.physicsManager.PhysicsManager` when the player collider
  enters or exits the door's trigger zone.
* **Layer filtering** — ignores any collider that does not belong to the
  ``PLAYER`` physics layer, ensuring doors only react to the player.
* **Transition delegation** — forwards a directional transition request to
  the registered :class:`~dungeon.dungeonManager.DungeonManager` on enter,
  leaving all room-loading and player-placement logic to that component.
* **Cooldown** — enforces a brief per-door cooldown (default 30 frames)
  after a successful transition to prevent the same overlap event from
  firing a second transition in the destination room.

Design notes
------------
:class:`Door` is purely reactive — it contains no polling or distance-check
logic.  All overlap detection is performed upstream by
:meth:`~physics.physicsManager.PhysicsManager.process_triggers`, which calls
:meth:`~Door.on_trigger_enter` and :meth:`~Door.on_trigger_exit` directly.

The cooldown on :class:`Door` is intentionally independent from the
transition cooldown maintained by :class:`~dungeon.dungeonManager.DungeonManager`.
Together they form a two-layer guard: the manager prevents rapid successive
room swaps, while the door prevents the entering collider from immediately
re-firing in the new room before the player has moved away.

Usage
-----
    Doors are typically constructed and attached by :class:`~dungeon.room.Room`
    when it reads door tiles from the room matrix:

    >>> door_obj = GameObject('door_up')
    >>> door = door_obj.AddComponent(
    ...     Door,
    ...     direction='up',
    ...     dungeon_manager=dm,
    ... )

    The :class:`~physics.physicsManager.PhysicsManager` then calls the
    trigger hooks automatically — no manual invocation is required:

    >>> # Called automatically when the player collider overlaps the door:
    >>> door.on_trigger_enter(player_collider)

    >>> # Called automatically when the player collider leaves the door:
    >>> door.on_trigger_exit(player_collider)
"""

from __future__ import annotations

from components.boxCollider import BoxCollider
from core.gameObject import GameObject
from core.monoBehavior import MonoBehavior
from physics.physicsManager import PhysicsLayers


class Door(MonoBehavior):
    """MonoBehavior component that triggers a dungeon room transition on player contact.

    :class:`Door` is intended to be attached to a door tile game object inside
    a :class:`~dungeon.room.Room`.  It relies on the physics system to call
    :meth:`on_trigger_enter` and :meth:`on_trigger_exit`; no manual update
    polling is performed beyond decrementing the internal cooldown counter.

    .. note::
        A :class:`~dungeon.dungeonManager.DungeonManager` reference must be
        supplied at construction time.  Without it, all trigger callbacks
        become no-ops and no transition will occur.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    direction : str, optional
        The cardinal direction this door leads toward.  Must be one of
        ``'up'``, ``'down'``, ``'left'``, ``'right'``.  Defaults to
        ``'up'``.
    dungeon_manager : DungeonManager or None, optional
        The active :class:`~dungeon.dungeonManager.DungeonManager` instance.
        Transition calls are forwarded to this object.  Defaults to ``None``.

    Attributes
    ----------
    direction : str
        The cardinal direction this door leads toward.
    """

    def __init__(
        self,
        game_object: GameObject,
        direction: str = 'up',
        dungeon_manager=None,
    ) -> None:
        super().__init__(game_object)
        self.direction = direction
        self._dungeon_manager = dungeon_manager
        self._cooldown: int = 0

    # ---------------------------------------------------------------------- #
    #  MonoBehavior lifecycle                                                  #
    # ---------------------------------------------------------------------- #

    def Update(self) -> None:
        """Called once per frame by the component system.

        Decrements the per-door transition cooldown counter when it is active.
        """
        if self._cooldown > 0:
            self._cooldown -= 1

    # ---------------------------------------------------------------------- #
    #  Trigger callbacks                                                       #
    # ---------------------------------------------------------------------- #

    def on_trigger_enter(self, other_collider: BoxCollider) -> None:
        """Handle a collider entering this door's trigger zone.

        Called automatically by
        :meth:`~physics.physicsManager.PhysicsManager.process_triggers` when
        *other_collider* begins overlapping the door's trigger collider.
        Requests a room transition from the registered
        :class:`~dungeon.dungeonManager.DungeonManager` if all of the
        following conditions are met:

        * The per-door cooldown is not active.
        * *other_collider* belongs to the ``PLAYER`` physics layer.
        * A :class:`~dungeon.dungeonManager.DungeonManager` is registered.

        On a successful transition the cooldown is reset to 30 frames to
        prevent an immediate re-trigger in the destination room.

        Parameters
        ----------
        other_collider : BoxCollider
            The collider that entered the trigger zone.
        """
        if self._cooldown > 0:
            return
        if other_collider.layer != PhysicsLayers.PLAYER:
            return
        if self._dungeon_manager is None:
            return
        success = self._dungeon_manager.transition_to_room(self.direction)
        if success:
            self._cooldown = 30

    def on_trigger_exit(self, other_collider: BoxCollider) -> None:
        """Handle a collider leaving this door's trigger zone.

        Called automatically by
        :meth:`~physics.physicsManager.PhysicsManager.process_triggers` when
        *other_collider* stops overlapping the door's trigger collider.
        Currently a no-op for non-player colliders; reserved for future
        logic such as re-enabling a temporarily disabled player collider.

        Parameters
        ----------
        other_collider : BoxCollider
            The collider that exited the trigger zone.
        """
        if other_collider.layer != PhysicsLayers.PLAYER:
            return
        if self._dungeon_manager is None:
            return