"""
Procedural dungeon generation using a breadth-first expansion algorithm.

Overview
--------
This module provides the :class:`DungeonGenerator` class, which produces a
complete dungeon layout as a grid of tile matrices.  The generator expands
outward from an origin cell ``(0, 0)`` using a BFS-style queue, assigning
each reachable grid coordinate a procedurally built :data:`RoomMatrix`.

Tile codes
----------
.. list-table::
   :header-rows: 1
   :widths: 10 90

   * - Code
     - Meaning
   * - ``0``
     - Floor — walkable interior tile.
   * - ``1``
     - Wall — solid boundary or interior obstacle.
   * - ``2``
     - Door / passage opening between adjacent rooms.
   * - ``3``
     - Finish marker — placed only in the final room.
   * - ``4``
     - Void — outside the room shape; treated as impassable solid space.

Room shapes
-----------
Each room is stamped with one of the following shape masks before walls and
doors are applied:

    ``rect``, ``L``, ``J``, ``T``, ``plus``, ``S``, ``U``, ``Z``,
    ``F``, ``H``, ``diagonal_cut``, ``octagon``

Start and finish rooms are always ``rect``; normal rooms are selected using
weighted random sampling with minimum-dimension guards.

Generation algorithm
--------------------
1. A BFS queue seeds the first entry ``(0, 0, None, None, None)``.
2. Each dequeued entry either:

   * **Case A** — the grid cell is already occupied: the two rooms are
     connected retroactively by opening matching doors on both sides.
   * **Case B** — the grid cell is free: a new room is built, its doors are
     opened toward the parent and zero-to-two random exits are enqueued.

3. After the main loop, :meth:`_seal_pending_queue` closes any unmatched
   doors that point at grid cells that were never filled.
4. :meth:`_check_connectivity` runs a graph BFS over all rooms and
   auto-repairs isolated rooms by forcing a door connection to the nearest
   filled neighbour.

Interior structures
-------------------
Normal rooms may contain one of the following interior obstacle patterns
chosen by weighted random selection:

    ``empty``, ``diamond``, ``columns``, ``cross``, ``small_center``,
    ``box``, ``diagonal``, ``checker``, ``pillar_rows``, ``maze_fragment``,
    ``ring``, ``spiral_arms``, ``alcoves``, ``scattered``

Path carving
------------
After doors are placed, :meth:`_clear_door_paths` verifies that a walkable
path connects every door tile to the room centre.  If no such path exists it
carves an L-shaped corridor through walls, ensuring the dungeon is always
fully navigable.

Usage
-----
    >>> gen = DungeonGenerator(total_rooms=50, min_room_size=7, max_room_size=13)
    >>> world_map = gen.generate()
    >>> # world_map[(0, 0)] is the starting RoomMatrix
    >>> gen.save_to_csv('my_dungeon.csv')

Type aliases
------------
:data:`RoomMatrix`
    ``List[List[int]]`` — a 2-D grid of tile codes representing one room.
:data:`WorldMap`
    ``Dict[Tuple[int, int], RoomMatrix]`` — the full dungeon keyed by
    grid coordinates ``(col, row)``.
"""

import csv
import random
import warnings
from collections import deque
from typing import Dict, List, Optional, Set, Tuple


RoomMatrix = List[List[int]]
WorldMap   = Dict[Tuple[int, int], RoomMatrix]


_SHAPE_MIN_DIM: Dict[str, Tuple[int, int]] = {
    "F":            (9,  13),
    "H":            (9,  13),
    "U":            (9,  11),
    "diagonal_cut": (9,   9),
    "octagon":      (9,   9),
    "plus":         (9,   9),
    "ring":         (9,   9),
}
"""Minimum ``(height, width)`` in tiles required before a shape may be used."""

_ALL_SHAPES    = ["rect","L","J","T","plus","S","U","Z","F","H","diagonal_cut","octagon"]
_SHAPE_WEIGHTS = [28,    8,  8,  8,  8,    8,  8,  6,  6,  6,  6,            6]


class DungeonGenerator:
    """Procedural dungeon layout generator.

    :class:`DungeonGenerator` builds a :data:`WorldMap` — a dictionary that
    maps grid coordinates to tile matrices — using a breadth-first expansion
    strategy.  It is consumed by :class:`~dungeon.dungeonManager.DungeonManager`,
    which handles room instantiation and player interaction.

    .. note::
        The generator is stateful: calling :meth:`generate` overwrites any
        previously produced :attr:`world_map`.  Create a fresh instance or
        call :meth:`generate` again to produce a new dungeon.

    Parameters
    ----------
    total_rooms : int, optional
        Target number of rooms to place.  Actual room count may be lower if
        the algorithm cannot find enough free grid cells; a :class:`RuntimeWarning`
        is issued in that case.  Defaults to ``100``.
    min_room_size : int, optional
        Minimum side length (in tiles) of any generated room.  Values below
        ``7`` are clamped to ``7`` to guarantee space for doors and interior
        content.  Defaults to ``9``.
    max_room_size : int, optional
        Maximum side length (in tiles) of any generated room.  Defaults to
        ``15``.
    seed : int or None, optional
        Optional seed for the internal :class:`random.Random` instance.
        Passing the same seed produces a deterministic dungeon.  Defaults to
        ``None`` (non-deterministic).

    Attributes
    ----------
    OPPOSITE_DIRECTIONS : dict[str, str]
        Class-level mapping from each cardinal direction to its opposite.
        Used throughout the generator to find matching doors across room
        boundaries.
    DIRECTION_DELTAS : dict[str, tuple[int, int]]
        Class-level mapping from each cardinal direction to the ``(Δcol, Δrow)``
        offset applied to grid coordinates when moving in that direction.
    TILE_FLOOR : int
        Tile code ``0`` — walkable floor.
    TILE_WALL : int
        Tile code ``1`` — solid wall.
    TILE_DOOR : int
        Tile code ``2`` — door / passage opening.
    TILE_FINISH : int
        Tile code ``3`` — finish marker (placed at the centre of the last room).
    TILE_VOID : int
        Tile code ``4`` — void space outside the room shape.
    world_map : WorldMap
        The dungeon layout produced by the most recent call to :meth:`generate`.
        Empty until :meth:`generate` is called.
    """

    OPPOSITE_DIRECTIONS: Dict[str, str] = {
        "up": "down", "down": "up", "left": "right", "right": "left",
    }
    DIRECTION_DELTAS: Dict[str, Tuple[int, int]] = {
        "up": (0,-1), "down": (0,1), "left": (-1,0), "right": (1,0),
    }

    TILE_FLOOR  = 0
    TILE_WALL   = 1
    TILE_DOOR   = 2
    TILE_FINISH = 3
    TILE_VOID   = 4

    def __init__(
        self,
        total_rooms:    int = 100,
        min_room_size:  int = 9,
        max_room_size:  int = 15,
        seed:           Optional[int] = None,
    ) -> None:
        self.total_rooms   = total_rooms
        self.min_room_size = max(7, min_room_size)
        self.max_room_size = max_room_size
        self.world_map: WorldMap = {}
        self._rng = random.Random(seed)

    # ==================================================================
    # Public API
    # ==================================================================

    def generate(self) -> WorldMap:
        """Run the BFS expansion and return the completed dungeon layout.

        Resets :attr:`world_map` and rebuilds it from scratch, then returns
        the finished map.  The map always contains at least a start room at
        grid position ``(0, 0)`` and a finish room at the last successfully
        placed position.

        After generation:

        * :meth:`_seal_pending_queue` closes unmatched doors.
        * :meth:`_check_connectivity` verifies full graph reachability and
          auto-repairs any isolated rooms.

        If fewer rooms than :attr:`total_rooms` could be placed, a
        :class:`RuntimeWarning` is issued but the partial map is still
        returned.

        Returns
        -------
        WorldMap
            Dictionary mapping grid coordinates ``(col, row)`` to their
            :data:`RoomMatrix`.  The start room is always at ``(0, 0)``.

        Warns
        -----
        RuntimeWarning
            Emitted when the actual room count is less than :attr:`total_rooms`,
            or when unreachable rooms remain after auto-repair.
        """
        self.world_map = {}
        rooms_count = 0
        created_rooms_log: List[Dict] = []
        queue: List[Tuple] = [(0, 0, None, None, None)]

        while rooms_count < self.total_rooms:
            if not queue:
                if not created_rooms_log:
                    break

                found = False
                indices = list(range(len(created_rooms_log)))
                self._rng.shuffle(indices)
                for idx in indices:
                    cand = created_rooms_log[idx]
                    gx, gy = cand["pos"]
                    dirs = ["up","down","left","right"]
                    self._rng.shuffle(dirs)
                    for d in dirs:
                        dx, dy = self.DIRECTION_DELTAS[d]
                        nx, ny = gx+dx, gy+dy
                        if (nx, ny) not in self.world_map:
                            queue.append((nx, ny, d, (gx, gy), d))
                            found = True
                            break
                    if found:
                        break
                if not queue:
                    break
                continue

            gx, gy, entry_dir, parent_pos, parent_exit = queue.pop(0)

            # ---- Case A: already occupied — connect retroactively -------
            if (gx, gy) in self.world_map:
                if parent_pos is not None:
                    child_dir   = self.OPPOSITE_DIRECTIONS[parent_exit]
                    child_room  = self.world_map[(gx, gy)]
                    parent_room = self.world_map[parent_pos]

                    cmid_x, cmid_y = self._find_centre(child_room)
                    pmid_x, pmid_y = self._find_centre(parent_room)

                    self._open_door(child_room, child_dir)
                    self._clear_door_paths(child_room, [child_dir], cmid_x, cmid_y)

                    self._open_door(parent_room, parent_exit)
                    self._clear_door_paths(parent_room, [parent_exit], pmid_x, pmid_y)
                continue

            # ---- Case B: create new room --------------------------------
            width  = self._rng.randint(self.min_room_size, self.max_room_size)
            height = self._rng.randint(self.min_room_size, self.max_room_size)
            if width  % 2 == 0: width  += 1
            if height % 2 == 0: height += 1

            if rooms_count == 0:
                room_type = "start"
            elif rooms_count == self.total_rooms - 1:
                room_type = "finish"
            else:
                room_type = "normal"

            door_directions: List[str] = []
            if entry_dir is not None:
                door_directions.append(self.OPPOSITE_DIRECTIONS[entry_dir])

            if room_type == "start":
                num_exits = 1
            elif room_type == "finish":
                num_exits = 0
            else:
                num_exits = self._rng.choice([1, 1, 2])

            possible_exits = ["up","down","left","right"]
            if entry_dir is not None:
                possible_exits.remove(self.OPPOSITE_DIRECTIONS[entry_dir])
            self._rng.shuffle(possible_exits)
            new_exits = possible_exits[:num_exits]
            door_directions.extend(new_exits)

            room, _, directions = self._generate_room(
                width, height, room_type, door_directions
            )
            self.world_map[(gx, gy)] = room
            created_rooms_log.append({"pos": (gx, gy), "dirs": directions})
            rooms_count += 1

            for d in new_exits:
                dx, dy = self.DIRECTION_DELTAS[d]
                queue.append((gx+dx, gy+dy, d, (gx, gy), d))

        if rooms_count < self.total_rooms:
            warnings.warn(
                f"DungeonGenerator: only {rooms_count}/{self.total_rooms} rooms "
                "could be placed. Consider a larger grid or fewer rooms.",
                RuntimeWarning,
                stacklevel=2,
            )

        self._seal_pending_queue(queue)
        self._check_connectivity()

        return self.world_map

    def save_to_csv(self, filename: str = "dungeon.csv") -> None:
        """Export the generated dungeon layout to a CSV file.

        Writes one row per non-floor tile with its global grid coordinates,
        local tile coordinates, and tile type code.  Floor tiles (code ``0``)
        are omitted to keep file size manageable.

        The output file has the following columns:

        * ``gx`` — grid column of the room.
        * ``gy`` — grid row of the room.
        * ``lx`` — local tile column within the room.
        * ``ly`` — local tile row within the room.
        * ``type`` — tile code (see module-level tile codes table).

        Parameters
        ----------
        filename : str, optional
            Destination file path for the CSV export.  Defaults to
            ``'dungeon.csv'``.

        Raises
        ------
        OSError
            If the file cannot be created or written to.
        """
        with open(filename, mode="w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["gx","gy","lx","ly","type"])
            for (gx, gy), room_matrix in self.world_map.items():
                for ly, row in enumerate(room_matrix):
                    for lx, cell in enumerate(row):
                        if cell != 0:
                            writer.writerow([gx, gy, lx, ly, cell])

    # ==================================================================
    # Shape masks
    # ==================================================================

    def _available_shapes(self, height: int, width: int) -> Tuple[List[str], List[int]]:
        """Return shape names and weights compatible with the given room dimensions.

        Filters :data:`_ALL_SHAPES` against :data:`_SHAPE_MIN_DIM` so that
        shapes requiring larger canvases than *height* × *width* are excluded.
        If no shapes pass the filter, ``rect`` is returned as a guaranteed
        fallback.

        Parameters
        ----------
        height : int
            Room height in tiles.
        width : int
            Room width in tiles.

        Returns
        -------
        shapes : list[str]
            Names of eligible shapes.
        weights : list[int]
            Corresponding sampling weights, parallel to *shapes*.
        """
        shapes, weights = [], []
        for shape, weight in zip(_ALL_SHAPES, _SHAPE_WEIGHTS):
            min_h, min_w = _SHAPE_MIN_DIM.get(shape, (0, 0))
            if height >= min_h and width >= min_w:
                shapes.append(shape)
                weights.append(weight)
        if not shapes:
            shapes, weights = ["rect"], [1]
        return shapes, weights

    def _build_shape_mask(self, shape: str, height: int, width: int) -> List[List[bool]]:
        """Build a boolean inclusion mask for the given shape and dimensions.

        Returns a *height* × *width* grid where ``True`` marks cells that
        belong to the room interior and ``False`` marks void regions.  The
        mask is used to stamp tile types and to determine valid door positions.

        Parameters
        ----------
        shape : str
            One of the supported shape identifiers (see module docstring).
        height : int
            Room height in tiles (should be odd for correct centring).
        width : int
            Room width in tiles (should be odd for correct centring).

        Returns
        -------
        list[list[bool]]
            A *height* × *width* boolean mask.
        """
        mask = [[True]*width for _ in range(height)]
        H, W = height, width
        my, mx = H//2, W//2

        def cut(r0: int, r1: int, c0: int, c1: int) -> None:
            for r in range(r0, r1):
                for c in range(c0, c1):
                    if 0 <= r < H and 0 <= c < W:
                        mask[r][c] = False

        if shape == "rect":
            pass
        elif shape == "L":
            cut(my+1, H, mx+1, W)
        elif shape == "J":
            cut(my+1, H, 0, mx)
        elif shape == "T":
            sw = max(1, W//5)
            cut(my+1, H, 0, mx-sw)
            cut(my+1, H, mx+sw+1, W)
        elif shape == "plus":
            sh = max(1, H//4)
            sw = max(1, W//4)
            cut(0,       my-sh,   0,       mx-sw)
            cut(0,       my-sh,   mx+sw+1, W)
            cut(my+sh+1, H,       0,       mx-sw)
            cut(my+sh+1, H,       mx+sw+1, W)
        elif shape == "S":
            split_c = W//3
            cut(0,    my, 0,         split_c)
            cut(my+1, H,  W-split_c, W)
        elif shape == "Z":
            split_c = W//3
            cut(0,    my, W-split_c, W)
            cut(my+1, H,  0,         split_c)
        elif shape == "U":
            sw = max(1, W//4)
            cut(0, my, mx-sw+1, mx+sw)
        elif shape == "F":
            col_w = max(1, W//4)
            cut(my+1, H, col_w*2, W)
            cut(my - my//2, my, col_w*3, W)
        elif shape == "H":
            col_w = max(2, W//4)
            bar_h = max(1, H//4)
            cut(0,          my-bar_h,   col_w, W-col_w)
            cut(my+bar_h+1, H,          col_w, W-col_w)
        elif shape == "diagonal_cut":
            for r in range(H):
                for c in range(W):
                    threshold = mx + round((W-1-mx) * r / max(my, 1))
                    if r < my and c > threshold:
                        mask[r][c] = False
        elif shape == "octagon":
            cut_x = max(1, W//4)
            cut_y = max(1, H//4)
            half  = (cut_x + cut_y) // 2
            for r in range(H):
                for c in range(W):
                    if r < cut_y and c < cut_x and (r + c) < half:
                        mask[r][c] = False
                    if r < cut_y and c >= W-cut_x and (r + (W-1-c)) < half:
                        mask[r][c] = False
                    if r >= H-cut_y and c < cut_x and ((H-1-r) + c) < half:
                        mask[r][c] = False
                    if r >= H-cut_y and c >= W-cut_x and ((H-1-r)+(W-1-c)) < half:
                        mask[r][c] = False

        return mask

    # ==================================================================
    # Door candidate logic (shape-aware)
    # ==================================================================

    def _door_candidates(
        self,
        direction: str,
        height: int,
        width: int,
        mask: List[List[bool]],
        room: Optional[RoomMatrix] = None,
    ) -> List[Tuple[int, int]]:
        """Return valid door positions on the border facing *direction*.

        Scans the appropriate border row or column and collects positions that
        pass :meth:`_is_valid_door_pos`.  Results are sorted by proximity to
        the room's midpoint axis so that the best candidate is always first.

        Parameters
        ----------
        direction : str
            Cardinal direction of the border to scan.  One of ``'up'``,
            ``'down'``, ``'left'``, ``'right'``.
        height : int
            Room height in tiles.
        width : int
            Room width in tiles.
        mask : list[list[bool]]
            Shape inclusion mask — ``True`` where the cell belongs to the room.
        room : RoomMatrix or None, optional
            If provided, tile codes in the existing matrix are used for
            validation instead of the mask alone.  Pass ``None`` during initial
            room construction when the matrix is not yet available.

        Returns
        -------
        list[tuple[int, int]]
            Candidate positions as ``(row, col)`` tuples, sorted nearest-centre
            first.  May be empty if no valid position exists.
        """
        mid_x, mid_y = width//2, height//2
        candidates: List[Tuple[int,int]] = []

        if direction == "up":
            row = 0
            for col in range(1, width-1):
                if self._is_valid_door_pos(row, col, row+1, col, height, width, mask, room):
                    candidates.append((row, col))
            candidates.sort(key=lambda p: abs(p[1]-mid_x))
        elif direction == "down":
            row = height-1
            for col in range(1, width-1):
                if self._is_valid_door_pos(row, col, row-1, col, height, width, mask, room):
                    candidates.append((row, col))
            candidates.sort(key=lambda p: abs(p[1]-mid_x))
        elif direction == "left":
            col = 0
            for row in range(1, height-1):
                if self._is_valid_door_pos(row, col, row, col+1, height, width, mask, room):
                    candidates.append((row, col))
            candidates.sort(key=lambda p: abs(p[0]-mid_y))
        elif direction == "right":
            col = width-1
            for row in range(1, height-1):
                if self._is_valid_door_pos(row, col, row, col-1, height, width, mask, room):
                    candidates.append((row, col))
            candidates.sort(key=lambda p: abs(p[0]-mid_y))

        return candidates

    def _is_valid_door_pos(
        self,
        br: int, bc: int,
        ir: int, ic: int,
        height: int, width: int,
        mask: List[List[bool]],
        room: Optional[RoomMatrix] = None,
    ) -> bool:
        """Check whether a border cell is a geometrically valid door position.

        Validates that the border cell ``(br, bc)`` and its inward neighbour
        ``(ir, ic)`` both belong to the room shape, and that the inward
        neighbour is reachable from at least one additional floor-like tile.
        When *room* is supplied, actual tile codes take precedence over the
        mask for the inward-neighbour check.

        Parameters
        ----------
        br : int
            Row index of the border (potential door) cell.
        bc : int
            Column index of the border cell.
        ir : int
            Row index of the inward neighbour cell (one step inside the room).
        ic : int
            Column index of the inward neighbour cell.
        height : int
            Room height in tiles.
        width : int
            Room width in tiles.
        mask : list[list[bool]]
            Shape inclusion mask.
        room : RoomMatrix or None, optional
            Existing tile matrix used for code-level validation; see
            :meth:`_door_candidates`.

        Returns
        -------
        bool
            ``True`` if the position is suitable for a door; ``False``
            otherwise.
        """
        if not mask[br][bc]:
            return False
        if not (0 <= ir < height and 0 <= ic < width):
            return False
        if not mask[ir][ic]:
            return False

        FLOOR_LIKE = {self.TILE_FLOOR, self.TILE_FINISH}

        if room is not None:
            if room[ir][ic] not in FLOOR_LIKE:
                return False
            for nr, nc in ((ir-1,ic),(ir+1,ic),(ir,ic-1),(ir,ic+1)):
                if nr == br and nc == bc:
                    continue
                if not (0 <= nr < height and 0 <= nc < width):
                    continue
                if room[nr][nc] in FLOOR_LIKE:
                    return True
            return False
        else:
            for nr, nc in ((ir-1,ic),(ir+1,ic),(ir,ic-1),(ir,ic+1)):
                if nr == br and nc == bc:
                    continue
                if not (0 <= nr < height and 0 <= nc < width):
                    continue
                if mask[nr][nc]:
                    return True
            return False

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _mask_from_room(self, room: RoomMatrix) -> List[List[bool]]:
        """Derive a shape mask from an existing tile matrix.

        Treats any cell that is not :attr:`TILE_VOID` as part of the room
        shape.  Used when a mask is needed for a room that was already
        constructed.

        Parameters
        ----------
        room : RoomMatrix
            The tile matrix to derive the mask from.

        Returns
        -------
        list[list[bool]]
            Boolean mask with the same dimensions as *room*.
        """
        return [[cell != self.TILE_VOID for cell in row] for row in room]

    def _find_centre(self, room: RoomMatrix) -> Tuple[int, int]:
        """Locate the nearest passable tile to the geometric centre of *room*.

        Starts at the geometric midpoint and performs a BFS over the tile
        matrix until a floor-like tile is found.  This accounts for
        non-rectangular shapes where the midpoint may fall in a void or wall
        region.

        Parameters
        ----------
        room : RoomMatrix
            The tile matrix to search.

        Returns
        -------
        tuple[int, int]
            ``(col, row)`` of the nearest passable tile.  Falls back to the
            geometric midpoint if no passable tile is reachable.
        """
        h, w = len(room), len(room[0])
        mid_y, mid_x = h//2, w//2
        PASSABLE = {self.TILE_FLOOR, self.TILE_FINISH}
        if room[mid_y][mid_x] in PASSABLE:
            return mid_x, mid_y
        visited: Set[Tuple[int,int]] = {(mid_y, mid_x)}
        q: deque = deque([(mid_y, mid_x)])
        while q:
            cy, cx = q.popleft()
            if room[cy][cx] in PASSABLE:
                return cx, cy
            for ny, nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
                if 0 <= ny < h and 0 <= nx < w and (ny,nx) not in visited:
                    visited.add((ny, nx))
                    q.append((ny, nx))
        return mid_x, mid_y

    def _open_door(self, room: RoomMatrix, direction: str) -> Optional[Tuple[int,int]]:
        """Place a door tile on the border of *room* facing *direction*.

        Selects the best candidate position using :meth:`_door_candidates`
        (nearest to the room's midpoint axis) and sets its tile code to
        :attr:`TILE_DOOR`.

        Parameters
        ----------
        room : RoomMatrix
            The tile matrix to modify in-place.
        direction : str
            Border to place the door on.  One of ``'up'``, ``'down'``,
            ``'left'``, ``'right'``.

        Returns
        -------
        tuple[int, int] or None
            ``(row, col)`` of the placed door tile, or ``None`` if no valid
            candidate position exists.
        """
        h, w = len(room), len(room[0])
        mask = self._mask_from_room(room)
        candidates = self._door_candidates(direction, h, w, mask, room)
        if not candidates:
            return None
        row, col = candidates[0]
        room[row][col] = self.TILE_DOOR
        return (row, col)

    def _seal_pending_queue(self, queue: List[Tuple]) -> None:
        """Close unmatched doors left in the BFS queue after generation ends.

        Iterates over the remaining (unprocessed) queue entries and, for each
        parent room that opened a door toward a grid cell that was never
        filled, converts that door tile back to a wall.

        A door is only sealed if the neighbouring cell either does not exist
        in :attr:`world_map` or exists but has no answering door on its
        corresponding border.  Doors with a confirmed answering counterpart
        are preserved.

        Parameters
        ----------
        queue : list[tuple]
            The BFS queue as it stood when the main generation loop exited.
            Each entry has the form
            ``(gx, gy, entry_dir, parent_pos, parent_exit)``.
        """
        for gx, gy, _entry_dir, parent_pos, parent_exit in queue:
            if parent_pos is None:
                continue
            if parent_pos not in self.world_map:
                continue

            parent_room = self.world_map[parent_pos]
            h, w = len(parent_room), len(parent_room[0])
            mask = self._mask_from_room(parent_room)
            candidates = self._door_candidates(parent_exit, h, w, mask, parent_room)
            if not candidates:
                continue
            row, col = candidates[0]

            neighbor_pos = (gx, gy)
            if neighbor_pos not in self.world_map:
                # Neighbouring room was never created — seal the door.
                if parent_room[row][col] == self.TILE_DOOR:
                    parent_room[row][col] = self.TILE_WALL
            else:
                # Room exists — seal only if there is no answering door.
                neighbor_room = self.world_map[neighbor_pos]
                opp = self.OPPOSITE_DIRECTIONS[parent_exit]
                nh, nw = len(neighbor_room), len(neighbor_room[0])
                if opp == "up":
                    border = [(0,    c) for c in range(nw)]
                elif opp == "down":
                    border = [(nh-1, c) for c in range(nw)]
                elif opp == "left":
                    border = [(r,    0) for r in range(nh)]
                else:
                    border = [(r, nw-1) for r in range(nh)]

                has_answering_door = any(
                    neighbor_room[r][c] == self.TILE_DOOR for r, c in border
                )
                if not has_answering_door and parent_room[row][col] == self.TILE_DOOR:
                    parent_room[row][col] = self.TILE_WALL

    def _clear_door_paths(
        self,
        room: RoomMatrix,
        directions: List[str],
        mid_x: int,
        mid_y: int,
    ) -> None:
        """Ensure every door in *room* has a walkable path to the room centre.

        For each direction in *directions*, the method locates the
        corresponding door tile, then runs a BFS from the cell immediately
        inside the door toward ``(mid_x, mid_y)``.  If no path is found, an
        L-shaped corridor is carved through wall tiles to guarantee
        connectivity.  Void tiles are never carved.

        Parameters
        ----------
        room : RoomMatrix
            The tile matrix to modify in-place.
        directions : list[str]
            Directions for which to verify and repair paths.
        mid_x : int
            Column index of the room's logical centre (from :meth:`_find_centre`).
        mid_y : int
            Row index of the room's logical centre.
        """
        h, w = len(room), len(room[0])
        PASSABLE = {self.TILE_FLOOR, self.TILE_DOOR, self.TILE_FINISH}

        _INNER: Dict[str, Tuple[int,int]] = {
            "up":    (+1,  0),
            "down":  (-1,  0),
            "left":  ( 0, +1),
            "right": ( 0, -1),
        }

        for direction in directions:
            mask = self._mask_from_room(room)
            candidates = self._door_candidates(direction, h, w, mask, room)
            if not candidates:
                continue
            door_y, door_x = candidates[0]
            if room[door_y][door_x] != self.TILE_DOOR:
                continue

            di_r, di_c = _INNER[direction]
            start_y, start_x = door_y + di_r, door_x + di_c

            if not (0 <= start_y < h and 0 <= start_x < w):
                continue
            if not mask[start_y][start_x]:
                continue

            def walkable(y: int, x: int) -> bool:
                on_border = (y == 0 or y == h-1 or x == 0 or x == w-1)
                if on_border:
                    return False
                return room[y][x] in PASSABLE

            visited: Set[Tuple[int,int]] = {(start_y, start_x)}
            bfs_q: deque = deque([(start_y, start_x)])
            found = False
            while bfs_q:
                cy, cx = bfs_q.popleft()
                if cy == mid_y and cx == mid_x:
                    found = True
                    break
                for ny, nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
                    if 0 <= ny < h and 0 <= nx < w and (ny,nx) not in visited:
                        if walkable(ny, nx):
                            visited.add((ny, nx))
                            bfs_q.append((ny, nx))

            if found:
                continue

            def carve(y: int, x: int) -> None:
                if not (0 <= y < h and 0 <= x < w):
                    return
                if room[y][x] != self.TILE_WALL:
                    return
                for ny2, nx2 in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                    if 0 <= ny2 < h and 0 <= nx2 < w and room[ny2][nx2] == self.TILE_VOID:
                        return
                room[y][x] = self.TILE_FLOOR

            if direction == "up":
                for r in range(door_y+1, mid_y+1):
                    carve(r, door_x)
                step = 1 if mid_x >= door_x else -1
                for c in range(door_x, mid_x+step, step):
                    carve(mid_y, c)
            elif direction == "down":
                for r in range(door_y-1, mid_y-1, -1):
                    carve(r, door_x)
                step = 1 if mid_x >= door_x else -1
                for c in range(door_x, mid_x+step, step):
                    carve(mid_y, c)
            elif direction == "left":
                for c in range(door_x+1, mid_x+1):
                    carve(door_y, c)
                step = 1 if mid_y >= door_y else -1
                for r in range(door_y, mid_y+step, step):
                    carve(r, mid_x)
            elif direction == "right":
                for c in range(door_x-1, mid_x-1, -1):
                    carve(door_y, c)
                step = 1 if mid_y >= door_y else -1
                for r in range(door_y, mid_y+step, step):
                    carve(r, mid_x)

    # ==================================================================
    # Void-leak repair
    # ==================================================================

    def _seal_void_leaks(self, room: RoomMatrix, mask: List[List[bool]]) -> None:
        """Convert floor tiles that border void cells into walls.

        Iterates over the room matrix until no floor tile remains directly
        adjacent (4-connected) to a void tile.  This prevents visual and
        logical "leaks" at the boundary between the room shape and the
        surrounding void space.

        Parameters
        ----------
        room : RoomMatrix
            The tile matrix to repair in-place.
        mask : list[list[bool]]
            Shape inclusion mask (used implicitly via the void tiles already
            present in *room*; retained as a parameter for API symmetry).
        """
        h, w = len(room), len(room[0])
        changed = True
        while changed:
            changed = False
            for r in range(h):
                for c in range(w):
                    if room[r][c] != self.TILE_FLOOR:
                        continue
                    for nr, nc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                        if 0 <= nr < h and 0 <= nc < w:
                            if room[nr][nc] == self.TILE_VOID:
                                room[r][c] = self.TILE_WALL
                                changed = True
                                break

    # ==================================================================
    # Connectivity check + auto-repair
    # ==================================================================

    def _check_connectivity(self) -> None:
        """Verify full graph reachability and auto-repair isolated rooms.

        Performs a BFS over the room graph, treating two rooms as connected
        only when a :attr:`TILE_DOOR` tile exists on the shared border.
        Rooms not reachable from the first entry in :attr:`world_map` are
        considered isolated.

        For each isolated room, the method attempts to force a bidirectional
        door connection to the first available filled neighbour using
        :meth:`_open_door` and :meth:`_clear_door_paths`.  A
        :class:`RuntimeWarning` is issued for each room that cannot be
        repaired and for any rooms still unreachable after the repair pass.

        Warns
        -----
        RuntimeWarning
            Emitted when isolated rooms are found, when a specific room
            cannot be connected, and when rooms remain unreachable after the
            full repair attempt.
        """
        if not self.world_map:
            return

        def door_neighbours(gx: int, gy: int) -> List[Tuple[int,int]]:
            result = []
            for d, (dx, dy) in self.DIRECTION_DELTAS.items():
                nb = (gx+dx, gy+dy)
                if nb not in self.world_map:
                    continue
                room = self.world_map[(gx, gy)]
                h, w = len(room), len(room[0])
                if d == "up":    border = [(0,    c) for c in range(w)]
                elif d == "down": border = [(h-1,  c) for c in range(w)]
                elif d == "left": border = [(r,    0) for r in range(h)]
                else:             border = [(r, w-1) for r in range(h)]
                if any(room[r][c] == self.TILE_DOOR for r, c in border):
                    result.append(nb)
            return result

        def bfs_reachable(start: Tuple[int,int]) -> Set[Tuple[int,int]]:
            visited: Set[Tuple[int,int]] = {start}
            q: deque = deque([start])
            while q:
                gx, gy = q.popleft()
                for nb in door_neighbours(gx, gy):
                    if nb not in visited:
                        visited.add(nb)
                        q.append(nb)
            return visited

        start = next(iter(self.world_map))
        reachable = bfs_reachable(start)
        unreachable = [pos for pos in self.world_map if pos not in reachable]

        if not unreachable:
            return

        warnings.warn(
            f"DungeonGenerator: {len(unreachable)} room(s) unreachable — "
            "running auto-repair.",
            RuntimeWarning,
            stacklevel=3,
        )

        repaired = 0
        for iso_pos in unreachable:
            gx, gy = iso_pos
            connected = False
            for d, (dx, dy) in self.DIRECTION_DELTAS.items():
                nb = (gx+dx, gy+dy)
                if nb not in self.world_map:
                    continue
                iso_room = self.world_map[iso_pos]
                nb_room  = self.world_map[nb]
                opp = self.OPPOSITE_DIRECTIONS[d]

                mid_x,  mid_y  = self._find_centre(iso_room)
                nmid_x, nmid_y = self._find_centre(nb_room)

                placed_iso = self._open_door(iso_room, d)
                if placed_iso:
                    self._clear_door_paths(iso_room, [d], mid_x, mid_y)
                    self._open_door(nb_room, opp)
                    self._clear_door_paths(nb_room, [opp], nmid_x, nmid_y)
                    connected = True
                    repaired += 1
                    break

            if not connected:
                warnings.warn(
                    f"DungeonGenerator: could not auto-repair room at {iso_pos} "
                    "(no suitable neighbour found).",
                    RuntimeWarning,
                    stacklevel=3,
                )

        if repaired:
            reachable2 = bfs_reachable(start)
            still_bad = len(self.world_map) - len(reachable2)
            if still_bad > 0:
                warnings.warn(
                    f"DungeonGenerator: {still_bad} room(s) still unreachable "
                    "after auto-repair.",
                    RuntimeWarning,
                    stacklevel=3,
                )

    # ==================================================================
    # Room generation
    # ==================================================================

    def _generate_room(
        self,
        width: int,
        height: int,
        room_type: str = "normal",
        directions_to_place: Optional[List[str]] = None,
    ) -> Tuple[RoomMatrix, List, List[str]]:
        """Build and return a single room tile matrix.

        Constructs a room of the requested type by:

        1. Selecting a shape (always ``rect`` for start/finish rooms).
        2. Applying the shape mask to produce floor and void tiles.
        3. Stamping boundary walls along the mask perimeter.
        4. Optionally placing an interior obstacle structure (normal rooms only).
        5. Placing the finish marker at the centre (finish rooms only).
        6. Opening doors in all requested directions.
        7. Carving paths from each door to the room centre.
        8. Sealing void-adjacent floor tiles.

        Dimensions are silently incremented by 1 if even, ensuring the room
        always has an odd size and a well-defined geometric centre.

        Parameters
        ----------
        width : int
            Desired room width in tiles.  Rounded up to odd if necessary.
        height : int
            Desired room height in tiles.  Rounded up to odd if necessary.
        room_type : str, optional
            One of ``'start'``, ``'finish'``, or ``'normal'``.  Controls
            shape selection, interior structures, and finish marker placement.
            Defaults to ``'normal'``.
        directions_to_place : list[str] or None, optional
            Cardinal directions in which to open doors.  Each direction is
            validated against available candidates before a door is placed;
            invalid directions are silently skipped.  Defaults to ``[]``.

        Returns
        -------
        room : RoomMatrix
            The completed tile matrix.
        reserved : list
            Always an empty list; reserved for future use (e.g. entity spawn
            points).
        valid_dirs : list[str]
            Subset of *directions_to_place* for which doors were successfully
            placed.
        """
        if directions_to_place is None:
            directions_to_place = []
        if width  % 2 == 0: width  += 1
        if height % 2 == 0: height += 1

        if room_type in ("start", "finish"):
            shape = "rect"
        else:
            avail_shapes, avail_weights = self._available_shapes(height, width)
            shape = self._rng.choices(avail_shapes, weights=avail_weights)[0]

        mask = self._build_shape_mask(shape, height, width)

        room: RoomMatrix = [[self.TILE_VOID]*width for _ in range(height)]

        for r in range(height):
            for c in range(width):
                if mask[r][c]:
                    room[r][c] = self.TILE_FLOOR

        for r in range(height):
            for c in range(width):
                if not mask[r][c]:
                    continue
                for nr, nc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                    if nr < 0 or nr >= height or nc < 0 or nc >= width or not mask[nr][nc]:
                        room[r][c] = self.TILE_WALL
                        break

        mid_x, mid_y = self._find_centre(room)

        if room_type == "normal":
            def try_wall(y: int, x: int) -> None:
                if not (0 <= y < height and 0 <= x < width): return
                if not mask[y][x]: return
                if room[y][x] != self.TILE_FLOOR: return
                room[y][x] = self.TILE_WALL

            structure = self._rng.choices(
                ["empty","diamond","columns","cross","small_center","box",
                 "diagonal","checker","pillar_rows","maze_fragment",
                 "ring","spiral_arms","alcoves","scattered"],
                weights=[30,6,6,6,6,6,6,6,6,5,5,5,5,2],
            )[0]

            if structure == "diamond":
                for dy in range(-2,3):
                    for dx in range(-2,3):
                        if abs(dy)+abs(dx) == 2:
                            try_wall(mid_y+dy, mid_x+dx)

            elif structure == "columns":
                for dy, dx in [(-2,-2),(-2,2),(2,-2),(2,2)]:
                    try_wall(mid_y+dy, mid_x+dx)

            elif structure == "cross":
                for dy in range(-2,3): try_wall(mid_y+dy, mid_x)
                for dx in range(-2,3): try_wall(mid_y, mid_x+dx)

            elif structure == "small_center":
                for dy in range(-1,2):
                    for dx in range(-1,2):
                        if dy or dx: try_wall(mid_y+dy, mid_x+dx)

            elif structure == "box":
                for dy in [-2, 2]:
                    for dx in range(-2,3): try_wall(mid_y+dy, mid_x+dx)
                for dx in [-2, 2]:
                    for dy in range(-2,3): try_wall(mid_y+dy, mid_x+dx)

            elif structure == "diagonal":
                reach = min(mid_x, mid_y) - 1
                for i in range(1, reach+1):
                    for sy, sx in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                        try_wall(mid_y+i*sy, mid_x+i*sx)

            elif structure == "checker":
                for dy in range(-3,4,2):
                    for dx in range(-3,4,2):
                        if dy or dx: try_wall(mid_y+dy, mid_x+dx)

            elif structure == "pillar_rows":
                for dx in [-3, 3]:
                    for dy in range(-2,3): try_wall(mid_y+dy, mid_x+dx)

            elif structure == "maze_fragment":
                for sdy,sdx,length,axis in [
                    (-2,-3,4,"h"),(2,0,4,"h"),(-2,-3,3,"v"),(0,3,3,"v")
                ]:
                    for i in range(length):
                        if axis == "h": try_wall(mid_y+sdy, mid_x+sdx+i)
                        else:           try_wall(mid_y+sdy+i, mid_x+sdx)

            elif structure == "ring":
                for dy in range(-4,5):
                    for dx in range(-4,5):
                        if abs(dy)+abs(dx) in (3, 4):
                            try_wall(mid_y+dy, mid_x+dx)
                for gdy, gdx in [(0,-3),(0,3),(-3,0),(3,0)]:
                    ny, nx = mid_y+gdy, mid_x+gdx
                    if (0 <= ny < height and 0 <= nx < width
                            and room[ny][nx] == self.TILE_WALL
                            and mask[ny][nx]):
                        room[ny][nx] = self.TILE_FLOOR

            elif structure == "spiral_arms":
                for (dys,dxs),(dyt,dxt) in [
                    ((-1,0),(0,1)),((0,1),(1,0)),((1,0),(0,-1)),((0,-1),(-1,0))
                ]:
                    for i in range(1,3): try_wall(mid_y+dys*i, mid_x+dxs*i)
                    try_wall(mid_y+dys*2+dyt, mid_x+dxs*2+dxt)

            elif structure == "alcoves":
                margin = 2
                raw_offsets = [
                    (-(height//2-2), 0),
                    ( (height//2-2), 0),
                    (0, -(width//2-2)),
                    (0,  (width//2-2)),
                ]
                safe_offsets = []
                for cdy, cdx in raw_offsets:
                    cy = mid_y + cdy
                    cx = mid_x + cdx
                    if margin <= cy < height-margin and margin <= cx < width-margin:
                        safe_offsets.append((cdy, cdx))
                if safe_offsets:
                    k = self._rng.randint(min(2, len(safe_offsets)), len(safe_offsets))
                    for cdy, cdx in self._rng.sample(safe_offsets, k=k):
                        cy, cx = mid_y+cdy, mid_x+cdx
                        for delta in (-1, 0, 1):
                            if cdy == 0: try_wall(cy+delta, cx)
                            else:        try_wall(cy, cx+delta)

            elif structure == "scattered":
                for _ in range(self._rng.randint(5, 10)):
                    dy = self._rng.randint(-(mid_y-1), mid_y-1)
                    dx = self._rng.randint(-(mid_x-1), mid_x-1)
                    if abs(dy) < 2 and abs(dx) < 2: continue
                    try_wall(mid_y+dy, mid_x+dx)

        if room_type == "finish":
            room[mid_y][mid_x] = self.TILE_FINISH

        valid_dirs = [d for d in directions_to_place
                      if self._door_candidates(d, height, width, mask, room)]

        for d in valid_dirs:
            self._open_door(room, d)

        self._clear_door_paths(room, valid_dirs, mid_x, mid_y)
        self._seal_void_leaks(room, mask)

        return room, [], valid_dirs