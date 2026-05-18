"""
Transform component — spatial state and change notification for game objects.

Overview
--------
This module provides the :class:`Transform` component, which is the canonical
authority for an object's spatial state within the scene.  Every
:class:`~core.gameObject.GameObject` owns exactly one :class:`Transform` and
uses it to read and write position, scale, rotation, and size.

Responsibilities
----------------
* **Spatial state** — stores and exposes the four fundamental spatial
  attributes of a game object: ``position``, ``scale``, ``rotation``,
  and ``size``.
* **Change notification** — maintains a list of zero-argument callbacks that
  are invoked whenever any spatial attribute is mutated through a property
  setter, allowing dependent systems (e.g. renderers, colliders) to react
  without polling.
* **Silent mutation** — exposes :meth:`_set_position_silent` for batch-move
  scenarios where firing callbacks on every intermediate position would be
  wasteful or incorrect.

Change notification
-------------------
Any system that needs to react to spatial changes should append a callable to
:attr:`on_changed_callbacks`.  All registered callbacks are called
synchronously, in registration order, immediately after the mutating setter
completes.  Callbacks are **not** invoked by :meth:`_set_position_silent`.

Usage
-----
    >>> from geometry import Vector2
    >>> go = GameObject('Player')
    >>> t = go.transform               # automatically attached by GameObject
    >>> t.position = Vector2(100, 200)
    >>> t.rotation = 45.0
    >>> t.scale = Vector2(2, 2)

    >>> # Subscribe to change events:
    >>> def on_moved():
    ...     print('object moved to', go.transform.position)
    >>> t.on_changed_callbacks.append(on_moved)

    >>> # Batch move without intermediate callbacks:
    >>> t._set_position_silent(Vector2(300, 400))
"""

from __future__ import annotations

from typing import Callable, List, Optional

from core.component import Component
from geometry import Vector2


class Transform(Component):
    """Component that owns the spatial state of a :class:`~core.gameObject.GameObject`.

    :class:`Transform` is attached automatically to every
    :class:`~core.gameObject.GameObject` at construction time and should not
    be added manually.  It is the single source of truth for an object's
    position, scale, rotation, and size, and broadcasts change notifications
    to any registered listeners whenever those values are mutated.

    .. note::
        Use :meth:`_set_position_silent` only in batch-move or physics-
        integration contexts where suppressing mid-step callbacks is
        intentional.  All other code should write to the :attr:`position`
        property directly so that dependent components stay in sync.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, injected automatically
        by the component system.
    init_pos : Vector2, optional
        Initial world position.  Defaults to ``Vector2(0, 0)``.
    init_scale : Vector2, optional
        Initial scale multiplier applied to the object's rendered size.
        Defaults to ``Vector2(1, 1)`` (no scaling).
    init_rot : float, optional
        Initial rotation in degrees, measured clockwise from the positive
        x-axis.  Defaults to ``0.0``.
    init_size : Vector2, optional
        Initial unscaled pixel dimensions of the object.
        Defaults to ``Vector2(32, 32)``.

    Attributes
    ----------
    on_changed_callbacks : list[Callable[[], None]]
        Mutable list of zero-argument callables invoked after any spatial
        attribute is changed through a property setter.  Subscribers are
        called in the order they were appended.  Cleared entries should be
        removed explicitly by the owning system.
    """

    def __init__(
        self,
        game_object: 'GameObject',
        init_pos: Optional[Vector2] = None,
        init_scale: Optional[Vector2] = None,
        init_rot: float = 0.0,
        init_size: Optional[Vector2] = None,
    ) -> None:
        super().__init__(game_object)
        self._position = init_pos if init_pos else Vector2(0, 0)
        self._scale = init_scale if init_scale else Vector2(1, 1)
        self._rotation = init_rot
        self._size = init_size if init_size else Vector2(32, 32)
        self.on_changed_callbacks: List[Callable[[], None]] = []

    # ---------------------------------------------------------------------- #
    #  Properties                                                              #
    # ---------------------------------------------------------------------- #

    @property
    def position(self) -> Vector2:
        """World-space position of the object.

        Setting this property fires all :attr:`on_changed_callbacks`.

        :type: :class:`~geometry.Vector2`
        """
        return self._position

    @position.setter
    def position(self, value: Vector2) -> None:
        self._position = value
        self._notify_changed()

    @property
    def scale(self) -> Vector2:
        """Scale multiplier applied on top of the object's base :attr:`size`.

        A value of ``Vector2(1, 1)`` means no scaling; ``Vector2(2, 2)``
        doubles the rendered dimensions on both axes.  Setting this property
        fires all :attr:`on_changed_callbacks`.

        :type: :class:`~geometry.Vector2`
        """
        return self._scale

    @scale.setter
    def scale(self, value: Vector2) -> None:
        self._scale = value
        self._notify_changed()

    @property
    def rotation(self) -> float:
        """Clockwise rotation of the object in degrees.

        ``0.0`` means no rotation (aligned with the positive x-axis).
        Setting this property fires all :attr:`on_changed_callbacks`.

        :type: float
        """
        return self._rotation

    @rotation.setter
    def rotation(self, value: float) -> None:
        self._rotation = value
        self._notify_changed()

    @property
    def size(self) -> Vector2:
        """Unscaled pixel dimensions of the object ``(width, height)``.

        This represents the object's intrinsic size before :attr:`scale` is
        applied.  Setting this property fires all :attr:`on_changed_callbacks`.

        :type: :class:`~geometry.Vector2`
        """
        return self._size

    @size.setter
    def size(self, value: Vector2) -> None:
        self._size = value
        self._notify_changed()

    # ---------------------------------------------------------------------- #
    #  Notification helpers                                                    #
    # ---------------------------------------------------------------------- #

    def _notify_changed(self) -> None:
        """Invoke all registered change callbacks synchronously.

        Called internally by every property setter after the backing field
        has been updated.  Callbacks receive no arguments; they are expected
        to read the new state directly from the :class:`Transform` if needed.
        """
        for callback in self.on_changed_callbacks:
            callback()

    def _set_position_silent(self, value: Vector2) -> None:
        """Set :attr:`position` without firing :attr:`on_changed_callbacks`.

        Intended for batch-move operations (e.g. physics integration steps,
        room-transition teleportation) where triggering callbacks on every
        intermediate position would cause unnecessary or incorrect side
        effects.  Callers are responsible for ensuring that dependent systems
        are notified or refreshed after the batch operation completes.

        Parameters
        ----------
        value : Vector2
            The new world-space position to assign directly to the backing
            field.
        """
        self._position = value