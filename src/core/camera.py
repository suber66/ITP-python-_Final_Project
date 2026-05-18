"""
Camera — world-to-screen and screen-to-world coordinate projection.

Overview
--------
This module provides the :class:`Camera` component, which defines the player's
view into the game world.  It translates between two coordinate spaces —
*world space* (the global coordinate system shared by all game objects) and
*screen space* (pixel coordinates on the display surface, with the origin at
the top-left corner) — and supports uniform zoom scaling.

Responsibilities
----------------
* **World-to-screen projection** — converts a world-space position to the
  corresponding pixel coordinate on the display surface, accounting for the
  camera's world position and zoom level.
* **Screen-to-world unprojection** — inverts the projection to convert a
  screen-space pixel coordinate (e.g. a mouse cursor position) back to its
  world-space equivalent.
* **Zoom** — applies a uniform scale factor around the camera's world position,
  making the viewport appear closer (zoom > 1) or further away (zoom < 1).

Coordinate system
-----------------
The camera keeps its :attr:`~core.component.Component.transform` position at
the world-space point that should appear at the **centre** of the screen.
The projection formulas are:

.. code-block:: text

    # World → Screen
    screen_x = (world_x − camera_x) * zoom + half_screen_w
    screen_y = (world_y − camera_y) * zoom + half_screen_h

    # Screen → World  (exact inverse)
    world_x = (screen_x − half_screen_w) / zoom + camera_x
    world_y = (screen_y − half_screen_h) / zoom + camera_y

Both methods query the current display surface at call time via
:func:`pygame.display.get_surface`, so they automatically adapt to window
resizes without requiring explicit notification.  If no display surface is
available, the input coordinate is returned unchanged as a safe fallback.

Usage
-----
    >>> camera_obj = GameObject('MainCamera')
    >>> camera = camera_obj.AddComponent(Camera, zoom=1.5)
    >>> renderer.register_object(camera_obj)

    >>> # Move the camera to follow the player:
    >>> camera.transform.position = player.transform.position

    >>> # Project a world point to the screen:
    >>> screen_pos = camera.WorldToScreen(enemy.transform.position)

    >>> # Unproject a mouse click to world space:
    >>> mouse_x, mouse_y = pygame.mouse.get_pos()
    >>> world_pos = camera.ScreenToWorld(Vector2(mouse_x, mouse_y))
"""

from __future__ import annotations

import pygame

from core.component import Component
from geometry import Vector2


class Camera(Component):
    """Component that projects between world space and screen space.

    :class:`Camera` is attached to a dedicated game object whose
    :attr:`~core.component.Component.transform` position determines the
    world-space point rendered at the centre of the screen.  Move that
    transform to pan the view; adjust :attr:`zoom` to scale it.

    The :class:`~core.renderer.Renderer` discovers the first enabled
    :class:`Camera` in the scene automatically and uses it for all render
    and visibility calls during that frame.

    .. note::
        Both projection methods read the display surface dimensions at call
        time.  They do not cache screen size, so the result is always correct
        after a window resize without any additional setup.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    zoom : float, optional
        Initial zoom level.  Values greater than ``1.0`` magnify the world
        (objects appear larger); values between ``0.0`` and ``1.0`` shrink it.
        Defaults to ``1.0`` (no zoom).

    Attributes
    ----------
    zoom : float
        Current zoom level applied uniformly to both axes during projection.
        May be changed at any time; the new value takes effect on the very
        next :meth:`WorldToScreen` or :meth:`ScreenToWorld` call.
    """

    def __init__(self, game_object: 'GameObject', zoom: float = 1.0) -> None:
        super().__init__(game_object)
        self.zoom: float = zoom

    # ---------------------------------------------------------------------- #
    #  Coordinate projection                                                   #
    # ---------------------------------------------------------------------- #

    def WorldToScreen(self, world_pos: Vector2) -> Vector2:
        """Project a world-space position to screen-space pixel coordinates.

        Translates *world_pos* relative to the camera's current world position,
        applies :attr:`zoom`, and offsets the result so that the camera centre
        maps to the centre of the display surface.

        If no pygame display surface is available (e.g. during headless tests),
        *world_pos* is returned unchanged.

        Parameters
        ----------
        world_pos : Vector2
            The position in world space to project.

        Returns
        -------
        Vector2
            The corresponding pixel coordinate in screen space, with
            ``(0, 0)`` at the top-left corner of the display surface.
        """
        screen = pygame.display.get_surface()
        if not screen:
            return world_pos

        half_w = screen.get_width() / 2
        half_h = screen.get_height() / 2

        screen_x = (world_pos.x - self.transform.position.x) * self.zoom + half_w
        screen_y = (world_pos.y - self.transform.position.y) * self.zoom + half_h

        return Vector2(screen_x, screen_y)

    def ScreenToWorld(self, screen_pos: Vector2) -> Vector2:
        """Unproject a screen-space pixel coordinate to world-space.

        Applies the exact inverse of :meth:`WorldToScreen`: removes the
        half-screen offset, divides by :attr:`zoom`, and translates by the
        camera's world position.  Useful for converting mouse or touch input
        into world coordinates.

        If no pygame display surface is available (e.g. during headless tests),
        *screen_pos* is returned unchanged.

        Parameters
        ----------
        screen_pos : Vector2
            The pixel coordinate in screen space to unproject, with
            ``(0, 0)`` at the top-left corner of the display surface.

        Returns
        -------
        Vector2
            The corresponding position in world space.
        """
        screen = pygame.display.get_surface()
        if not screen:
            return screen_pos

        half_w = screen.get_width() / 2
        half_h = screen.get_height() / 2

        world_x = (screen_pos.x - half_w) / self.zoom + self.transform.position.x
        world_y = (screen_pos.y - half_h) / self.zoom + self.transform.position.y

        return Vector2(world_x, world_y)