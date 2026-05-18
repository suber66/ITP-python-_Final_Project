"""
TMP_Text — TextMeshPro-inspired UI text component for pygame.

Overview
--------
This module provides the :class:`TMP_Text` component, a rich text rendering
element modelled after Unity's *TextMeshPro* package.  It uses
``pygame.freetype`` for SDF-style, sub-pixel-accurate glyph rasterisation and
exposes a Unity-like property API that rebuilds the backing surface lazily
whenever any visual attribute changes.

Responsibilities
----------------
* **Font management** — resolves system fonts through :class:`_FontCache`,
  a process-level cache that avoids re-loading the same typeface on every
  component instantiation.
* **Text layout** — breaks raw text into display lines via
  :meth:`~TMP_Text._wrap_text`, honouring the active :class:`OverflowMode`
  and the component's bounding rectangle.
* **Surface rendering** — composites optional drop-shadow, eight-direction
  outline, and main text glyphs onto a transparent ``SRCALPHA`` surface via
  :meth:`~TMP_Text._build_surface`.
* **Alignment** — positions each line both horizontally (left / centre /
  right) and vertically (top / middle / bottom) within the bounding rect
  according to the active :class:`TextAnchor`.
* **Reactivity** — every settable property is backed by a private attribute
  and a setter that calls :meth:`~TMP_Text._mark_dirty`, deferring the
  (potentially expensive) surface rebuild to the next
  :meth:`~TMP_Text.UIUpdate` or :meth:`~TMP_Text.UIRender` call.

Lazy rebuilding
---------------
The backing ``pygame.Surface`` (``_surface``) is not rebuilt immediately when
a property changes.  Instead a ``_dirty`` flag is set.  The surface is
reconstructed the first time :meth:`UIUpdate` or :meth:`UIRender` is called
after the flag is raised.  This means that batching multiple property changes
in a single frame incurs only one rebuild.

Usage
-----
    >>> label = GameObject('Label')
    >>> txt = label.AddComponent(
    ...     TMP_Text,
    ...     text="Hello!",
    ...     font_size=24,
    ...     color=(255, 255, 255, 255),
    ...     alignment=TextAnchor.MIDDLE_CENTER,
    ...     rect=pygame.Rect(100, 100, 300, 60),
    ... )

    >>> # Updating a property triggers a lazy rebuild on the next frame:
    >>> txt.text = "World!"
    >>> txt.color = (255, 220, 0, 255)

    >>> # Override at runtime:
    >>> txt.font_size = 32
    >>> txt.alignment = TextAnchor.LOWER_RIGHT
"""

import pygame
import pygame.freetype
from enum import Enum
from typing import Optional, Tuple
from core.ui.components.ui_component import UIComponent
from core.gameObject import GameObject

pygame.freetype.init()


# ------------------------------------------------------------------ #
#  Enums                                                               #
# ------------------------------------------------------------------ #

class TextAnchor(Enum):
    """Nine-point anchor grid that controls text alignment within its rect.

    Each member encodes a ``(horizontal, vertical)`` pair where:

    * horizontal — ``0`` = left, ``1`` = centre, ``2`` = right
    * vertical   — ``0`` = top,  ``1`` = middle, ``2`` = bottom

    The :attr:`h` and :attr:`v` convenience properties expose these integers
    so that rendering code can branch without inspecting the raw tuple.

    Example
    -------
    >>> anchor = TextAnchor.MIDDLE_CENTER
    >>> anchor.h   # 1 — centre
    1
    >>> anchor.v   # 1 — middle
    1
    """

    UPPER_LEFT    = (0, 0)
    UPPER_CENTER  = (1, 0)
    UPPER_RIGHT   = (2, 0)
    MIDDLE_LEFT   = (0, 1)
    MIDDLE_CENTER = (1, 1)
    MIDDLE_RIGHT  = (2, 1)
    LOWER_LEFT    = (0, 2)
    LOWER_CENTER  = (1, 2)
    LOWER_RIGHT   = (2, 2)

    @property
    def h(self) -> int:
        """Horizontal alignment index.

        Returns
        -------
        int
            ``0`` for left, ``1`` for centre, ``2`` for right.
        """
        return self.value[0]

    @property
    def v(self) -> int:
        """Vertical alignment index.

        Returns
        -------
        int
            ``0`` for top, ``1`` for middle, ``2`` for bottom.
        """
        return self.value[1]


class OverflowMode(Enum):
    """Policy that governs how text behaves when it exceeds the bounding rect.

    Attributes
    ----------
    OVERFLOW : str
        Text is drawn without clipping; glyphs may appear outside the rect.
    TRUNCATE : str
        The rendered surface is hard-clipped to the rect dimensions.
    WRAP : str
        Long lines are broken at word boundaries to fit within the rect width.
        Explicit newlines in the source string are always honoured regardless
        of the active mode.
    """

    OVERFLOW = 'overflow'
    TRUNCATE = 'truncate'
    WRAP     = 'wrap'


# ------------------------------------------------------------------ #
#  Font cache                                                          #
# ------------------------------------------------------------------ #

class _FontCache:
    """Process-level cache for ``pygame.freetype.Font`` objects.

    Fonts are keyed by ``(name, bold, italic)`` and constructed at most once
    per unique combination.  If a requested system font cannot be found,
    ``Arial`` is substituted silently.

    .. note::
        This class is an internal implementation detail of :mod:`tmp_text`
        and is not part of the public API.  Callers should use
        :meth:`TMP_Text._get_font` rather than accessing :class:`_FontCache`
        directly.
    """

    _cache: dict = {}

    @classmethod
    def get(
        cls,
        name: str,
        bold: bool = False,
        italic: bool = False,
    ) -> pygame.freetype.Font:
        """Return a cached font, constructing it on first access.

        Parameters
        ----------
        name : str
            System font family name (e.g. ``'Arial'``, ``'Consolas'``).
        bold : bool, optional
            Request the bold variant.  Defaults to ``False``.
        italic : bool, optional
            Request the italic variant.  Defaults to ``False``.

        Returns
        -------
        pygame.freetype.Font
            A shared font instance.  The returned object must not be
            modified by callers, as it is shared across all components
            that use the same typeface configuration.
        """
        key = (name, bold, italic)
        if key not in cls._cache:
            try:
                font = pygame.freetype.SysFont(name, 0, bold=bold, italic=italic)
            except Exception:
                font = pygame.freetype.SysFont('Arial', 0, bold=bold, italic=italic)
            cls._cache[key] = font
        return cls._cache[key]


# ------------------------------------------------------------------ #
#  Type alias                                                          #
# ------------------------------------------------------------------ #

RGBA = Tuple[int, int, int, int]
"""Type alias for a four-channel colour value ``(R, G, B, A)``."""


# ------------------------------------------------------------------ #
#  TMP_Text component                                                  #
# ------------------------------------------------------------------ #

from core.ui.ui_anchor import UIAnchor


class TMP_Text(UIComponent):
    """TextMeshPro-inspired UI text component backed by ``pygame.freetype``.

    :class:`TMP_Text` is intended to be attached to a
    :class:`~core.gameObject.GameObject` via ``AddComponent``.  It manages
    its own ``pygame.Surface`` and redraws it lazily whenever a visual
    property changes.

    .. note::
        The component requires a valid ``rect`` (inherited from
        :class:`~core.ui.components.ui_component.UIComponent`) before it can
        render.  Word-wrapping and vertical alignment both depend on the rect
        dimensions.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, supplied automatically
        by the component system.
    anchor : UIAnchor, optional
        Anchor preset used to position the component relative to its parent
        or the screen.  Defaults to ``None`` (no anchor).
    text : str, optional
        Initial display string.  Supports explicit newlines (``'\\n'``).
        Defaults to ``'Text'``.
    font_name : str, optional
        System font family name passed to :class:`_FontCache`.  Falls back
        to ``'Arial'`` if the requested font is unavailable.  Defaults to
        ``'Arial'``.
    font_size : float, optional
        Point size at which glyphs are rasterised.  Defaults to ``20.0``.
    color : RGBA, optional
        Foreground glyph colour as an ``(R, G, B, A)`` tuple.  Defaults to
        opaque white ``(255, 255, 255, 255)``.
    alignment : TextAnchor, optional
        Horizontal and vertical alignment of the text block within the
        bounding rect.  Defaults to :attr:`TextAnchor.MIDDLE_CENTER`.
    bold : bool, optional
        Request the bold font variant.  Defaults to ``False``.
    italic : bool, optional
        Request the italic font variant.  Defaults to ``False``.
    line_spacing : float, optional
        Multiplier applied to the natural line height to control the gap
        between successive lines.  A value of ``1.0`` produces no extra
        space; ``1.2`` adds 20 % padding.  Defaults to ``1.2``.
    overflow : OverflowMode, optional
        Policy for text that exceeds the bounding rect.  Defaults to
        :attr:`OverflowMode.WRAP`.
    outline_width : int, optional
        Pixel radius of the eight-direction outline drawn behind each glyph.
        ``0`` disables the outline entirely.  Defaults to ``0``.
    outline_color : RGBA, optional
        Colour of the glyph outline.  Defaults to opaque black
        ``(0, 0, 0, 255)``.
    shadow_offset : tuple[int, int], optional
        ``(dx, dy)`` pixel offset of the drop-shadow pass.  ``(0, 0)``
        disables the shadow.  Defaults to ``(0, 0)``.
    shadow_color : RGBA, optional
        Colour of the drop-shadow.  Defaults to semi-transparent black
        ``(0, 0, 0, 128)``.
    ui_layer : int, optional
        Render-order layer forwarded to the parent
        :class:`~core.ui.components.ui_component.UIComponent`.  Higher
        values render on top.  Defaults to ``0``.

    Attributes
    ----------
    _dirty : bool
        ``True`` when the backing surface must be rebuilt before the next
        render.  Set by every property setter via :meth:`_mark_dirty`.
    _surface : pygame.Surface or None
        The most recently built composite surface, or ``None`` before the
        first build.
    """

    def __init__(
        self,
        game_object: GameObject,
        *,
        anchor: UIAnchor = None,
        text: str = 'Text',
        font_name: str = 'Arial',
        font_size: float = 20.0,
        color: RGBA = (255, 255, 255, 255),
        alignment: TextAnchor = TextAnchor.MIDDLE_CENTER,
        bold: bool = False,
        italic: bool = False,
        line_spacing: float = 1.2,
        overflow: OverflowMode = OverflowMode.WRAP,
        outline_width: int = 0,
        outline_color: RGBA = (0, 0, 0, 255),
        shadow_offset: Tuple[int, int] = (0, 0),
        shadow_color: RGBA = (0, 0, 0, 128),
        ui_layer: int = 0,
    ) -> None:
        super().__init__(game_object, ui_layer=ui_layer, anchor=anchor)

        self._text = text
        self._font_name = font_name
        self._font_size = font_size
        self._color = color
        self._alignment = alignment
        self._bold = bold
        self._italic = italic
        self._line_spacing = line_spacing
        self._overflow = overflow
        self._outline_width = outline_width
        self._outline_color = outline_color
        self._shadow_offset = shadow_offset
        self._shadow_color = shadow_color
        self._surface: Optional[pygame.Surface] = None
        self._dirty: bool = True

    # ---------------------------------------------------------------- #
    #  Internal helpers                                                  #
    # ---------------------------------------------------------------- #

    def _mark_dirty(self) -> None:
        """Schedule a surface rebuild on the next update or render cycle.

        Called internally by every property setter that affects the visual
        output.  Repeated calls before the next rebuild have no additional
        cost.
        """
        self._dirty = True

    def _get_font(self) -> pygame.freetype.Font:
        """Retrieve the font for the current typeface configuration.

        Delegates to :class:`_FontCache` using the component's active
        :attr:`_font_name`, :attr:`_bold`, and :attr:`_italic` settings.

        Returns
        -------
        pygame.freetype.Font
            The shared font object for the current configuration.
        """
        return _FontCache.get(self._font_name, self._bold, self._italic)

    def _wrap_text(
        self,
        font: pygame.freetype.Font,
        text: str,
        max_width: int,
    ) -> list[str]:
        """Break *text* into display lines that fit within *max_width*.

        The method always splits on explicit newline characters (``'\\n'``).
        Additional word-boundary wrapping is applied only when
        :attr:`_overflow` is :attr:`OverflowMode.WRAP` and *max_width* is
        positive.  Words that are wider than *max_width* on their own are
        placed on a line by themselves without further splitting.

        Parameters
        ----------
        font : pygame.freetype.Font
            Font used to measure glyph advances; must match the font that
            will render the final output.
        text : str
            The raw display string, which may contain ``'\\n'`` characters.
        max_width : int
            Maximum pixel width of a single display line.  Values ``<= 0``
            disable word-wrap regardless of :attr:`_overflow`.

        Returns
        -------
        list[str]
            Ordered list of display lines ready for rendering.
        """
        if self._overflow != OverflowMode.WRAP or max_width <= 0:
            return text.split('\n')

        result = []
        for paragraph in text.split('\n'):
            words = paragraph.split(' ')
            line = ''
            for word in words:
                test = (line + ' ' + word).strip()
                bounds = font.get_rect(test, size=self._font_size)
                if bounds.width <= max_width or not line:
                    line = test
                else:
                    result.append(line)
                    line = word
            result.append(line)
        return result

    def _build_surface(self) -> None:
        """Reconstruct the backing ``pygame.Surface`` from the current state.

        This is the core rendering routine.  It performs the following steps
        in order:

        1. Obtain the font from :class:`_FontCache`.
        2. Wrap the display string into lines via :meth:`_wrap_text`.
        3. Compute the total text block height and the vertical start
           position according to :attr:`_alignment`.
        4. For each line: optionally render a drop-shadow pass, then an
           eight-direction outline pass, and finally the main glyph pass.
        5. If :attr:`_overflow` is :attr:`OverflowMode.TRUNCATE`, clip the
           result to the bounding rect.
        6. Store the finished surface in :attr:`_surface` and clear
           :attr:`_dirty`.

        .. note::
            This method is called automatically by :meth:`UIUpdate` and
            :meth:`UIRender` when :attr:`_dirty` is ``True``.  It should not
            normally be called directly by external code.
        """
        font = self._get_font()
        lines = self._wrap_text(font, self._text, self._rect.width)

        line_height = font.get_sized_height(self._font_size)
        gap = line_height * (self._line_spacing - 1.0)
        total_h = len(lines) * line_height + (len(lines) - 1) * gap

        # Canvas: transparent background
        surf = pygame.Surface((self._rect.width, self._rect.height), pygame.SRCALPHA)

        # Vertical start position
        if self._alignment.v == 0:      # top
            y_start = 0
        elif self._alignment.v == 1:    # middle
            y_start = (self._rect.height - total_h) / 2
        else:                           # bottom
            y_start = self._rect.height - total_h

        y = y_start
        for line in lines:
            bounds = font.get_rect(line, size=self._font_size)
            lw = bounds.width

            # Horizontal position
            if self._alignment.h == 0:      # left
                x = 0
            elif self._alignment.h == 1:    # centre
                x = (self._rect.width - lw) / 2
            else:                           # right
                x = self._rect.width - lw

            # Drop-shadow pass
            if self._shadow_offset != (0, 0):
                font.render_to(
                    surf,
                    (x + self._shadow_offset[0], y + self._shadow_offset[1]),
                    line,
                    fgcolor=self._shadow_color,
                    size=self._font_size,
                )

            # Eight-direction outline pass
            if self._outline_width > 0:
                ow = self._outline_width
                for ox, oy in [(-ow, 0), (ow, 0), (0, -ow), (0, ow),
                                (-ow, -ow), (ow, -ow), (-ow, ow), (ow, ow)]:
                    font.render_to(
                        surf, (x + ox, y + oy),
                        line,
                        fgcolor=self._outline_color,
                        size=self._font_size,
                    )

            # Main glyph pass
            font.render_to(surf, (x, y), line,
                           fgcolor=self._color, size=self._font_size)

            y += line_height + gap

        # Hard-clip to rect if truncation is active
        if self._overflow == OverflowMode.TRUNCATE:
            clip_surf = pygame.Surface(
                (self._rect.width, self._rect.height), pygame.SRCALPHA)
            clip_surf.blit(surf, (0, 0))
            surf = clip_surf

        self._surface = surf
        self._dirty = False

    # ---------------------------------------------------------------- #
    #  Properties with lazy-rebuild semantics                            #
    # ---------------------------------------------------------------- #

    @property
    def text(self) -> str:
        """The display string rendered by this component.

        Explicit newline characters (``'\\n'``) produce line breaks
        regardless of the active :class:`OverflowMode`.  Assigning a value
        that is identical to the current string (after ``str()`` coercion)
        is a no-op and does not trigger a rebuild.

        :type: str
        """
        return self._text

    @text.setter
    def text(self, v: str) -> None:
        if self._text != str(v):
            self._text = str(v)
            self._mark_dirty()

    @property
    def font_size(self) -> float:
        """Point size at which glyphs are rasterised.

        Changing this value affects layout metrics (line height, word-wrap
        boundaries) and triggers a full surface rebuild.

        :type: float
        """
        return self._font_size

    @font_size.setter
    def font_size(self, v: float) -> None:
        self._font_size = float(v)
        self._mark_dirty()

    @property
    def color(self) -> RGBA:
        """Foreground glyph colour as an ``(R, G, B, A)`` tuple.

        The alpha channel is composited normally by pygame when the surface
        is blitted to the screen.

        :type: RGBA
        """
        return self._color

    @color.setter
    def color(self, v: RGBA) -> None:
        self._color = v
        self._mark_dirty()

    @property
    def rect(self) -> pygame.Rect:
        """Bounding rectangle that defines the layout canvas.

        Both the surface dimensions and the word-wrap column width are derived
        from this rect.  Assigning a new rect discards the cached surface.

        :type: pygame.Rect
        """
        return self._rect

    @rect.setter
    def rect(self, v: pygame.Rect) -> None:
        self._rect = v
        self._mark_dirty()

    @property
    def alignment(self) -> TextAnchor:
        """Horizontal and vertical text alignment within the bounding rect.

        :type: TextAnchor
        """
        return self._alignment

    @alignment.setter
    def alignment(self, v: TextAnchor) -> None:
        self._alignment = v
        self._mark_dirty()

    @property
    def bold(self) -> bool:
        """Whether the bold font variant is requested.

        Toggling this property causes :class:`_FontCache` to resolve a
        different font object on the next rebuild.

        :type: bool
        """
        return self._bold

    @bold.setter
    def bold(self, v: bool) -> None:
        self._bold = v
        self._mark_dirty()

    # ---------------------------------------------------------------- #
    #  UIComponent interface                                             #
    # ---------------------------------------------------------------- #

    def UIUpdate(self) -> None:
        """Per-frame logic hook called by the UI system before rendering.

        Rebuilds the backing surface via :meth:`_build_surface` if
        :attr:`_dirty` is ``True``.  Keeping the rebuild here (rather than
        deferring it entirely to :meth:`UIRender`) allows layout-dependent
        queries (e.g. bounding-box calculations) to read up-to-date
        dimensions within the same frame.
        """
        if self._dirty:
            self._build_surface()

    def UIRender(self, screen: pygame.Surface) -> None:
        """Blit the text surface onto *screen* at the component's position.

        Triggers a surface rebuild via :meth:`_build_surface` if the surface
        is stale (i.e. :attr:`_dirty` is ``True``) so that a rebuild is
        never missed even if :meth:`UIUpdate` was skipped.  Does nothing if
        the surface could not be constructed.

        Parameters
        ----------
        screen : pygame.Surface
            The render target, typically the main display surface.
        """
        if self._dirty:
            self._build_surface()
        if self._surface:
            screen.blit(self._surface, self._rect.topleft)