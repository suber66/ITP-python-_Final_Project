"""
PlayerController — keyboard-driven movement component for the player entity.

Overview
--------
This module provides the :class:`PlayerController` component, which reads
raw keyboard input every frame and translates it into physics-driven
displacement via a sibling :class:`~components.rigidbody.Rigidbody`.  It
also mirrors the player sprite horizontally to match the direction of
lateral movement.

Responsibilities
----------------
* **Input polling** — samples ``pygame.key.get_pressed()`` each frame to
  build a cardinal direction vector from the W / A / S / D and arrow-key
  bindings.
* **Velocity construction** — scales the normalised direction vector by
  :attr:`~PlayerController.move_speed` and forwards the result to
  :meth:`~components.rigidbody.Rigidbody.move`, which handles collision
  resolution internally.
* **Sprite flipping** — sets the ``flip_x`` flag on the sibling
  :class:`~core.spriteRenderer.SpriteRenderer` to face the sprite in the
  direction of the last horizontal input.

Input bindings
--------------
Both WASD and arrow-key schemes are supported simultaneously:

=============  ============================
Key(s)         Effect
=============  ============================
W / ↑          Move up    (``move_dir.y -= 1``)
S / ↓          Move down  (``move_dir.y += 1``)
A / ←          Move left  (``move_dir.x -= 1``, sprite flipped)
D / →          Move right (``move_dir.x += 1``, sprite unflipped)
=============  ============================

Diagonal movement is produced naturally when two perpendicular keys are
held simultaneously.  The resulting velocity vector is **not normalised**,
so diagonal movement is faster than cardinal movement by a factor of
``sqrt(2)``.  Normalisation can be added by callers if isometric speed is
required.

Dependency resolution
---------------------
Both :attr:`_rigidbody` and :attr:`_sprite_renderer` are resolved in
:meth:`Start` rather than ``__init__`` to respect the Unity-style component
lifecycle: sibling components are guaranteed to be fully constructed by the
time ``Start`` is called, but may not be when ``__init__`` runs.

Usage
-----
    >>> player = GameObject('Player')
    >>> player.AddComponent(BoxCollider, width=32, height=32)
    >>> player.AddComponent(Rigidbody)
    >>> player.AddComponent(SpriteRenderer, sprite=player_sprite)
    >>> player.AddComponent(PlayerController, move_speed=4.0)
"""

import pygame
from core.monoBehavior import MonoBehavior
from components.rigidbody import Rigidbody
from core.spriteRenderer import SpriteRenderer
from geometry import Vector2


class PlayerController(MonoBehavior):
    """Keyboard-driven movement and sprite-flip controller for the player.

    :class:`PlayerController` is intended to be attached to the player
    :class:`~core.gameObject.GameObject` alongside a
    :class:`~components.rigidbody.Rigidbody` and a
    :class:`~core.spriteRenderer.SpriteRenderer`.  Each frame it polls
    keyboard state, constructs a velocity vector, and delegates physical
    movement to the sibling :class:`~components.rigidbody.Rigidbody` so
    that collision detection and depenetration are handled transparently.

    .. note::
        If no :class:`~components.rigidbody.Rigidbody` is found on the
        owner during :meth:`Start`, movement input is silently ignored.
        The component will still update sprite flipping if a
        :class:`~core.spriteRenderer.SpriteRenderer` is present.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, supplied automatically
        by the component system.
    move_speed : float, optional
        Scalar applied to the raw direction vector to produce the per-frame
        pixel displacement passed to
        :meth:`~components.rigidbody.Rigidbody.move`.  Defaults to ``5.0``.

    Attributes
    ----------
    move_speed : float
        Per-frame pixel displacement per unit of direction.  May be changed
        at runtime (e.g. for speed-boost power-ups) without requiring a
        component rebuild.
    _rigidbody : Rigidbody or None
        Sibling :class:`~components.rigidbody.Rigidbody` resolved in
        :meth:`Start`.  ``None`` until ``Start`` has been called or if no
        rigidbody exists on the owner.
    _sprite_renderer : SpriteRenderer or None
        Sibling :class:`~core.spriteRenderer.SpriteRenderer` resolved in
        :meth:`Start`.  ``None`` until ``Start`` has been called or if no
        sprite renderer exists on the owner.
    """

    def __init__(self, game_object, move_speed: float = 5.0) -> None:
        super().__init__(game_object)
        self.move_speed                              = move_speed
        self._rigidbody: Rigidbody | None           = None
        self._sprite_renderer: SpriteRenderer | None = None

    # ---------------------------------------------------------------- #
    #  MonoBehavior lifecycle                                            #
    # ---------------------------------------------------------------- #

    def Start(self) -> None:
        """Resolve sibling component references.

        Called by the component system after all components on the owner
        :class:`~core.gameObject.GameObject` have been constructed.  Looks
        up the sibling :class:`~components.rigidbody.Rigidbody` and
        :class:`~core.spriteRenderer.SpriteRenderer` and stores them for
        use in :meth:`Update`.
        """
        self._rigidbody       = self.gameObject.GetComponent(Rigidbody)
        self._sprite_renderer = self.gameObject.GetComponent(SpriteRenderer)

    def Update(self) -> None:
        """Sample keyboard input and apply movement for the current frame.

        Performs the following steps in order each frame:

        1. Poll ``pygame.key.get_pressed()`` and accumulate a raw integer
           direction vector from the W / A / S / D and arrow-key bindings.
        2. Update ``flip_x`` on the sibling
           :class:`~core.spriteRenderer.SpriteRenderer` to face the sprite
           toward the most recent horizontal input (``True`` for left,
           ``False`` for right).
        3. If a :class:`~components.rigidbody.Rigidbody` is present and the
           direction vector is non-zero, scale it by :attr:`move_speed` and
           forward the resulting velocity to
           :meth:`~components.rigidbody.Rigidbody.move`.

        .. note::
            Movement is skipped entirely when the direction vector is zero
            (no movement keys held) to avoid an unnecessary
            :meth:`~components.rigidbody.Rigidbody.move` call and its
            associated spatial hash update overhead.
        """
        keys     = pygame.key.get_pressed()
        move_dir = Vector2(0, 0)

        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move_dir.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move_dir.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_dir.x -= 1
            if self._sprite_renderer:
                self._sprite_renderer.flip_x = True
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_dir.x += 1
            if self._sprite_renderer:
                self._sprite_renderer.flip_x = False

        if self._rigidbody and (move_dir.x != 0 or move_dir.y != 0):
            velocity = Vector2(
                move_dir.x * self.move_speed,
                move_dir.y * self.move_speed,
            )
            self._rigidbody.move(velocity)