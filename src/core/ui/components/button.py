"""
Button — interactive ScreenSpace button component.

Overview
--------
This module provides the :class:`Button` component, a fully interactive
ScreenSpace UI element that responds to mouse hover, press, and release
events.  It is modelled after Unity's ``UI.Button`` workflow and integrates
with the same font and alignment infrastructure used by
:class:`~core.ui.components.tmp_text.TMP_Text`.

Responsibilities
----------------
* **State management** — tracks one of four exclusive visual states
  (Normal, Hovered, Pressed, Disabled) based on mouse position and button
  input polled each frame.
* **Surface pre-baking** — constructs one ``pygame.Surface`` per state at
  build time via :meth:`~Button._build_surfaces`, so that each
  :meth:`~Button.UIRender` call is a single ``blit`` with no per-frame
  glyph rasterisation.
* **Callback dispatch** — fires caller-supplied callables on click
  (mouse release inside rect), hover entry, and hover exit.
* **Appearance customisation** — delegates all colour and geometry
  parameters to :class:`ButtonColors`, keeping the button class itself
  free of hard-coded visual constants.
* **Reactivity** — label text and interactability can be changed at
  runtime; a ``_dirty`` flag schedules a surface rebuild on the next frame.

State transitions
-----------------
The state machine follows a simple linear model::

    NORMAL ──(enter)──► HOVERED ──(LMB down)──► PRESSED
      ▲                    │                        │
      └───(leave)──────────┘    ◄──(LMB up inside)──┘

The :attr:`~_BtnState.DISABLED` state is entered whenever
:attr:`~Button.interactable` is set to ``False`` and overrides all
pointer-driven transitions until interactability is restored.

Surface caching
---------------
All four state surfaces are built once by :meth:`~Button._build_surfaces`
and stored in ``_surfaces``.  The surfaces are rebuilt only when ``_dirty``
is ``True`` (e.g. after a :attr:`~Button.text` assignment).  Changing the
active :class:`ButtonColors` scheme at runtime requires setting
``_dirty = True`` manually or reassigning the ``_colors`` attribute through
a dedicated setter if one is added.

Callbacks
---------
All callbacks are invoked with no arguments.  Exceptions raised inside a
callback are caught and printed to ``stdout`` with a ``[Button]`` prefix so
that a misbehaving callback cannot crash the render loop.

Usage
-----
    >>> btn_obj = GameObject('StartButton')
    >>> btn = btn_obj.AddComponent(
    ...     Button,
    ...     rect=pygame.Rect(560, 400, 160, 50),
    ...     text='Start Game',
    ...     on_click=lambda: scene_manager.load_scene('game'),
    ... )

    >>> # Disable the button at runtime:
    >>> btn.interactable = False

    >>> # Update the label without recreating the component:
    >>> btn.text = 'Loading…'
"""

import pygame
import pygame.freetype
from typing import Callable, Optional, Tuple
from core.ui.components.ui_component import UIComponent
from core.ui.components.tmp_text import _FontCache, TextAnchor
from core.gameObject import GameObject
from core.gameManager import GameManager
from core.ui.ui_anchor import UIAnchor

pygame.freetype.init()

RGBA = Tuple[int, int, int, int]
"""Type alias for a four-channel colour value ``(R, G, B, A)``."""


# ------------------------------------------------------------------ #
#  Color scheme                                                        #
# ------------------------------------------------------------------ #

class ButtonColors:
    """Visual theme applied uniformly across all four button states.

    :class:`ButtonColors` is a plain data container — every attribute is
    public and may be mutated directly.  To apply changes at runtime, set
    ``Button._dirty = True`` after modifying the scheme so that the cached
    surfaces are rebuilt on the next frame.

    Parameters
    ----------
    normal : RGBA, optional
        Background colour in the idle state.
        Defaults to ``(60, 60, 80, 220)``.
    hovered : RGBA, optional
        Background colour while the pointer is inside the rect.
        Defaults to ``(90, 90, 130, 240)``.
    pressed : RGBA, optional
        Background colour while the left mouse button is held down.
        Defaults to ``(40, 40, 60, 255)``.
    disabled : RGBA, optional
        Background colour when :attr:`~Button.interactable` is ``False``.
        Defaults to ``(50, 50, 50, 150)``.
    text_normal : RGBA, optional
        Label colour in the idle state.
        Defaults to opaque white ``(255, 255, 255, 255)``.
    text_hovered : RGBA, optional
        Label colour while hovered.
        Defaults to ``(255, 255, 200, 255)``.
    text_pressed : RGBA, optional
        Label colour while pressed.
        Defaults to ``(200, 200, 200, 255)``.
    text_disabled : RGBA, optional
        Label colour when disabled.
        Defaults to ``(120, 120, 120, 255)``.
    border : RGBA, optional
        Colour of the rectangular outline drawn around the button.
        Defaults to ``(150, 150, 200, 200)``.
    border_width : int, optional
        Pixel width of the border stroke.  ``0`` hides the border.
        Defaults to ``2``.
    corner_radius : int, optional
        Pixel radius of the rounded corners applied to both the background
        fill and the border stroke.  ``0`` produces sharp corners.
        Defaults to ``8``.
    """

    def __init__(
        self,
        normal:        RGBA = (60, 60, 80, 220),
        hovered:       RGBA = (90, 90, 130, 240),
        pressed:       RGBA = (40, 40, 60, 255),
        disabled:      RGBA = (50, 50, 50, 150),
        text_normal:   RGBA = (255, 255, 255, 255),
        text_hovered:  RGBA = (255, 255, 200, 255),
        text_pressed:  RGBA = (200, 200, 200, 255),
        text_disabled: RGBA = (120, 120, 120, 255),
        border:        RGBA = (150, 150, 200, 200),
        border_width:  int  = 2,
        corner_radius: int  = 8,
    ) -> None:
        self.normal        = normal
        self.hovered       = hovered
        self.pressed       = pressed
        self.disabled      = disabled
        self.text_normal   = text_normal
        self.text_hovered  = text_hovered
        self.text_pressed  = text_pressed
        self.text_disabled = text_disabled
        self.border        = border
        self.border_width  = border_width
        self.corner_radius = corner_radius


# ------------------------------------------------------------------ #
#  Button states                                                       #
# ------------------------------------------------------------------ #

class _BtnState:
    """Integer constants that identify each visual state of a :class:`Button`.

    Using plain integers (rather than an ``Enum``) lets the constants serve
    directly as dictionary keys into ``Button._surfaces`` without an
    extra ``.value`` dereference.

    .. note::
        This class is an internal implementation detail and is not part of
        the public API.

    Attributes
    ----------
    NORMAL : int
        The button is idle; the pointer is not over it.
    HOVERED : int
        The pointer is inside the button's rect but no button is pressed.
    PRESSED : int
        The left mouse button is held down while the pointer is inside the
        button's rect.
    DISABLED : int
        The button does not respond to pointer input.  Set automatically
        when :attr:`~Button.interactable` is ``False``.
    """

    NORMAL   = 0
    HOVERED  = 1
    PRESSED  = 2
    DISABLED = 3


# ------------------------------------------------------------------ #
#  Button                                                              #
# ------------------------------------------------------------------ #

class Button(UIComponent):
    """Interactive ScreenSpace button component with four visual states.

    :class:`Button` is intended to be attached to a
    :class:`~core.gameObject.GameObject` via ``AddComponent``.  It polls
    mouse state each frame in :meth:`UIUpdate`, drives the internal state
    machine, dispatches registered callbacks, and blits the appropriate
    pre-baked surface in :meth:`UIRender`.

    .. note::
        All four state surfaces are built once and cached.  The cache is
        invalidated (``_dirty = True``) only when :attr:`text` is reassigned.
        Other visual changes (e.g. swapping :class:`ButtonColors`) require
        the caller to set ``_dirty = True`` manually.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, supplied automatically
        by the component system.
    anchor : UIAnchor, optional
        Anchor preset used to resolve the component's bounding rect relative
        to its parent or the screen.  Defaults to ``None`` (no anchor).
    text : str, optional
        Label displayed at the centre of the button.  Supports explicit
        newlines (``'\\n'``).  Defaults to ``'Button'``.
    font_name : str, optional
        System font family name resolved via
        :class:`~core.ui.components.tmp_text._FontCache`.  Falls back to
        ``'Arial'`` if the requested font is unavailable.  Defaults to
        ``'Arial'``.
    font_size : float, optional
        Point size at which label glyphs are rasterised.  Defaults to
        ``18.0``.
    bold : bool, optional
        Request the bold font variant for the label.  Defaults to ``False``.
    colors : ButtonColors, optional
        Visual theme applied to all four states.  A default
        :class:`ButtonColors` instance is used when not provided.
    alignment : TextAnchor, optional
        Horizontal and vertical alignment of the label within the button
        rect.  Defaults to :attr:`~core.ui.components.tmp_text.TextAnchor.MIDDLE_CENTER`.
    on_click : callable, optional
        Invoked with no arguments when the left mouse button is released
        inside the button rect.  Defaults to ``None``.
    on_hover : callable, optional
        Invoked with no arguments when the pointer first enters the button
        rect.  Defaults to ``None``.
    on_exit : callable, optional
        Invoked with no arguments when the pointer leaves the button rect.
        Defaults to ``None``.
    interactable : bool, optional
        When ``False`` the button is locked in the
        :attr:`~_BtnState.DISABLED` state and no callbacks are fired.
        Defaults to ``True``.
    ui_layer : int, optional
        Render-order layer forwarded to the parent
        :class:`~core.ui.components.ui_component.UIComponent`.  Higher
        values render on top.  Defaults to ``0``.
    transition_speed : float, optional
        Reserved for future animated cross-fading between state surfaces.
        Currently stored but not used by the rendering pipeline.
        Defaults to ``15.0``.

    Attributes
    ----------
    _state : int
        The current :class:`_BtnState` constant.  Updated every frame by
        :meth:`UIUpdate`.
    _prev_state : int
        The :class:`_BtnState` constant from the previous frame.  Used to
        detect edge transitions (hover entry, click release).
    _surfaces : dict[int, pygame.Surface]
        Pre-baked surfaces keyed by :class:`_BtnState` constant.  Populated
        by :meth:`_build_surfaces` and consumed by :meth:`UIRender`.
    _dirty : bool
        ``True`` when :attr:`_surfaces` must be rebuilt before the next
        render.  Set automatically when :attr:`text` is reassigned.
    _blend : float
        Interpolation factor reserved for future animated transitions.
    _blend_surf : pygame.Surface or None
        Scratch surface reserved for future animated transitions.
    """

    def __init__(
        self,
        game_object: GameObject,
        *,
        anchor: UIAnchor = None,
        text: str = 'Button',
        font_name: str = 'Arial',
        font_size: float = 18.0,
        bold: bool = False,
        colors: Optional[ButtonColors] = None,
        alignment: TextAnchor = TextAnchor.MIDDLE_CENTER,
        on_click:  Optional[Callable] = None,
        on_hover:  Optional[Callable] = None,
        on_exit:   Optional[Callable] = None,
        interactable: bool = True,
        ui_layer: int = 0,
        transition_speed: float = 15.0,
    ) -> None:
        super().__init__(game_object, ui_layer=ui_layer, anchor=anchor)

        self._text             = text
        self._font_name        = font_name
        self._font_size        = font_size
        self._bold             = bold
        self._colors           = colors or ButtonColors()
        self._alignment        = alignment
        self._on_click         = on_click
        self._on_hover         = on_hover
        self._on_exit          = on_exit
        self._interactable     = interactable
        self._transition_speed = transition_speed
        self._state            = _BtnState.NORMAL
        self._prev_state       = _BtnState.NORMAL
        self._surfaces: dict[int, pygame.Surface] = {}
        self._dirty            = True
        self._blend: float     = 1.0
        self._blend_surf: Optional[pygame.Surface] = None

    # ---------------------------------------------------------------- #
    #  Properties                                                        #
    # ---------------------------------------------------------------- #

    @property
    def text(self) -> str:
        """Label string displayed on the button face.

        Assigning a new value converts it to ``str`` and sets ``_dirty``
        so that all four state surfaces are rebuilt on the next frame.

        :type: str
        """
        return self._text

    @text.setter
    def text(self, v: str) -> None:
        self._text  = str(v)
        self._dirty = True

    @property
    def rect(self) -> pygame.Rect:
        """Bounding rectangle used for hit-testing and surface dimensions.

        The rect is resolved by the parent
        :class:`~core.ui.components.ui_component.UIComponent` during
        initialisation and is read-only at the component level.

        :type: pygame.Rect
        """
        return self._rect

    @property
    def interactable(self) -> bool:
        """Whether the button responds to pointer input.

        Setting this to ``False`` forces the button into the
        :attr:`~_BtnState.DISABLED` state and suppresses all callbacks until
        the property is restored to ``True``.

        :type: bool
        """
        return self._interactable

    @interactable.setter
    def interactable(self, v: bool) -> None:
        self._interactable = bool(v)

    # ---------------------------------------------------------------- #
    #  Surface building                                                  #
    # ---------------------------------------------------------------- #

    def _build_state_surface(
        self,
        bg_color: RGBA,
        text_color: RGBA,
    ) -> pygame.Surface:
        """Rasterise a single button state into a new ``pygame.Surface``.

        Draws, in order: a rounded-rectangle background fill, an optional
        border stroke, and then the label text positioned according to
        :attr:`_alignment`.

        Parameters
        ----------
        bg_color : RGBA
            Fill colour for the button background.
        text_color : RGBA
            Foreground colour used when rasterising the label glyphs.

        Returns
        -------
        pygame.Surface
            A fully composited ``SRCALPHA`` surface sized to match
            :attr:`rect`.
        """
        surf = pygame.Surface(self._rect.size, pygame.SRCALPHA)
        r    = pygame.Rect(0, 0, *self._rect.size)

        # Rounded-rectangle background fill
        pygame.draw.rect(surf, bg_color, r,
                         border_radius=self._colors.corner_radius)

        # Border stroke
        if self._colors.border_width > 0:
            pygame.draw.rect(surf, self._colors.border, r,
                             width=self._colors.border_width,
                             border_radius=self._colors.corner_radius)

        # Label text
        font        = _FontCache.get(self._font_name, self._bold)
        lines       = self._text.split('\n')
        line_height = font.get_sized_height(self._font_size)
        total_h     = len(lines) * line_height

        if self._alignment.v == 0:      # top
            y = 0
        elif self._alignment.v == 1:    # middle
            y = (r.height - total_h) / 2
        else:                           # bottom
            y = r.height - total_h

        for line in lines:
            bounds = font.get_rect(line, size=self._font_size)
            if self._alignment.h == 0:      # left
                x = 0
            elif self._alignment.h == 1:    # centre
                x = (r.width - bounds.width) / 2
            else:                           # right
                x = r.width - bounds.width

            font.render_to(surf, (x, y), line,
                           fgcolor=text_color, size=self._font_size)
            y += line_height

        return surf

    def _build_surfaces(self) -> None:
        """Rebuild the pre-baked surface for every button state.

        Calls :meth:`_build_state_surface` once per :class:`_BtnState`
        constant, pairing each state with the appropriate background and
        text colours from :attr:`_colors`, and stores the results in
        :attr:`_surfaces`.  Clears :attr:`_dirty` on completion.

        .. note::
            This method is called automatically by :meth:`UIUpdate` and
            :meth:`UIRender` when :attr:`_dirty` is ``True``.  It should
            not normally be invoked directly by external code.
        """
        c = self._colors
        self._surfaces = {
            _BtnState.NORMAL:   self._build_state_surface(c.normal,   c.text_normal),
            _BtnState.HOVERED:  self._build_state_surface(c.hovered,  c.text_hovered),
            _BtnState.PRESSED:  self._build_state_surface(c.pressed,  c.text_pressed),
            _BtnState.DISABLED: self._build_state_surface(c.disabled, c.text_disabled),
        }
        self._dirty = False

    # ---------------------------------------------------------------- #
    #  UIComponent interface                                             #
    # ---------------------------------------------------------------- #

    def UIUpdate(self) -> None:
        """Per-frame logic hook called by the UI system before rendering.

        Performs the following steps in order:

        1. Rebuilds :attr:`_surfaces` via :meth:`_build_surfaces` if
           :attr:`_dirty` is ``True``.
        2. Forces the state to :attr:`~_BtnState.DISABLED` and returns
           early if :attr:`interactable` is ``False``.
        3. Queries ``pygame.mouse`` for the current cursor position and
           left-button state.
        4. Drives the state machine and dispatches callbacks:

           * ``HOVERED → PRESSED`` when LMB is held while hovering.
           * ``PRESSED → HOVERED`` (+ :attr:`_on_click`) on LMB release
             inside the rect.
           * ``NORMAL → HOVERED`` (+ :attr:`_on_hover`) on pointer entry.
           * ``HOVERED → NORMAL`` (+ :attr:`_on_exit`) on pointer exit.

        Callbacks are wrapped in a ``try/except`` block; any exception is
        printed to ``stdout`` and does not propagate to the caller.
        """
        if self._dirty:
            self._build_surfaces()

        if not self._interactable:
            self._state = _BtnState.DISABLED
            return

        mouse_pos     = pygame.mouse.get_pos()
        mouse_buttons = pygame.mouse.get_pressed()
        hovering      = self._rect.collidepoint(mouse_pos)

        prev = self._state
        if hovering:
            if mouse_buttons[0]:
                self._state = _BtnState.PRESSED
            else:
                # LMB released inside rect — fire click callback
                if prev == _BtnState.PRESSED:
                    if self._on_click:
                        try:
                            self._on_click()
                        except Exception as e:
                            print(f'[Button] on_click error: {e}')
                self._state = _BtnState.HOVERED
                if prev != _BtnState.HOVERED and self._on_hover:
                    self._on_hover()
        else:
            if prev == _BtnState.HOVERED and self._on_exit:
                self._on_exit()
            self._state = _BtnState.NORMAL

    def UIRender(self, screen: pygame.Surface) -> None:
        """Blit the current state surface onto *screen*.

        Triggers a surface rebuild via :meth:`_build_surfaces` if
        :attr:`_dirty` is ``True``, ensuring the correct surface is always
        available even if :meth:`UIUpdate` was skipped for the current frame.
        Does nothing if no surface is available for the active state.

        Parameters
        ----------
        screen : pygame.Surface
            The render target, typically the main display surface.
        """
        if self._dirty:
            self._build_surfaces()
        surf = self._surfaces.get(self._state)
        if surf:
            screen.blit(surf, self._rect.topleft)