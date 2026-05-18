"""
Rigidbody — axis-aligned physics component with swept depenetration.

Overview
--------
This module provides the :class:`Rigidbody` component, a lightweight
rigid-body implementation designed for tile-based or arena-style games that
require solid collision response without a full physics engine.  It operates
exclusively in screen-space and assumes all colliders are axis-aligned
rectangles (:class:`~components.boxCollider.BoxCollider`).

Responsibilities
----------------
* **Displacement** — applies a frame-level movement delta to the owner
  transform via :meth:`~Rigidbody.move`, splitting horizontal and vertical
  axes to enable single-axis depenetration.
* **Depenetration** — for each axis that was displaced, queries
  :class:`~physics.physicsManager.PhysicsManager` for overlapping solid
  colliders and pushes the owner back out of any penetrations via
  :meth:`~Rigidbody._depenetrate`.
* **Multi-wall resolution** — accumulates per-solid push vectors
  iteratively rather than taking only the deepest overlap, so that corner
  contacts with two adjacent walls are resolved cleanly in a single pass.
* **Spatial hash synchronisation** — after all axis moves are complete,
  updates the spatial hash once to keep the owner's collider position
  consistent with the physics world.

Depenetration strategy
----------------------
Movement is resolved axis-by-axis in the order X → Y.  For each axis:

1. The transform is displaced silently (no change notification is fired).
2. :meth:`~Rigidbody._depenetrate` queries the spatial hash for overlapping
   solids (trigger colliders are excluded).
3. :func:`~Rigidbody._resolve_x` / :func:`~Rigidbody._resolve_y` sum the
   minimum-distance push required to separate from each solid, advancing a
   local copy of the bounding rect after every push so that subsequent solids
   are checked against the already-corrected position.
4. A single ``_notify_changed`` call and spatial hash update are issued at
   the very end, after both axes have been processed.

Solid layers
------------
Only colliders whose ``layer`` attribute is listed in ``_solid_layers``
participate in depenetration.  By default this includes
:attr:`~physics.physicsManager.PhysicsLayers.WALL` and
:attr:`~physics.physicsManager.PhysicsLayers.OBSTACLE`.  Trigger colliders
(``is_trigger == True``) are always excluded regardless of layer.

Usage
-----
    >>> player = GameObject('Player')
    >>> player.AddComponent(BoxCollider, width=32, height=32)
    >>> rb = player.AddComponent(Rigidbody)

    >>> # Called each frame from a movement component:
    >>> rb.move(Vector2(dx, dy))
"""

from typing import Optional, List
from core.component import Component
from components.boxCollider import BoxCollider
from core.gameObject import GameObject
from physics.physicsManager import PhysicsManager, PhysicsLayers
from geometry import Vector2


class Rigidbody(Component):
    """Axis-aligned rigid-body component with iterative depenetration.

    :class:`Rigidbody` is intended to be attached to a
    :class:`~core.gameObject.GameObject` that also owns a
    :class:`~components.boxCollider.BoxCollider`.  Each call to
    :meth:`move` displaces the owner along X and Y independently, checks
    for solid overlaps after each axis step, and resolves any penetrations
    before notifying the rest of the engine of the final position.

    .. note::
        If no :class:`~components.boxCollider.BoxCollider` is found on the
        owner during :meth:`Start`, the component falls back to direct
        transform translation with no collision response.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, supplied automatically
        by the component system.

    Attributes
    ----------
    velocity : Vector2
        Stored velocity vector.  Not consumed internally by :class:`Rigidbody`
        itself; provided as a convenience field for movement components that
        need to accumulate or read back the current velocity.
    _collider : BoxCollider or None
        Reference to the sibling :class:`~components.boxCollider.BoxCollider`
        resolved in :meth:`Start`.  ``None`` until ``Start`` has been called
        or if no collider exists on the owner.
    _solid_layers : tuple[PhysicsLayers, ...]
        Layers whose colliders participate in depenetration.  Defaults to
        ``(PhysicsLayers.WALL, PhysicsLayers.OBSTACLE)``.
    """

    def __init__(self, game_object: GameObject) -> None:
        super().__init__(game_object)
        self.velocity                            = Vector2(0, 0)
        self._collider: Optional[BoxCollider]    = None
        self._solid_layers                       = (PhysicsLayers.WALL,
                                                    PhysicsLayers.OBSTACLE)

    def Start(self) -> None:
        """Resolve the sibling collider reference.

        Called by the component system after all components on the owner
        :class:`~core.gameObject.GameObject` have been constructed.  Looks up
        the sibling :class:`~components.boxCollider.BoxCollider` and stores it
        in :attr:`_collider`.  If no collider is present, :attr:`_collider`
        remains ``None`` and :meth:`move` will fall back to unconstrained
        translation.
        """
        self._collider = self.gameObject.GetComponent(BoxCollider)

    # ---------------------------------------------------------------- #
    #  Public interface                                                  #
    # ---------------------------------------------------------------- #

    def move(self, move_delta: Vector2) -> None:
        """Displace the owner by *move_delta*, resolving solid collisions.

        Applies the requested displacement in two independent axis passes
        (X then Y).  After each pass, :meth:`_depenetrate` is called to push
        the owner out of any solid overlaps introduced by that step.  A
        single transform notification and spatial hash update are issued once
        both axes have been processed.

        If the owner has no :class:`~components.boxCollider.BoxCollider`, the
        delta is applied directly to the transform with no collision
        resolution.

        Parameters
        ----------
        move_delta : Vector2
            The desired displacement in pixels for this frame.  Components
            may be zero to skip the corresponding axis entirely.
        """
        if not self._collider:
            p = self.transform.position
            self.transform.position = Vector2(p.x + move_delta.x,
                                              p.y + move_delta.y)
            return

        physics = PhysicsManager.instance()

        if move_delta.x != 0:
            self.transform._set_position_silent(Vector2(
                self.transform.position.x + move_delta.x,
                self.transform.position.y))
            if self._collider.enabled:
                self._depenetrate('x', physics)

        if move_delta.y != 0:
            self.transform._set_position_silent(Vector2(
                self.transform.position.x,
                self.transform.position.y + move_delta.y))
            if self._collider.enabled:
                self._depenetrate('y', physics)

        # Single notify + spatial hash sync after both axes are resolved
        self.transform._notify_changed()
        physics._spatial.remove(self._collider)
        physics._spatial.insert(self._collider)

    # ---------------------------------------------------------------- #
    #  Depenetration                                                     #
    # ---------------------------------------------------------------- #

    def _depenetrate(self, axis: str, physics: PhysicsManager) -> None:
        """Push the owner out of any solid overlaps on the given *axis*.

        Queries the spatial hash for colliders currently overlapping the
        owner's :attr:`_collider`, filters out non-solid layers and trigger
        colliders, and delegates the push calculation to :meth:`_resolve_x`
        or :meth:`_resolve_y`.  The resulting correction is applied via a
        silent position set so that no intermediate change notifications are
        fired.

        .. note::
            This method reads the collider rect *after* the silent move so
            that it reflects the displaced position, not the position from
            the previous frame.

        Parameters
        ----------
        axis : str
            The axis to resolve; must be ``'x'`` or ``'y'``.
        physics : PhysicsManager
            The active :class:`~physics.physicsManager.PhysicsManager`
            instance, passed in by :meth:`move` to avoid repeated singleton
            look-ups within the same frame.
        """
        solids = [
            c for c in physics.get_collisions(self._collider)
            if c.layer in self._solid_layers and not c.is_trigger
        ]
        if not solids:
            return

        my_rect = self._collider.rect

        if axis == 'x':
            push = self._resolve_x(my_rect, solids)
            if push != 0:
                self.transform._set_position_silent(Vector2(
                    self.transform.position.x + push,
                    self.transform.position.y))
        else:
            push = self._resolve_y(my_rect, solids)
            if push != 0:
                self.transform._set_position_silent(Vector2(
                    self.transform.position.x,
                    self.transform.position.y + push))

    @staticmethod
    def _resolve_x(my_rect, solids) -> float:
        """Compute the total X correction needed to clear all solid overlaps.

        Iterates over every overlapping solid and calculates the
        minimum-distance push on the X axis required to separate the two
        rects.  After each push, *my_rect* is advanced by that amount so
        that the next solid is evaluated against the already-corrected
        position.  Summing individual pushes rather than taking the largest
        single overlap ensures that corner contacts involving two or more
        adjacent walls are fully resolved in a single call.

        The direction of each push is chosen by comparing the overlap depths
        from both sides: the shallower penetration determines the exit
        direction.

        Parameters
        ----------
        my_rect : pygame.Rect
            The owner's bounding rectangle *after* the silent X displacement.
            A local copy is advanced with each resolved solid; the original
            object is not mutated.
        solids : list
            Sequence of solid :class:`~components.boxCollider.BoxCollider`
            instances to test, pre-filtered by :meth:`_depenetrate`.

        Returns
        -------
        float
            The total X correction in pixels.  Positive values push the owner
            rightward; negative values push leftward.  Returns ``0.0`` if no
            solid overlaps *my_rect*.
        """
        total = 0.0
        for other in solids:
            r = other.rect
            if not my_rect.colliderect(r):
                continue
            overlap_right = my_rect.right  - r.left    # entered from left  → push left
            overlap_left  = r.right        - my_rect.left  # entered from right → push right

            push   = -overlap_right if overlap_right <= overlap_left else overlap_left
            total += push
            my_rect = my_rect.move(push, 0)
        return total

    @staticmethod
    def _resolve_y(my_rect, solids) -> float:
        """Compute the total Y correction needed to clear all solid overlaps.

        Mirrors the logic of :meth:`_resolve_x` along the vertical axis.
        Overlap depths are measured from the bottom and top edges; the
        shallower penetration determines the exit direction.  *my_rect* is
        advanced after each resolved solid so that subsequent solids are
        evaluated against the corrected position.

        Parameters
        ----------
        my_rect : pygame.Rect
            The owner's bounding rectangle *after* the silent Y displacement.
            A local copy is advanced with each resolved solid; the original
            object is not mutated.
        solids : list
            Sequence of solid :class:`~components.boxCollider.BoxCollider`
            instances to test, pre-filtered by :meth:`_depenetrate`.

        Returns
        -------
        float
            The total Y correction in pixels.  Positive values push the owner
            downward; negative values push upward.  Returns ``0.0`` if no
            solid overlaps *my_rect*.
        """
        total = 0.0
        for other in solids:
            r = other.rect
            if not my_rect.colliderect(r):
                continue
            overlap_bottom = my_rect.bottom - r.top
            overlap_top    = r.bottom       - my_rect.top

            push   = -overlap_bottom if overlap_bottom <= overlap_top else overlap_top
            total += push
            my_rect = my_rect.move(0, push)
        return total