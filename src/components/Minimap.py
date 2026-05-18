"""
Minimap — procedural dungeon minimap rendered as a ScreenSpace UI component.

Overview
--------
This module provides the :class:`Minimap` component, a self-contained
ScreenSpace overlay that visualises the full layout of a procedurally
generated dungeon as seen through the player's exploration progress.  It
reads live state from a :class:`~dungeon.dungeonManager.DungeonManager` each
frame and redraws itself only when that state changes, keeping per-frame cost
to a minimum.

Responsibilities
----------------
* **State diffing** — compares the current room position and the set of
  visited rooms against a cached snapshot each frame in
  :meth:`~Minimap.UIUpdate` and triggers a full rebuild only on change,
  avoiding redundant surface construction.
* **Room graph rendering** — draws every room in the world map as a small
  rounded rectangle, colour-coded by its exploration status (unknown,
  visited, current, finish), with connecting lines between adjacent rooms
  that share a confirmed door pair.
* **Two-pass surface pipeline** — separates layout into a *raw* surface
  sized to the natural dungeon extents (:meth:`~Minimap._rebuild`) and a
  *scaled* surface fitted into the component's bounding rect while
  preserving the aspect ratio (:meth:`~Minimap._update_scaled_surface`).
  The scaled surface is regenerated whenever the rect changes without
  requiring a full graph rebuild.
* **Resize handling** — overrides :meth:`~Minimap.on_resize` to set the
  dirty flag so that the scaled surface is refreshed when the screen is
  resized.

Visual states
-------------
Each room icon is rendered in one of four exclusive visual states determined
by the following priority order:

=============  ======================  ====================================
Priority       Condition               Appearance
=============  ======================  ====================================
1 (highest)    Current room            Blue fill, gold border, player dot
2              Finish room (not cur)   Dark green fill, green border, ``F``
3              Visited room            Purple fill, light purple border
4 (lowest)     Unvisited room          Near-black fill, dim border, ``?``
=============  ======================  ====================================

Connector lines between adjacent rooms are drawn in one of two styles:
a brighter colour when both neighbours have confirmed matching doors, and a
dimmer colour for rooms where door data is not yet available (e.g. neither
room has been visited).

Room graph coordinate system
-----------------------------
Grid coordinates ``(gx, gy)`` from :attr:`~dungeon.dungeonManager.DungeonManager.world_map`
are mapped to pixel centres on the raw surface by the local ``to_px``
helper inside :meth:`~Minimap._rebuild`::

    px = PADDING + (gx - min_gx) * (ROOM_SIZE + ROOM_GAP) + ROOM_SIZE // 2
    py = PADDING + (gy - min_gy) * (ROOM_SIZE + ROOM_GAP) + ROOM_SIZE // 2

The raw surface is then scaled to fit within the component rect by
:meth:`~Minimap._update_scaled_surface` using ``pygame.transform.smoothscale``.

Usage
-----
    >>> hud = GameObject('HUD')
    >>> minimap = hud.AddComponent(
    ...     Minimap,
    ...     dungeon_manager=dm,
    ...     anchor=UIAnchor.TOP_RIGHT,
    ...     ui_layer=10,
    ... )
"""

import pygame

from core.ui.components.ui_component import UIComponent
from core.ui.ui_anchor import UIAnchor
from dungeon.dungeonManager import DungeonManager


class Minimap(UIComponent):
    """ScreenSpace minimap overlay for a procedurally generated dungeon.

    :class:`Minimap` is intended to be attached to a HUD
    :class:`~core.gameObject.GameObject` via ``AddComponent``.  It queries
    :class:`~dungeon.dungeonManager.DungeonManager` for the world map and
    visited-room set each frame and rebuilds its backing surfaces only when
    either the current room or the visited set changes.

    .. note::
        The component maintains two internal surfaces: :attr:`_raw_surface`,
        drawn at the dungeon's natural pixel scale, and
        :attr:`_scaled_surface`, fitted into the component's bounding rect.
        Only the scaled surface is blit to the screen each frame.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, supplied automatically
        by the component system.
    dungeon_manager : DungeonManager
        The active :class:`~dungeon.dungeonManager.DungeonManager` instance
        from which room layout and exploration state are read each frame.
    anchor : UIAnchor, optional
        Anchor preset used to position the component on screen.
        Defaults to ``None`` (no anchor).
    ui_layer : int, optional
        Render-order layer forwarded to the parent
        :class:`~core.ui.components.ui_component.UIComponent`.  Higher
        values render on top.  Defaults to ``0``.

    Attributes
    ----------
    _dm : DungeonManager
        Reference to the active dungeon manager, read each frame in
        :meth:`UIUpdate`.
    _font : pygame.freetype.Font or None
        Lazily initialised font used to render room labels (``'F'``, ``'?'``).
        Resolved on first call to :meth:`_get_font`.
    _raw_surface : pygame.Surface or None
        Full-resolution composite of the dungeon graph, sized to the natural
        extents of the room grid.  Rebuilt by :meth:`_rebuild` when state
        changes.
    _scaled_surface : pygame.Surface or None
        Aspect-ratio-correct scaled version of :attr:`_raw_surface` fitted
        into the component's bounding rect.  Rebuilt by
        :meth:`_update_scaled_surface` on rect changes and after every
        :meth:`_rebuild`.
    _last_state : tuple or None
        Cached ``(current_position, frozenset(visited))`` snapshot used by
        :meth:`UIUpdate` to detect state changes without a full redraw.
    _last_rect : pygame.Rect or None
        Cached copy of the bounding rect used to detect resize events that
        require the scaled surface to be refreshed.
    _dirty : bool
        When ``True``, forces a full rebuild on the next :meth:`UIUpdate`
        call regardless of whether the dungeon state has changed.  Set by
        :meth:`on_resize` and on construction.
    """

    # ---------------------------------------------------------------- #
    #  Class-level visual constants                                      #
    # ---------------------------------------------------------------- #

    ROOM_SIZE:     int  = 20
    """Pixel side-length of each room icon on the raw surface."""

    ROOM_GAP:      int  = 16
    """Pixel gap between adjacent room icons on the raw surface."""

    PADDING:       int  = 20
    """Pixel margin between the dungeon graph and the raw surface edge."""

    BG_COLOR:      tuple = (10, 10, 26, 210)
    """Background fill of the entire minimap panel."""

    BORDER_COLOR:  tuple = (70, 70, 110, 200)
    """Outer border of the minimap panel."""

    LINE_VISITED:  tuple = (80, 80, 140, 200)
    """Connector line colour between two rooms with confirmed matching doors."""

    LINE_UNKNOWN:  tuple = (45, 45, 75, 140)
    """Connector line colour when door data is unavailable for either room."""

    VISITED_FILL:  tuple = (70, 70, 160, 220)
    """Background fill for a room the player has already entered."""

    VISITED_BORD:  tuple = (110, 110, 200, 255)
    """Border colour for a visited room."""

    CURRENT_FILL:  tuple = (90, 90, 200, 255)
    """Background fill for the room the player is currently in."""

    CURRENT_BORD:  tuple = (255, 215, 0, 255)
    """Border colour for the current room (gold)."""

    UNKNOWN_FILL:  tuple = (28, 28, 48, 180)
    """Background fill for a room the player has not yet visited."""

    UNKNOWN_BORD:  tuple = (55, 55, 85, 170)
    """Border colour for an unvisited room."""

    FINISH_FILL:   tuple = (18, 58, 38, 220)
    """Background fill for the dungeon exit room."""

    FINISH_BORD:   tuple = (55, 195, 115, 255)
    """Border colour for the dungeon exit room (green)."""

    PLAYER_COLOR:  tuple = (255, 215, 0, 255)
    """Colour of the player dot drawn at the centre of the current room icon."""

    NEIGHBORS: dict = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
    """Cardinal direction vectors used when iterating over room adjacency."""

    # ---------------------------------------------------------------- #
    #  Lifecycle                                                         #
    # ---------------------------------------------------------------- #

    def __init__(
        self,
        game_object,
        *,
        dungeon_manager: DungeonManager,
        anchor: UIAnchor = None,
        ui_layer: int = 0,
    ) -> None:
        super().__init__(game_object, ui_layer=ui_layer, anchor=anchor)
        self._dm                = dungeon_manager
        self._font              = None
        self._raw_surface       = None
        self._scaled_surface    = None
        self._last_state        = None
        self._last_rect         = None
        self._dirty: bool       = True

    def on_resize(self, screen_w: int, screen_h: int) -> None:
        """Handle a screen resize event.

        Forwards the new dimensions to the parent
        :class:`~core.ui.components.ui_component.UIComponent` so the
        anchor can recompute the bounding rect, then sets :attr:`_dirty` to
        force a scaled-surface refresh on the next :meth:`UIUpdate` call.

        Parameters
        ----------
        screen_w : int
            New screen width in pixels.
        screen_h : int
            New screen height in pixels.
        """
        super().on_resize(screen_w, screen_h)
        self._dirty = True

    # ---------------------------------------------------------------- #
    #  UIComponent interface                                             #
    # ---------------------------------------------------------------- #

    def UIUpdate(self) -> None:
        """Rebuild backing surfaces if dungeon state or rect has changed.

        Computes a lightweight state key from the current room position and
        the ``frozenset`` of visited room coordinates, then compares it with
        the cached snapshot from the previous frame.  A full rebuild via
        :meth:`_rebuild` is triggered when any of the following conditions
        hold:

        * :attr:`_dirty` is ``True`` (forced rebuild, e.g. after resize).
        * The current room or visited set has changed since the last frame.
        * The bounding rect dimensions have changed (window resize or
          anchor recalculation).

        When none of these conditions apply, the method returns immediately
        with no surface work.
        """
        cur     = self._dm.current_position
        visited = frozenset(self._dm._rooms.keys())
        key     = (cur, visited)
        rect_changed = (self._last_rect != self._rect)

        if self._dirty or key != self._last_state or rect_changed:
            self._last_state = key
            self._last_rect  = self._rect.copy()
            self._rebuild(cur, visited)
            self._dirty = False

    def UIRender(self, screen: pygame.Surface) -> None:
        """Blit the scaled minimap surface onto *screen*.

        Attempts a lazy initialisation of :attr:`_scaled_surface` if it is
        ``None`` (e.g. the first render before :meth:`UIUpdate` has run).
        Does nothing if no scaled surface could be produced.

        Parameters
        ----------
        screen : pygame.Surface
            The render target, typically the main display surface.
        """
        if self._scaled_surface is None:
            self._update_scaled_surface()
        if self._scaled_surface:
            screen.blit(self._scaled_surface, self._rect.topleft)

    # ---------------------------------------------------------------- #
    #  Internal helpers                                                  #
    # ---------------------------------------------------------------- #

    def _get_font(self):
        """Return the shared font used to render room labels.

        Lazily resolves the font from
        :class:`~core.ui.components.tmp_text._FontCache` on first call and
        caches the result in :attr:`_font`.  Subsequent calls return the
        cached instance without touching the font cache.

        Returns
        -------
        pygame.freetype.Font
            The ``'Arial'`` font instance shared across all label draws.
        """
        if self._font is None:
            from core.ui.components.tmp_text import _FontCache
            self._font = _FontCache.get('Arial')
        return self._font

    def _get_connections(self, world_set: set, visited: frozenset) -> list:
        """Build the list of confirmed and speculative room connections.

        Iterates over every pair of grid-adjacent rooms in *world_set*,
        deduplicates edges (each pair is emitted at most once), and checks
        whether both rooms expose a matching door towards each other.  If
        both :class:`~dungeon.room.Room` instances are available in the
        manager's room cache, door presence is verified directly; otherwise
        the connection is marked as unconfirmed.

        Parameters
        ----------
        world_set : set
            Full set of ``(gx, gy)`` grid coordinates present in the world
            map, used to restrict neighbour lookups to valid positions.
        visited : frozenset
            Set of ``(gx, gy)`` coordinates the player has entered.
            Currently accepted by the signature for forward compatibility
            but not used in the filtering logic.

        Returns
        -------
        list[tuple[tuple, tuple, bool]]
            A list of ``(pos_a, pos_b, confirmed)`` triples where *pos_a*
            and *pos_b* are grid-coordinate tuples and *confirmed* is
            ``True`` when both rooms have a matching door on the shared wall.
        """
        DIRECTION_TO_DELTA = {
            'up':    (0, -1), 'down':  (0,  1),
            'left':  (-1, 0), 'right': (1,  0),
        }
        OPPOSITE = {
            'up': 'down', 'down': 'up',
            'left': 'right', 'right': 'left',
        }
        connections = []
        drawn       = set()

        for pos in world_set:
            room = self._dm._rooms.get(pos)
            for direction, (dx, dy) in DIRECTION_TO_DELTA.items():
                nb = (pos[0] + dx, pos[1] + dy)
                if nb not in world_set:
                    continue
                edge = frozenset([pos, nb])
                if edge in drawn:
                    continue
                drawn.add(edge)

                nb_room = self._dm._rooms.get(nb)
                if room is not None and nb_room is not None:
                    has_door_here  = room.get_door_at_direction(direction) is not None
                    has_door_there = nb_room.get_door_at_direction(OPPOSITE[direction]) is not None
                    connections.append((pos, nb, has_door_here and has_door_there))
                else:
                    connections.append((pos, nb, False))

        return connections

    def _is_finish_room(self, pos: tuple) -> bool:
        """Check whether the room at *pos* contains a finish tile.

        Looks up the :class:`~dungeon.room.Room` instance in the manager's
        room cache and scans its tiles for tile type ``3`` (finish / exit).
        Returns ``False`` for rooms that have not yet been constructed (i.e.
        not present in the cache).

        Parameters
        ----------
        pos : tuple[int, int]
            Grid coordinates ``(gx, gy)`` of the room to inspect.

        Returns
        -------
        bool
            ``True`` if at least one tile in the room has ``tile_type == 3``;
            ``False`` otherwise or if the room has not been visited.
        """
        room = self._dm._rooms.get(pos)
        if room is None:
            return False
        for tile in room.tiles:
            if getattr(tile, 'tile_type', -1) == 3:
                return True
        return False

    def _rebuild(self, cur: tuple, visited: frozenset) -> None:
        """Construct the full-resolution dungeon graph surface.

        Computes the pixel extents of the world map, allocates a transparent
        ``SRCALPHA`` surface sized to those extents, and renders in order:

        1. Rounded-rectangle background panel and border.
        2. Connector lines between adjacent rooms (visited style or unknown
           style) via :meth:`_get_connections`.
        3. Room icons (rounded rectangles) colour-coded by exploration status,
           with ``'F'`` / ``'?'`` labels for finish and unvisited rooms.
        4. A gold player dot at the centre of the current room icon.

        The finished surface is stored in :attr:`_raw_surface`, then
        :meth:`_update_scaled_surface` is called immediately to regenerate
        the display-ready :attr:`_scaled_surface`.

        If :attr:`~dungeon.dungeonManager.DungeonManager.world_map` is empty,
        both surfaces are set to ``None`` and the method returns early.

        Parameters
        ----------
        cur : tuple[int, int]
            Grid coordinates of the room the player is currently in.
        visited : frozenset
            ``frozenset`` of grid coordinates the player has entered at
            least once.
        """
        world = self._dm._world_map
        if not world:
            self._raw_surface    = None
            self._scaled_surface = None
            return

        all_pos = list(world.keys())
        all_gx  = [p[0] for p in all_pos]
        all_gy  = [p[1] for p in all_pos]
        min_gx, max_gx = min(all_gx), max(all_gx)
        min_gy, max_gy = min(all_gy), max(all_gy)

        step = self.ROOM_SIZE + self.ROOM_GAP
        P    = self.PADDING

        def to_px(gx: int, gy: int) -> tuple:
            """Map grid coordinates to a pixel centre on the raw surface."""
            x = P + (gx - min_gx) * step + self.ROOM_SIZE // 2
            y = P + (gy - min_gy) * step + self.ROOM_SIZE // 2
            return (x, y)

        surf_w = 2 * P + (max_gx - min_gx) * step + self.ROOM_SIZE
        surf_h = 2 * P + (max_gy - min_gy) * step + self.ROOM_SIZE
        surf   = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)

        # Panel background and border
        pygame.draw.rect(surf, self.BG_COLOR,    (0, 0, surf_w, surf_h), border_radius=8)
        pygame.draw.rect(surf, self.BORDER_COLOR,(0, 0, surf_w, surf_h), width=1, border_radius=8)

        # Connector lines
        world_set   = set(world.keys())
        drawn_edges = set()
        for (gx, gy) in all_pos:
            for (dx, dy) in self.NEIGHBORS.values():
                nb = (gx + dx, gy + dy)
                if nb not in world_set:
                    continue
                edge = frozenset([(gx, gy), nb])
                if edge in drawn_edges:
                    continue
                drawn_edges.add(edge)
                for (pos_a, pos_b, confirmed) in self._get_connections(world_set, visited):
                    color = self.LINE_VISITED if confirmed else self.LINE_UNKNOWN
                    pygame.draw.line(surf, color, to_px(*pos_a), to_px(*pos_b), 2)

        # Room icons
        font = self._get_font()
        for (gx, gy) in all_pos:
            pos      = (gx, gy)
            cx, cy   = to_px(gx, gy)
            rx, ry   = cx - self.ROOM_SIZE // 2, cy - self.ROOM_SIZE // 2
            rect     = pygame.Rect(rx, ry, self.ROOM_SIZE, self.ROOM_SIZE)

            is_cur     = pos == cur
            is_visited = pos in visited
            is_finish  = self._is_finish_room(pos)

            if is_cur:
                fill, bord, bw = self.CURRENT_FILL, self.CURRENT_BORD, 2
            elif is_finish:
                fill, bord, bw = self.FINISH_FILL,  self.FINISH_BORD,  2
            elif is_visited:
                fill, bord, bw = self.VISITED_FILL, self.VISITED_BORD, 1
            else:
                fill, bord, bw = self.UNKNOWN_FILL, self.UNKNOWN_BORD, 1

            pygame.draw.rect(surf, fill, rect, border_radius=3)
            pygame.draw.rect(surf, bord, rect, width=bw, border_radius=3)

            if is_finish and not is_cur:
                font.render_to(surf, (rx + 2, ry + 1), 'F', fgcolor=self.FINISH_BORD, size=7)
            elif not is_visited:
                font.render_to(surf, (rx + 2, ry + 1), '?', fgcolor=self.UNKNOWN_BORD, size=7)

        # Player dot
        if cur in world_set:
            pcx, pcy = to_px(*cur)
            pygame.draw.circle(surf, self.PLAYER_COLOR, (pcx, pcy), 3)

        self._raw_surface = surf
        self._update_scaled_surface()

    def _update_scaled_surface(self) -> None:
        """Scale :attr:`_raw_surface` into the component's bounding rect.

        Computes the largest uniform scale factor that fits the raw surface
        within the bounding rect without cropping, applies it via
        ``pygame.transform.smoothscale``, and centres the result on a
        transparent ``SRCALPHA`` canvas sized to the bounding rect.

        Sets :attr:`_scaled_surface` to ``None`` when :attr:`_raw_surface`
        is ``None`` or the bounding rect has zero area.  Otherwise stores
        the centred, scaled composite in :attr:`_scaled_surface` ready for
        blitting in :meth:`UIRender`.
        """
        if self._raw_surface is None:
            self._scaled_surface = None
            return

        target_w, target_h = self._rect.width, self._rect.height
        if target_w <= 0 or target_h <= 0:
            self._scaled_surface = None
            return

        raw_w, raw_h = self._raw_surface.get_size()
        scale  = min(target_w / raw_w, target_h / raw_h)
        new_w  = max(1, int(raw_w * scale))
        new_h  = max(1, int(raw_h * scale))
        scaled = pygame.transform.smoothscale(self._raw_surface, (new_w, new_h))

        self._scaled_surface = pygame.Surface((target_w, target_h), pygame.SRCALPHA)
        x = (target_w - new_w) // 2
        y = (target_h - new_h) // 2
        self._scaled_surface.blit(scaled, (x, y))