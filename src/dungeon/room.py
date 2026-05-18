"""
Dungeon room — tile construction, lifecycle, and spatial queries.

Overview
--------
This module provides the :class:`Room` class, which represents a single
rectangular room inside a procedurally generated dungeon.  A room is
defined by a 2-D integer matrix in which each cell encodes a tile type:

.. list-table:: Tile type legend
   :header-rows: 1
   :widths: 10 20 70

   * - Value
     - Name
     - Description
   * - ``0``
     - Floor
     - Walkable surface.  Registered as a static tile and baked into the
       background tilemap.
   * - ``1``
     - Wall
     - Impassable surface.  Receives a solid :class:`~components.boxCollider.BoxCollider`
       on the ``WALL`` physics layer and is baked into the background tilemap.
   * - ``2``
     - Door
     - Transition tile placed on a room edge.  Receives a trigger
       :class:`~components.boxCollider.BoxCollider` and a
       :class:`~components.door.Door` component that communicates with the
       :class:`~managers.dungeonManager.DungeonManager`.
   * - ``3``
     - Finish
     - Level-exit tile.  Receives a trigger
       :class:`~components.boxCollider.BoxCollider` so that the
       ``FinishDetector`` system can fire.

Tile layout
-----------
Every tile is a :class:`~core.gameObject.GameObject` whose world position is
centred on its cell.  Positions are scaled by ``constants.World.GLOBAL_SCALE``
so that the room fits seamlessly into the global coordinate system.

After construction the caller should invoke :meth:`Room.bake_background` to
composite all bakeable tiles into a single :class:`~core.tilemapRenderer.TilemapRenderer`
surface, which dramatically reduces per-frame draw calls.  Dynamic tiles
(doors, finish) have their :class:`~core.spriteRenderer.SpriteRenderer`
hidden after baking so they can be managed independently at runtime.

Lifecycle
---------
Rooms are loaded and unloaded by the dungeon manager as the player navigates
between them:

* :meth:`Room.unload` — deregisters the tilemap and all dynamic tiles from
  the renderer, and disables all colliders so that physics no longer reacts
  to this room's geometry.
* :meth:`Room.reload` — reverses the above, bringing the room back into the
  active scene.

Usage
-----
    >>> matrix = [
    ...     [1, 1, 2, 1, 1],
    ...     [1, 0, 0, 0, 1],
    ...     [1, 0, 0, 0, 1],
    ...     [1, 0, 0, 0, 1],
    ...     [1, 1, 1, 1, 1],
    ... ]
    >>> room = Room(matrix, room_position=(0, 0), dungeon_manager=dm)
    >>> room.bake_background()

    >>> # Spatial queries
    >>> door = room.get_door_at_direction('up')
    >>> tile = room.get_tile_at(2, 0)

    >>> # Lifecycle
    >>> room.unload()
    >>> room.reload()
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from components.boxCollider import BoxCollider
from core.gameManager import GameManager
from core.gameObject import GameObject
from core.spriteRenderer import SpriteRenderer
from core.tilemapRenderer import TilemapRenderer
from geometry import Vector2
from physics.physicsManager import PhysicsLayers


class Room:
    """A single rectangular dungeon room built from a 2-D tile matrix.

    :class:`Room` iterates over *room_matrix* during construction, creates one
    :class:`~core.gameObject.GameObject` per cell, attaches the appropriate
    components based on the tile type, and registers a shared
    :class:`~core.tilemapRenderer.TilemapRenderer` with the active renderer.

    The room differentiates between three internal tile categories:

    * **Static tiles** (floors and walls) — geometry that never changes at
      runtime.  Their colliders are toggled en-masse by :meth:`unload` and
      :meth:`reload`.
    * **Dynamic tiles** (doors and finish) — tiles that participate in game
      events and must be individually registered/unregistered with the
      renderer.
    * **Bake tiles** — the union of static and dynamic tiles passed to
      :meth:`~core.tilemapRenderer.TilemapRenderer.bake` when
      :meth:`bake_background` is called.

    .. note::
        Instantiate :class:`Room` only after :class:`~core.gameManager.GameManager`
        has been initialised, as construction immediately registers objects with
        the active renderer.

    Parameters
    ----------
    room_matrix : list[list[int]]
        A 2-D row-major grid of tile type integers (see module-level legend).
        ``room_matrix[0]`` is the top row; ``room_matrix[y][x]`` addresses
        column *x* in row *y*.
    room_position : tuple[int, int], optional
        The logical grid position of this room within the dungeon (column,
        row).  Used externally by the dungeon manager for neighbour lookups;
        the :class:`Room` itself does not interpret this value.  Defaults to
        ``(0, 0)``.
    dungeon_manager : DungeonManager or None, optional
        Reference to the owning dungeon manager, forwarded to each
        :class:`~components.door.Door` component so that door transitions can
        trigger room navigation.  Defaults to ``None``.

    Attributes
    ----------
    room_position : tuple[int, int]
        Logical grid coordinates of the room inside the dungeon.
    width : int
        Number of columns in the tile matrix.
    height : int
        Number of rows in the tile matrix.
    doors : list[tuple[int, int, str]]
        List of ``(x, y, direction)`` tuples, one entry per door tile
        discovered during construction.  *direction* is one of
        ``'up'``, ``'down'``, ``'left'``, ``'right'``.
    tile_size : int
        Logical size of a single tile in pixels before global scaling.
        Fixed at ``32``.
    tiles : list[GameObject]
        Flat, row-major list of every tile :class:`~core.gameObject.GameObject`
        in the room.  Index ``y * width + x`` addresses the tile at column *x*,
        row *y*.
    """

    def __init__(
        self,
        room_matrix: List[List[int]],
        room_position: Tuple[int, int] = (0, 0),
        dungeon_manager=None,
    ) -> None:
        self._room_matrix = room_matrix
        self.room_position = room_position
        self._dungeon_manager = dungeon_manager
        self.width: int = len(room_matrix[0]) if room_matrix else 0
        self.height: int = len(room_matrix) if room_matrix else 0
        self.doors: List[Tuple[int, int, str]] = []
        self.tile_size: int = 32
        self._static_tiles: List[GameObject] = []
        self._dynamic_tiles: List[GameObject] = []
        self._bake_tiles: List[GameObject] = []
        self.tiles: List[GameObject] = []
        self._tilemap: Optional[GameObject] = None
        self._tilemap_renderer: Optional[TilemapRenderer] = None
        self._build_room()

    # ---------------------------------------------------------------------- #
    #  Internal helpers                                                        #
    # ---------------------------------------------------------------------- #

    def _get_door_direction(self, x: int, y: int) -> str:
        """Infer the cardinal direction of a door tile from its position.

        Doors must be placed on the perimeter of the room matrix.  The
        direction is determined by checking which edge the cell lies on, in
        priority order: top → bottom → left → right.  If none of the edge
        conditions match (which should not occur for a valid matrix), the
        method falls back to ``'up'``.

        Parameters
        ----------
        x : int
            Column index of the door tile (0-based).
        y : int
            Row index of the door tile (0-based).

        Returns
        -------
        str
            One of ``'up'``, ``'down'``, ``'left'``, or ``'right'``.
        """
        if y == 0:
            return 'up'
        if y == self.height - 1:
            return 'down'
        if x == 0:
            return 'left'
        if x == self.width - 1:
            return 'right'
        return 'up'

    def _build_room(self) -> None:
        """Construct all tile game objects and register the tilemap renderer.

        Iterates over every cell in ``_room_matrix`` and for each cell:

        1. Creates a :class:`~core.gameObject.GameObject` named
           ``'Tile_<x>_<y>'``.
        2. Positions it at the cell centre in world space, scaled by
           ``constants.World.GLOBAL_SCALE``.
        3. Attaches a :class:`~core.spriteRenderer.SpriteRenderer` at
           sorting layer ``-1``.
        4. Adds type-specific components (colliders, :class:`~components.door.Door`)
           and places the tile into the appropriate internal lists.

        After all tiles are created, a single ``'Room_Tilemap'``
        :class:`~core.gameObject.GameObject` is instantiated, a
        :class:`~core.tilemapRenderer.TilemapRenderer` is attached to it at
        sorting layer ``-10``, and the tilemap is registered with the active
        renderer.

        .. note::
            This method is called automatically by :meth:`__init__` and should
            not be invoked again after construction.
        """
        import constants
        renderer = GameManager.instance().renderer
        for (y, row) in enumerate(self._room_matrix):
            for (x, tile_type) in enumerate(row):
                tile = GameObject(f'Tile_{x}_{y}')
                tile.transform.position = Vector2(
                    (x * self.tile_size + self.tile_size // 2) * constants.World.GLOBAL_SCALE,
                    (y * self.tile_size + self.tile_size // 2) * constants.World.GLOBAL_SCALE,
                )
                tile.transform.size = Vector2(self.tile_size, self.tile_size)
                tile.transform.scale = Vector2(
                    constants.World.GLOBAL_SCALE, constants.World.GLOBAL_SCALE)
                tile.tile_type = tile_type
                tile.AddComponent(SpriteRenderer, sorting_layer=-1)

                if tile_type == 0:   # floor
                    self._static_tiles.append(tile)
                    self._bake_tiles.append(tile)

                elif tile_type == 1:  # wall
                    tile.AddComponent(BoxCollider,
                                      is_trigger=False,
                                      layer=PhysicsLayers.WALL)
                    self._static_tiles.append(tile)
                    self._bake_tiles.append(tile)

                elif tile_type == 2:  # door
                    direction = self._get_door_direction(x, y)
                    self.doors.append((x, y, direction))
                    tile.AddComponent(BoxCollider,
                                      is_trigger=True,
                                      layer=PhysicsLayers.DEFAULT)
                    tile.is_door = True
                    tile.door_direction = direction
                    from components.door import Door
                    tile.AddComponent(Door,
                                      direction=direction,
                                      dungeon_manager=self._dungeon_manager)
                    self._dynamic_tiles.append(tile)
                    self._bake_tiles.append(tile)

                elif tile_type == 3:  # finish
                    tile.is_finish = True
                    # Give it a trigger collider so FinishDetector fires
                    tile.AddComponent(BoxCollider,
                                      is_trigger=True,
                                      layer=PhysicsLayers.DEFAULT)
                    self._dynamic_tiles.append(tile)
                    self._bake_tiles.append(tile)

                self.tiles.append(tile)

        self._tilemap = GameObject('Room_Tilemap')
        self._tilemap_renderer = self._tilemap.AddComponent(
            TilemapRenderer, sorting_layer=-10)
        renderer.register_object(self._tilemap)

    # ---------------------------------------------------------------------- #
    #  Public API                                                              #
    # ---------------------------------------------------------------------- #

    def bake_background(self) -> None:
        """Composite all bakeable tiles into a single tilemap surface.

        Passes every tile in ``_bake_tiles`` to
        :meth:`~core.tilemapRenderer.TilemapRenderer.bake`, which renders
        them onto a shared surface managed by the
        :class:`~core.tilemapRenderer.TilemapRenderer`.  After baking,
        the individual :class:`~core.spriteRenderer.SpriteRenderer`
        components of all dynamic tiles (doors, finish) are disabled so
        they do not overdraw the composited background.

        Call this method once after construction, before the first frame in
        which the room is visible.  Calling it more than once is harmless but
        redundant.
        """
        if self._tilemap_renderer:
            self._tilemap_renderer.bake(self._bake_tiles)
        for tile in self._dynamic_tiles:
            sr = tile.GetComponent(SpriteRenderer)
            if sr:
                sr.enabled = False

    def get_door_at_direction(self, direction: str) -> Optional[Tuple[int, int, str]]:
        """Return the door descriptor for a given cardinal direction.

        Searches :attr:`doors` for an entry whose direction field matches
        *direction*.  Only the first match is returned; the room matrix is
        expected to contain at most one door per edge.

        Parameters
        ----------
        direction : str
            The cardinal direction to search for.  Must be one of
            ``'up'``, ``'down'``, ``'left'``, ``'right'``.

        Returns
        -------
        tuple[int, int, str] or None
            A ``(x, y, direction)`` tuple identifying the door tile, or
            ``None`` if no door exists in that direction.
        """
        for d in self.doors:
            if d[2] == direction:
                return d
        return None

    def get_tile_at(self, x: int, y: int) -> Optional[GameObject]:
        """Return the tile game object at grid coordinates *(x, y)*.

        Converts the 2-D grid coordinates to a flat index into :attr:`tiles`
        using the formula ``y * width + x``.

        Parameters
        ----------
        x : int
            Column index (0-based, left to right).
        y : int
            Row index (0-based, top to bottom).

        Returns
        -------
        GameObject or None
            The tile at the requested position, or ``None`` if the coordinates
            are out of bounds.
        """
        index = y * self.width + x
        if 0 <= index < len(self.tiles):
            return self.tiles[index]
        return None

    def unload(self) -> None:
        """Remove this room from the active scene without destroying it.

        Performs the following operations so that the room is invisible and
        non-interactive while inactive:

        * Unregisters the tilemap from the renderer.
        * Unregisters each dynamic tile from the renderer, disables its
          :class:`~components.boxCollider.BoxCollider`, and re-enables its
          :class:`~core.spriteRenderer.SpriteRenderer` (so it is ready to
          render again on :meth:`reload`).
        * Disables the :class:`~components.boxCollider.BoxCollider` of every
          static tile so that physics ignores the room geometry.

        Call :meth:`reload` to reverse this operation.
        """
        renderer = GameManager.instance().renderer
        renderer.unregister_object(self._tilemap)
        for tile in self._dynamic_tiles:
            renderer.unregister_object(tile)
            col = tile.GetComponent(BoxCollider)
            if col:
                col.enabled = False
            sr = tile.GetComponent(SpriteRenderer)
            if sr:
                sr.enabled = True
        for tile in self._static_tiles:
            col = tile.GetComponent(BoxCollider)
            if col:
                col.enabled = False

    def reload(self) -> None:
        """Bring a previously unloaded room back into the active scene.

        Reverses the effects of :meth:`unload`:

        * Re-registers the tilemap with the renderer.
        * Re-registers each dynamic tile with the renderer and re-enables
          its :class:`~components.boxCollider.BoxCollider`.
        * Re-enables the :class:`~components.boxCollider.BoxCollider` of
          every static tile so that physics resumes for this room's geometry.

        .. note::
            This method does not re-bake the background tilemap.  If
            :meth:`bake_background` was called before :meth:`unload`, the
            baked surface is preserved and will be displayed immediately upon
            reload.
        """
        renderer = GameManager.instance().renderer
        renderer.register_object(self._tilemap)
        for tile in self._dynamic_tiles:
            renderer.register_object(tile)
            col = tile.GetComponent(BoxCollider)
            if col:
                col.enabled = True
        for tile in self._static_tiles:
            col = tile.GetComponent(BoxCollider)
            if col:
                col.enabled = True