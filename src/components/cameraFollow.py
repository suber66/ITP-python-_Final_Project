"""
Camera-follow component — smooth lerp-based tracking of a target game object.

Overview
--------
This module provides the :class:`CameraFollow` component, a minimal
:class:`~core.monoBehavior.MonoBehavior` that moves the owning game object
(typically a camera) toward a designated target each frame using linear
interpolation (lerp).

Responsibilities
----------------
* **Target tracking** — reads the world position of the registered target
  game object every late-update tick.
* **Smooth interpolation** — applies a frame-rate-dependent lerp step
  controlled by :attr:`lerp_speed` so the camera eases toward the target
  rather than snapping to it instantly.
* **Late evaluation** — runs in :meth:`LateUpdate` to guarantee that all
  game-object positions for the current frame have already been committed
  before the camera repositions itself, preventing a one-frame lag artifact.

Design notes
------------
The lerp formula applied each frame is::

    new = current + (target - current) * lerp_speed

Because *lerp_speed* is multiplied by the raw frame delta rather than
``delta_time``, the effective smoothing is frame-rate-dependent.  For
frame-rate-independent smoothing, callers should scale :attr:`lerp_speed`
by ``delta_time`` before passing it to the constructor, or replace the
formula with an exponential decay approach.

Setting :attr:`lerp_speed` to ``1.0`` produces instant snap-to-target
behaviour; values approaching ``0.0`` produce heavier lag.  Typical values
for a responsive but smooth feel lie in the range ``0.05``–``0.2``.

Usage
-----
    >>> cam_obj = GameObject('camera')
    >>> follow = cam_obj.AddComponent(
    ...     CameraFollow,
    ...     target=player_game_object,
    ...     lerp_speed=0.1,
    ... )

    >>> # Target can be swapped at runtime:
    >>> follow.target = new_target_object

    >>> # Disable tracking temporarily by clearing the target:
    >>> follow.target = None
"""

from __future__ import annotations

from core.gameObject import GameObject
from core.monoBehavior import MonoBehavior
from geometry import Vector2


class CameraFollow(MonoBehavior):
    """MonoBehavior component that smoothly lerps the owner toward a target each frame.

    :class:`CameraFollow` is intended to be attached to a camera game object
    via ``AddComponent``.  Each :meth:`LateUpdate` tick it advances the
    owner's world position a fraction of the way toward the target's current
    position, producing a smooth trailing effect.

    .. note::
        Set :attr:`target` to ``None`` to suspend tracking without removing
        the component.  Tracking resumes automatically once a new target is
        assigned.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    target : GameObject or None, optional
        The game object to follow.  If ``None``, :meth:`LateUpdate` is a
        no-op until a target is assigned.  Defaults to ``None``.
    lerp_speed : float, optional
        Interpolation factor in the range ``(0.0, 1.0]`` applied per frame.
        Lower values produce heavier lag; ``1.0`` snaps the camera instantly
        to the target.  Defaults to ``0.1``.

    Attributes
    ----------
    target : GameObject or None
        The game object currently being tracked.  May be reassigned at any
        time during gameplay.
    lerp_speed : float
        Per-frame interpolation factor.  May be adjusted at runtime to change
        the feel of the camera smoothing.
    """

    def __init__(
        self,
        game_object: GameObject,
        target: GameObject = None,
        lerp_speed: float = 0.1,
    ) -> None:
        super().__init__(game_object)
        self.target = target
        self.lerp_speed = lerp_speed

    # ---------------------------------------------------------------------- #
    #  MonoBehavior lifecycle                                                  #
    # ---------------------------------------------------------------------- #

    def LateUpdate(self) -> None:
        """Called once per frame, after all :meth:`Update` calls have completed.

        Advances the owner's world position toward :attr:`target` using a
        single lerp step.  Does nothing if :attr:`target` is ``None``.

        The position update uses the following formula applied independently
        on each axis::

            new = current + (target - current) * lerp_speed
        """
        if self.target:
            cur_pos = self.transform.position
            target_pos = self.target.transform.position

            new_x = cur_pos.x + (target_pos.x - cur_pos.x) * self.lerp_speed
            new_y = cur_pos.y + (target_pos.y - cur_pos.y) * self.lerp_speed

            self.transform.position = Vector2(new_x, new_y)