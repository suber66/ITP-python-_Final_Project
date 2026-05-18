"""
UIAnchor — normalised screen-space anchor and pixel-offset layout descriptor.

Overview
--------
This module provides the :class:`UIAnchor` dataclass, a compact layout
descriptor that positions and sizes a UI element relative to the screen
dimensions using a two-stage system: a normalised *anchor point* that scales
with the window, followed by a fixed *pixel offset* applied on top of it.

Responsibilities
----------------
* **Anchor resolution** — maps a normalised ``(anchor_x, anchor_y)`` pair to
  an absolute pixel position by multiplying against the current screen
  dimensions, making layouts automatically adapt to window resizes.
* **Pixel offset** — applies a fixed ``(offset_x, offset_y)`` displacement
  from the resolved anchor, allowing fine-grained placement without changing
  the anchor itself.
* **Rect construction** — combines the resolved position with the element's
  pixel ``width`` and ``height`` to produce a :class:`pygame.Rect` centred on
  the anchor point, ready for use in :meth:`pygame.Surface.blit` and hit-test
  calls.

Layout model
------------
The resolve formula positions the **centre** of the element at the anchor
point plus the offset:

.. code-block:: text

    pixel_x = screen_w * anchor_x + offset_x
    pixel_y = screen_h * anchor_y + offset_y

    rect.x = pixel_x − width  / 2
    rect.y = pixel_y − height / 2

Common anchor presets:

+---------------------+-------------+---------+
| Position            | ``anchor_x``| ``anchor_y`` |
+=====================+=============+=============+
| Centre              | 0.5         | 0.5         |
| Top-left            | 0.0         | 0.0         |
| Top-right           | 1.0         | 0.0         |
| Bottom-centre       | 0.5         | 1.0         |
| Bottom-right        | 1.0         | 1.0         |
+---------------------+-------------+-------------+

Usage
-----
    >>> anchor = UIAnchor(
    ...     anchor_x=0.5, anchor_y=1.0,   # bottom-centre of screen
    ...     offset_x=0.0, offset_y=-20.0, # 20 px above the bottom edge
    ...     width=300.0, height=60.0,
    ... )

    >>> rect = anchor.resolve(screen_w=1280, screen_h=720)
    >>> screen.blit(button_surface, rect)

    >>> # Re-resolve after a window resize — no state change needed:
    >>> rect = anchor.resolve(screen_w=new_w, screen_h=new_h)
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass
class UIAnchor:
    """Normalised anchor and fixed-offset layout descriptor for a UI element.

    :class:`UIAnchor` stores everything needed to position and size one UI
    element in a resolution-independent way.  Call :meth:`resolve` each frame
    (or on every ``VIDEORESIZE`` event) to obtain an up-to-date
    :class:`pygame.Rect` centred on the anchor point.

    Because :class:`UIAnchor` is a plain :func:`~dataclasses.dataclass`, it
    carries no runtime state beyond its fields and can be freely copied,
    serialised, or shared between components.

    Attributes
    ----------
    anchor_x : float
        Normalised horizontal anchor position in the range ``[0.0, 1.0]``.
        ``0.0`` pins the element to the left edge of the screen; ``0.5``
        centres it horizontally; ``1.0`` pins it to the right edge.
        Defaults to ``0.5``.
    anchor_y : float
        Normalised vertical anchor position in the range ``[0.0, 1.0]``.
        ``0.0`` pins the element to the top edge of the screen; ``0.5``
        centres it vertically; ``1.0`` pins it to the bottom edge.
        Defaults to ``0.5``.
    offset_x : float
        Fixed horizontal pixel displacement applied after the anchor is
        resolved.  Positive values shift the element to the right.
        Defaults to ``0.0``.
    offset_y : float
        Fixed vertical pixel displacement applied after the anchor is
        resolved.  Positive values shift the element downward.
        Defaults to ``0.0``.
    width : float
        Width of the element in pixels.  The resolved :class:`pygame.Rect`
        is centred horizontally on the anchor point, so the left edge sits
        at ``pixel_x − width / 2``.  Defaults to ``200.0``.
    height : float
        Height of the element in pixels.  The resolved :class:`pygame.Rect`
        is centred vertically on the anchor point, so the top edge sits at
        ``pixel_y − height / 2``.  Defaults to ``50.0``.
    """

    anchor_x: float = 0.5
    anchor_y: float = 0.5
    offset_x: float = 0.0
    offset_y: float = 0.0
    width: float = 200.0
    height: float = 50.0

    # ---------------------------------------------------------------------- #
    #  Layout resolution                                                       #
    # ---------------------------------------------------------------------- #

    def resolve(self, screen_w: int, screen_h: int) -> pygame.Rect:
        """Compute the absolute screen-space :class:`pygame.Rect` for this anchor.

        Multiplies the normalised anchor coordinates by the supplied screen
        dimensions, applies the pixel offset, and constructs a
        :class:`pygame.Rect` of size ``(width, height)`` centred on the
        resulting point.  All floating-point coordinates are truncated to
        integers before the rect is created.

        This method is stateless and idempotent: calling it multiple times
        with the same arguments always returns an equal rect, and no internal
        fields are modified.

        Parameters
        ----------
        screen_w : int
            Current display surface width in pixels.
        screen_h : int
            Current display surface height in pixels.

        Returns
        -------
        pygame.Rect
            A rect of size ``(int(width), int(height))`` whose centre lies at
            ``(screen_w * anchor_x + offset_x, screen_h * anchor_y + offset_y)``.
        """
        x = screen_w * self.anchor_x + self.offset_x - self.width / 2
        y = screen_h * self.anchor_y + self.offset_y - self.height / 2
        return pygame.Rect(int(x), int(y), int(self.width), int(self.height))