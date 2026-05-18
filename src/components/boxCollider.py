"""
Box-collider component — axis-aligned rectangular collision and trigger volumes.

Overview
--------
This module provides the :class:`BoxCollider` component, an axis-aligned
bounding-box (AABB) collider built on top of :class:`pygame.Rect`.  It
integrates with the :class:`~physics.physicsManager.PhysicsManager` singleton
to participate in both solid collision resolution and trigger-overlap detection.

Responsibilities
----------------
* **Registration** — registers itself with the
  :class:`~physics.physicsManager.PhysicsManager` singleton on enable and
  unregisters on disable or destroy, so the physics system always has an
  up-to-date list of active colliders.
* **Rect computation** — derives a world-space :class:`pygame.Rect` each time
  :attr:`rect` is accessed, applying the owner's current scale, plus
  configurable position and size offsets, so the collider tracks the transform
  automatically without a separate update step.
* **Solid vs. trigger mode** — when :attr:`is_trigger` is ``False`` the
  physics system uses this collider for depenetration; when ``True`` it fires
  :meth:`~dungeon.door.Door.on_trigger_enter` /
  :meth:`~dungeon.door.Door.on_trigger_exit` callbacks instead.
* **Layer filtering** — exposes a :attr:`layer` value drawn from
  :class:`~physics.physicsManager.PhysicsLayers` so that collision and trigger
  queries can cheaply exclude irrelevant collider pairs.

Rect calculation
----------------
The world-space rect is recomputed on every :attr:`rect` access using the
formula::

    width  = transform.size.x * |transform.scale.x| + size_offset.x
    height = transform.size.y * |transform.scale.y| + size_offset.y
    center = transform.position + position_offset

:attr:`size_offset` accepts negative values to shrink the collider below the
sprite boundary (e.g. a narrow foot collider) or positive values to expand it.
The computed width and height are clamped to a minimum of ``1`` pixel to keep
the rect valid at all scales.

Usage
-----
    Default solid collider that matches the sprite exactly:

    >>> collider = game_object.AddComponent(BoxCollider)

    Trigger collider on the player layer:

    >>> trigger = game_object.AddComponent(
    ...     BoxCollider,
    ...     is_trigger=True,
    ...     layer=PhysicsLayers.PLAYER,
    ... )

    Narrow foot collider — shifted down and inset horizontally:

    >>> foot = game_object.AddComponent(
    ...     BoxCollider,
    ...     position_offset=Vector2(0, 8),
    ...     size_offset=Vector2(-10, -20),
    ... )
"""

from __future__ import annotations

import pygame

from core.component import Component
from geometry import Vector2
from physics.physicsManager import PhysicsLayers, PhysicsManager


class BoxCollider(Component):
    """Component that represents an axis-aligned rectangular collision or trigger volume.

    :class:`BoxCollider` derives its world-space bounds from the owner
    transform each frame, applying an optional positional offset and size
    delta.  It self-registers with the
    :class:`~physics.physicsManager.PhysicsManager` singleton so the physics
    pipeline always operates on the current set of active colliders.

    .. note::
        :attr:`rect` is recomputed on every access — avoid calling it
        repeatedly within a single frame when performance is critical.
        Cache the return value locally if the same rect is needed more than
        once per update.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    is_trigger : bool, optional
        When ``True`` the collider acts as a trigger volume: overlap events
        fire :meth:`on_trigger_enter` / :meth:`on_trigger_exit` callbacks but
        no depenetration is applied.  When ``False`` the collider participates
        in solid collision resolution.  Defaults to ``False``.
    layer : int, optional
        Physics layer identifier from :class:`~physics.physicsManager.PhysicsLayers`.
        Used by the physics system to filter collider pairs.  Defaults to
        :attr:`~physics.physicsManager.PhysicsLayers.DEFAULT`.
    position_offset : Vector2 or None, optional
        World-space offset applied to the rect centre relative to
        ``transform.position``.  Useful for shifting the collider away from
        the sprite pivot (e.g. downward for a foot collider).  Defaults to
        ``Vector2(0, 0)``.
    size_offset : Vector2 or None, optional
        Delta added to the scaled sprite dimensions when computing the rect
        extents.  Negative values shrink the collider; positive values expand
        it.  Defaults to ``Vector2(0, 0)``.

    Attributes
    ----------
    is_trigger : bool
        Whether this collider fires trigger callbacks instead of resolving
        solid collisions.
    layer : int
        Physics layer of this collider.
    position_offset : Vector2
        Centre offset relative to ``transform.position``.
    size_offset : Vector2
        Additive delta applied to the scaled sprite size.
    """

    def __init__(
        self,
        game_object,
        is_trigger: bool = False,
        layer: int = PhysicsLayers.DEFAULT,
        position_offset: Vector2 = None,
        size_offset: Vector2 = None,
    ) -> None:
        super().__init__(game_object)
        self.is_trigger      = is_trigger
        self.layer           = layer
        self.position_offset = position_offset if position_offset is not None else Vector2(0, 0)
        self.size_offset     = size_offset     if size_offset     is not None else Vector2(0, 0)
        self._rect: pygame.Rect      = pygame.Rect(0, 0, 0, 0)
        self._prev_rect: pygame.Rect = None

    # ---------------------------------------------------------------------- #
    #  Convenience alias                                                       #
    # ---------------------------------------------------------------------- #

    @property
    def offset(self) -> Vector2:
        """Alias for :attr:`position_offset`.

        Provided for brevity when only the positional offset is of interest.
        Reads and writes :attr:`position_offset` directly.
        """
        return self.position_offset

    @offset.setter
    def offset(self, value: Vector2) -> None:
        self.position_offset = value

    # ---------------------------------------------------------------------- #
    #  Component lifecycle                                                     #
    # ---------------------------------------------------------------------- #

    def OnEnable(self) -> None:
        """Called by the component system when this component is enabled.

        Registers this collider with the
        :class:`~physics.physicsManager.PhysicsManager` singleton so it is
        included in collision and trigger queries for subsequent frames.
        """
        PhysicsManager.instance().register_collider(self)

    def OnDisable(self) -> None:
        """Called by the component system when this component is disabled.

        Unregisters this collider from the
        :class:`~physics.physicsManager.PhysicsManager` singleton so it is
        excluded from collision and trigger queries while inactive.
        """
        PhysicsManager.instance().unregister_collider(self)

    def OnDestroy(self) -> None:
        """Called by the component system just before the owner is destroyed.

        Delegates to :meth:`OnDisable` to ensure the collider is removed from
        the physics manager even if it was not explicitly disabled beforehand.
        """
        self.OnDisable()

    # ---------------------------------------------------------------------- #
    #  Rect computation                                                        #
    # ---------------------------------------------------------------------- #

    @property
    def rect(self) -> pygame.Rect:
        """The world-space bounding rect of this collider, recomputed on every access.

        Derives width, height, and centre from the owner transform's current
        position, size, and scale, then applies :attr:`size_offset` and
        :attr:`position_offset` respectively.  Width and height are clamped to
        a minimum of ``1`` pixel so the rect remains valid at extreme scales.

        Returns
        -------
        pygame.Rect
            The axis-aligned bounding rect in world space.  The same internal
            :class:`pygame.Rect` instance is mutated and returned on each call;
            do not retain a reference across frames.
        """
        w = int(self.transform.size.x * abs(self.transform.scale.x) + self.size_offset.x)
        h = int(self.transform.size.y * abs(self.transform.scale.y) + self.size_offset.y)

        self._rect.width   = max(1, w)
        self._rect.height  = max(1, h)
        self._rect.centerx = int(self.transform.position.x + self.position_offset.x)
        self._rect.centery = int(self.transform.position.y + self.position_offset.y)

        return self._rect