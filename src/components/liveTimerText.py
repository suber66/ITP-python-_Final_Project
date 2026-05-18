"""
LiveTimerText — self-updating ScreenSpace timer label component.

Overview
--------
This module provides the :class:`LiveTimerText` component, a lightweight
UI text element that displays the current reading of a
:class:`~components.timer.Timer` as a live ``'MM:SS.mm'`` string.  It
redraws its backing surface only when the formatted time string changes,
so the rendering cost is proportional to how often the centisecond digit
advances rather than to the frame rate.

Responsibilities
----------------
* **Time formatting** — converts the raw ``float`` value from
  :attr:`~components.timer.Timer.elapsed` into a fixed-width
  ``'MM:SS.mm'`` string via :meth:`~LiveTimerText._fmt`, returning a
  placeholder ``'--:--.--'`` when the elapsed value is ``None``.
* **Change detection** — compares the newly formatted string against the
  cached value from the previous frame in :meth:`~LiveTimerText.UIUpdate`
  and triggers a surface rebuild only on change.
* **Outlined text rendering** — composites a four-direction outline pass
  followed by the main glyph pass onto a transparent ``SRCALPHA`` surface
  in :meth:`~LiveTimerText._build`, giving the timer digits strong contrast
  against any background.
* **Centre alignment** — positions the text block at the geometric centre
  of the bounding rect regardless of the string width.

Lazy rebuilding
---------------
Unlike :class:`~core.ui.components.tmp_text.TMP_Text`, which uses a generic
dirty flag, :class:`LiveTimerText` rebuilds its surface only when the
formatted string itself changes.  Because centiseconds advance at most 100
times per second, on a 60 Hz display most frames require no rebuild at all.

Usage
-----
    >>> hud = GameObject('HUD')
    >>> label = hud.AddComponent(
    ...     LiveTimerText,
    ...     game_timer=timer,
    ...     anchor=UIAnchor.TOP_CENTER,
    ...     ui_layer=5,
    ... )
"""

import pygame

from components.timer import Timer
from core.ui.components.ui_component import UIComponent
from core.ui.ui_anchor import UIAnchor


class LiveTimerText(UIComponent):
    """ScreenSpace label that mirrors a :class:`~components.timer.Timer` in real time.

    :class:`LiveTimerText` is intended to be attached to a HUD
    :class:`~core.gameObject.GameObject` alongside a running
    :class:`~components.timer.Timer`.  Each frame it reads the timer's
    :attr:`~components.timer.Timer.elapsed` value, formats it, and rebuilds
    its surface only when the formatted string differs from the previous
    frame's output.

    .. note::
        The component does not start or stop the associated
        :class:`~components.timer.Timer`; it only reads from it.  Timer
        lifecycle management is the responsibility of the caller.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, supplied automatically
        by the component system.
    game_timer : Timer
        The :class:`~components.timer.Timer` instance whose
        :attr:`~components.timer.Timer.elapsed` value is displayed.
        The timer may be running or stopped; both states are handled
        correctly.
    anchor : UIAnchor, optional
        Anchor preset used to position the label on screen.
        Defaults to ``None`` (no anchor).
    ui_layer : int, optional
        Render-order layer forwarded to the parent
        :class:`~core.ui.components.ui_component.UIComponent`.  Higher
        values render on top.  Defaults to ``0``.

    Attributes
    ----------
    _timer : Timer
        Reference to the associated :class:`~components.timer.Timer`,
        read each frame in :meth:`UIUpdate`.
    _font : pygame.freetype.Font or None
        Bold ``'Arial'`` font resolved lazily on the first call to
        :meth:`_get_font`.  ``None`` until that call is made.
    _font_size : int
        Point size used when rasterising glyphs.  Fixed at ``32``.
    _color : tuple
        ``(R, G, B, A)`` foreground colour of the timer digits.
        Defaults to a warm yellow ``(255, 255, 100, 255)``.
    _outline_color : tuple
        ``(R, G, B, A)`` colour of the four-direction outline pass rendered
        behind each glyph.  Defaults to a dark amber ``(80, 60, 0, 255)``.
    _last_text : str
        The formatted string produced on the previous frame.  Used by
        :meth:`UIUpdate` to skip rebuilds when the display has not changed.
    _surface : pygame.Surface or None
        The most recently composited label surface, or ``None`` before the
        first build.
    """

    def __init__(
        self,
        game_object,
        *,
        game_timer: Timer,
        anchor: UIAnchor = None,
        ui_layer: int = 0,
    ) -> None:
        super().__init__(game_object, ui_layer=ui_layer, anchor=anchor)
        self._timer         = game_timer
        self._font          = None
        self._font_size     = 32
        self._color         = (255, 255, 100, 255)
        self._outline_color = (80, 60, 0, 255)
        self._last_text     = ''
        self._surface       = None

    # ---------------------------------------------------------------- #
    #  Internal helpers                                                  #
    # ---------------------------------------------------------------- #

    def _get_font(self) -> 'pygame.freetype.Font':
        """Return the shared bold font, resolving it on first access.

        Imports ``pygame.freetype`` and retrieves the bold ``'Arial'``
        typeface from :class:`~core.ui.components.tmp_text._FontCache` on
        the first call, then caches the result in :attr:`_font`.  Subsequent
        calls return the cached instance with no further imports or cache
        lookups.

        Returns
        -------
        pygame.freetype.Font
            The bold ``'Arial'`` font instance shared across all render
            calls for this component.
        """
        if self._font is None:
            import pygame.freetype
            from core.ui.components.tmp_text import _FontCache
            self._font = _FontCache.get('Arial', bold=True)
        return self._font

    def _fmt(self, t: float) -> str:
        """Format *t* as a ``'MM:SS.mm'`` display string.

        Converts a raw elapsed-seconds float into a fixed-width string
        suitable for a timer HUD label.  The centisecond field represents
        hundredths of a second, providing two digits of sub-second precision.

        Parameters
        ----------
        t : float or None
            Elapsed time in seconds.  Passing ``None`` (e.g. before the
            timer has been started) produces the placeholder ``'--:--.--'``
            instead of raising an exception.

        Returns
        -------
        str
            A zero-padded string in the form ``'MM:SS.mm'``, for example
            ``'01:07.09'`` for 67.09 seconds, or ``'--:--.--'`` when *t*
            is ``None``.

        Examples
        --------
        >>> self._fmt(67.09)
        '01:07.09'
        >>> self._fmt(0.0)
        '00:00.00'
        >>> self._fmt(None)
        '--:--.--'
        """
        if t is None:
            return '--:--.--'
        minutes = int(t) // 60
        seconds = int(t) % 60
        millis  = int((t - int(t)) * 100)
        return f'{minutes:02d}:{seconds:02d}.{millis:02d}'

    def _build(self, text: str) -> None:
        """Rasterise *text* into a new backing surface.

        Allocates a transparent ``SRCALPHA`` surface the size of the
        bounding rect, measures the text block, centres it, and renders in
        two passes:

        1. **Outline pass** — renders the text four times at ``±2`` pixel
           offsets along each cardinal axis using :attr:`_outline_color`.
        2. **Main pass** — renders the text at the computed centre position
           using :attr:`_color`.

        The finished surface is stored in :attr:`_surface` and will be
        blitted to the screen by the next :meth:`UIRender` call.

        Parameters
        ----------
        text : str
            The pre-formatted display string to render, typically produced
            by :meth:`_fmt`.
        """
        import pygame.freetype
        font   = self._get_font()
        surf   = pygame.Surface(self._rect.size, pygame.SRCALPHA)
        bounds = font.get_rect(text, size=self._font_size)
        x      = (self._rect.width  - bounds.width)  / 2
        y      = (self._rect.height - bounds.height) / 2

        # Four-direction outline pass
        ow = 2
        for ox, oy in [(-ow, 0), (ow, 0), (0, -ow), (0, ow)]:
            font.render_to(surf, (x + ox, y + oy), text,
                           fgcolor=self._outline_color, size=self._font_size)

        # Main glyph pass
        font.render_to(surf, (x, y), text,
                       fgcolor=self._color, size=self._font_size)

        self._surface = surf

    # ---------------------------------------------------------------- #
    #  UIComponent interface                                             #
    # ---------------------------------------------------------------- #

    def UIUpdate(self) -> None:
        """Rebuild the label surface if the displayed time has changed.

        Reads :attr:`~components.timer.Timer.elapsed` from the associated
        :class:`~components.timer.Timer`, formats it via :meth:`_fmt`, and
        compares the result with :attr:`_last_text`.  A new surface is built
        via :meth:`_build` only when the formatted string differs, keeping
        the per-frame cost negligible on frames where the centisecond digit
        has not advanced.
        """
        t = self._fmt(self._timer.elapsed)
        if t != self._last_text:
            self._last_text = t
            self._build(t)

    def UIRender(self, screen: pygame.Surface) -> None:
        """Blit the label surface onto *screen*.

        Does nothing if :attr:`_surface` is ``None`` (i.e. before the first
        :meth:`UIUpdate` call or if the timer has never been started).

        Parameters
        ----------
        screen : pygame.Surface
            The render target, typically the main display surface.
        """
        if self._surface:
            screen.blit(self._surface, self._rect.topleft)