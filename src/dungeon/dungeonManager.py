"""
Dungeon manager — room lifecycle, transitions, and player placement.

Overview
--------
This module provides the :class:`DungeonManager` component, which acts as the
central authority for a procedurally generated dungeon session.  It owns the
full world map produced by :class:`~dungeon.dungeonGenerator.DungeonGenerator`,
manages the pool of instantiated :class:`~dungeon.room.Room` objects, and
orchestrates every room transition the player triggers.

Responsibilities
----------------
* **Generation** — delegates to :class:`~dungeon.dungeonGenerator.DungeonGenerator`
  and stores the resulting world map keyed by grid coordinates.
* **Room lifecycle** — constructs :class:`~dungeon.room.Room` instances on
  demand, caches them for reuse, and calls :meth:`~dungeon.room.Room.unload` /
  :meth:`~dungeon.room.Room.reload` as the player moves between rooms.
* **Sprite assignment** — distributes tile sprites to every tile in a room
  immediately after construction or reload, then triggers background baking.
* **Transitions** — resolves the neighbouring room in a given direction,
  loads it, and teleports the player to the appropriate entry door.
* **Cooldown** — enforces a brief per-transition cooldown (default 30 frames)
  to prevent rapid successive transitions from a single door contact.

Room caching
------------
Once a :class:`~dungeon.room.Room` is constructed it is stored in
``_rooms`` and never destroyed.  On subsequent visits the existing instance
is reused via :meth:`~dungeon.room.Room.reload`, avoiding the overhead of
rebuilding tile game objects.

Player placement
----------------
When a transition completes, the player is teleported to a position 1.5 tiles
inward from the entry door of the new room.  If the expected door tile cannot
be found, the player is placed at the room centre as a safe fallback.

Usage
-----
    >>> dm = player_object.AddComponent(
    ...     DungeonManager,
    ...     total_rooms=50,
    ...     min_room_size=7,
    ...     max_room_size=13,
    ... )
    >>> dm.set_player(player_game_object)
    >>> dm.generate_dungeon()
    >>> dm.load_tile_sprites(
    ...     floor_sprite=floor_img,
    ...     wall_sprite=wall_img,
    ...     door_sprite=door_img,
    ...     finish_sprite=finish_img,
    ... )

    >>> # Triggered by a Door component:
    >>> dm.transition_to_room('up')

    >>> # Check win condition:
    >>> if dm.is_finish_room():
    ...     show_victory_screen()
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from core.gameObject import GameObject
from core.monoBehavior import MonoBehavior
from core.spriteRenderer import SpriteRenderer
from dungeon.dungeonGenerator import DungeonGenerator
from dungeon.room import Room
from geometry import Vector2


class DungeonManager(MonoBehavior):
    """MonoBehavior component that drives a procedurally generated dungeon.

    :class:`DungeonManager` is intended to be attached to a persistent game
    object (e.g. a dedicated ``DungeonManager`` object) via
    ``AddComponent``.  It coordinates dungeon generation, room streaming, and
    player placement across the full dungeon session.

    .. note::
        Call :meth:`generate_dungeon` before any other gameplay method.
        Attempting a transition or querying the current room before generation
        will result in no-ops or ``None`` returns.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, provided automatically
        by the component system.
    total_rooms : int, optional
        Target number of rooms to generate.  Passed directly to
        :class:`~dungeon.dungeonGenerator.DungeonGenerator`.  Defaults to
        ``100``.
    min_room_size : int, optional
        Minimum side length (in tiles) of any generated room.  Defaults to
        ``9``.
    max_room_size : int, optional
        Maximum side length (in tiles) of any generated room.  Defaults to
        ``15``.

    Attributes
    ----------
    OPPOSITE_DIRECTIONS : dict[str, str]
        Class-level mapping from a cardinal direction to its opposite.
        Used to determine which door of the destination room the player
        should enter from.
    """

    OPPOSITE_DIRECTIONS: Dict[str, str] = {
        'up': 'down',
        'down': 'up',
        'left': 'right',
        'right': 'left',
    }

    def __init__(
        self,
        game_object: GameObject,
        total_rooms: int = 100,
        min_room_size: int = 9,
        max_room_size: int = 15,
    ) -> None:
        super().__init__(game_object)
        self._generator = DungeonGenerator(
            total_rooms=total_rooms,
            min_room_size=min_room_size,
            max_room_size=max_room_size,
        )
        self._world_map: Dict[Tuple[int, int], List[List[int]]] = {}
        self._rooms: Dict[Tuple[int, int], Room] = {}
        self._current_room: Optional[Room] = None
        self._current_position: Tuple[int, int] = (0, 0)
        self._generated: bool = False
        self._player: Optional[GameObject] = None
        self._tile_sprites: Dict[int, object] = {}
        self._transition_cooldown: int = 0
        self._TRANSITION_COOLDOWN_FRAMES: int = 30

    def Awake(self) -> None:
        """Called by the component system when the owner object is initialised.

        Currently a no-op; reserved for future startup logic.
        """
        pass

    # ---------------------------------------------------------------------- #
    #  Properties                                                              #
    # ---------------------------------------------------------------------- #

    @property
    def current_room(self) -> Optional[Room]:
        """The :class:`~dungeon.room.Room` instance currently active in the scene.

        Returns ``None`` before :meth:`generate_dungeon` is called or if the
        dungeon has no valid starting room.
        """
        return self._current_room

    @property
    def current_position(self) -> Tuple[int, int]:
        """The grid coordinates ``(col, row)`` of the currently active room."""
        return self._current_position

    @property
    def world_map(self) -> Dict[Tuple[int, int], List[List[int]]]:
        """The raw dungeon layout produced by :meth:`generate_dungeon`.

        Maps grid coordinates ``(col, row)`` to a 2-D tile matrix compatible
        with the :class:`~dungeon.room.Room` constructor.  The dictionary is
        empty until :meth:`generate_dungeon` is called.
        """
        return self._world_map

    # ---------------------------------------------------------------------- #
    #  Configuration                                                           #
    # ---------------------------------------------------------------------- #

    def set_player(self, player: GameObject) -> None:
        """Register the player game object for room-transition teleportation.

        The player reference is used by :meth:`_teleport_player_to_door`
        whenever a transition occurs.  Must be set before the first call to
        :meth:`transition_to_room` if automatic player placement is desired.

        Parameters
        ----------
        player : GameObject
            The player's :class:`~core.gameObject.GameObject`.
        """
        self._player = player

    # ---------------------------------------------------------------------- #
    #  Sprite loading                                                          #
    # ---------------------------------------------------------------------- #

    def load_tile_sprites(
        self,
        floor_sprite=None,
        wall_sprite=None,
        door_sprite=None,
        finish_sprite=None,
    ) -> None:
        """Assign tile sprites and bake the current room's background.

        Builds an internal sprite lookup table indexed by tile type and
        immediately applies sprites to all tiles in the active room, then
        triggers :meth:`~dungeon.room.Room.bake_background`.  Sprites
        assigned here are also applied automatically to every room loaded
        afterwards.

        Parameters
        ----------
        floor_sprite : surface-like or None, optional
            Sprite used for tile type ``0`` (floor).
        wall_sprite : surface-like or None, optional
            Sprite used for tile type ``1`` (wall).
        door_sprite : surface-like or None, optional
            Sprite used for tile type ``2`` (door).
        finish_sprite : surface-like or None, optional
            Sprite used for tile type ``3`` (finish / exit).
        """
        self._tile_sprites = {
            0: floor_sprite,
            1: wall_sprite,
            2: door_sprite,
            3: finish_sprite,
        }
        if self._current_room:
            self._apply_sprites_to_room(self._current_room)
            self._current_room.bake_background()

    def _apply_sprites_to_room(self, room: Room) -> None:
        """Assign the loaded tile sprites to every tile in *room*.

        Iterates over all tiles in *room*, looks up the sprite for each
        tile's ``tile_type`` attribute, and updates the tile's
        :class:`~core.spriteRenderer.SpriteRenderer` accordingly.  Does
        nothing if no sprites have been loaded yet.

        Parameters
        ----------
        room : Room
            The target room whose tiles will receive sprites.
        """
        if not self._tile_sprites:
            return
        for tile in room.tiles:
            sprite = self._tile_sprites.get(getattr(tile, 'tile_type', -1))
            if sprite is not None:
                sr = tile.GetComponent(SpriteRenderer)
                if sr:
                    sr.sprite = sprite
                    sr._update_surface()

    # ---------------------------------------------------------------------- #
    #  Generation                                                              #
    # ---------------------------------------------------------------------- #

    def generate_dungeon(self) -> None:
        """Generate the dungeon layout and load the starting room.

        Delegates world-map generation to the internal
        :class:`~dungeon.dungeonGenerator.DungeonGenerator`, stores the
        result in :attr:`world_map`, and immediately loads the room at grid
        position ``(0, 0)`` as the starting room.

        After this call, :attr:`current_room` and :attr:`current_position`
        are valid and gameplay can begin.
        """
        self._world_map = self._generator.generate()
        self._generated = True
        self._current_position = (0, 0)
        self._load_room(self._current_position)

    def _load_room(self, position: Tuple[int, int]) -> None:
        """Activate the room at *position*, constructing it if necessary.

        If *position* is not present in :attr:`world_map` the method returns
        immediately without side effects.

        The loading sequence is:

        1. Unload the currently active room (if any).
        2. If the target room has not been visited before, construct a new
           :class:`~dungeon.room.Room`, apply sprites, and bake its background.
        3. If the room was previously constructed, call
           :meth:`~dungeon.room.Room.reload` and re-bake the background.
        4. Update :attr:`current_room` and :attr:`current_position`.

        Parameters
        ----------
        position : tuple[int, int]
            Grid coordinates ``(col, row)`` of the room to load.
        """
        if position not in self._world_map:
            return
        if self._current_room is not None:
            self._current_room.unload()

        if position not in self._rooms:
            room_matrix = self._world_map[position]
            room = Room(room_matrix, position, dungeon_manager=self)
            self._rooms[position] = room
            self._apply_sprites_to_room(room)
            room.bake_background()
        else:
            room = self._rooms[position]
            room.reload()
            room.bake_background()

        self._current_room = self._rooms[position]
        self._current_position = position

    # ---------------------------------------------------------------------- #
    #  Room transition                                                         #
    # ---------------------------------------------------------------------- #

    def transition_to_room(self, direction: str) -> bool:
        """Transition the player from the current room through a door.

        Resolves the neighbouring room in *direction*, loads it, teleports
        the player to the opposite entry door, and resets the transition
        cooldown.

        The method is a no-op (returning ``False``) when any of the following
        conditions hold:

        * No room is currently active.
        * The current room has no door in *direction*.
        * The neighbouring grid cell is not present in :attr:`world_map`.

        Parameters
        ----------
        direction : str
            The direction the player is exiting through.  Must be one of
            ``'up'``, ``'down'``, ``'left'``, ``'right'``.

        Returns
        -------
        bool
            ``True`` if the transition succeeded and the new room is now
            active; ``False`` otherwise.
        """
        if not self._current_room:
            return False
        door = self._current_room.get_door_at_direction(direction)
        if not door:
            return False

        (gx, gy) = self._current_position
        if direction == 'up':
            gy -= 1
        elif direction == 'down':
            gy += 1
        elif direction == 'left':
            gx -= 1
        elif direction == 'right':
            gx += 1

        if (gx, gy) not in self._world_map:
            return False

        self._load_room((gx, gy))

        if self._player is not None:
            opposite_dir = self.OPPOSITE_DIRECTIONS[direction]
            self._teleport_player_to_door(opposite_dir)

        self._transition_cooldown = self._TRANSITION_COOLDOWN_FRAMES
        return True

    def _teleport_player_to_door(self, door_direction: str) -> None:
        """Place the player 1.5 tiles inward from the entry door of the current room.

        Locates the door tile matching *door_direction* in the current room
        and offsets the player's position away from the wall so they do not
        immediately re-trigger the door collider.  If the expected door tile
        cannot be found, the player is placed at the room centre as a safe
        fallback.

        Parameters
        ----------
        door_direction : str
            The direction of the entry door in the **new** (destination) room.
            This is always the opposite of the exit direction used to call
            :meth:`transition_to_room`.
        """
        if not self._current_room or not self._player:
            return
        room = self._current_room
        door_tile = None
        for (dx, dy, d) in room.doors:
            if d == door_direction:
                door_tile = room.get_tile_at(dx, dy)
                break

        if door_tile is None:
            # Fallback — place player at room centre
            self._player.transform.position = Vector2(
                room.width * room.tile_size // 2,
                room.height * room.tile_size // 2,
            )
            return

        door_pos = door_tile.transform.position
        offset = room.tile_size * 1.5
        if door_direction == 'up':
            self._player.transform.position = Vector2(door_pos.x, door_pos.y + offset)
        elif door_direction == 'down':
            self._player.transform.position = Vector2(door_pos.x, door_pos.y - offset)
        elif door_direction == 'left':
            self._player.transform.position = Vector2(door_pos.x + offset, door_pos.y)
        elif door_direction == 'right':
            self._player.transform.position = Vector2(door_pos.x - offset, door_pos.y)

    # ---------------------------------------------------------------------- #
    #  Helpers                                                                 #
    # ---------------------------------------------------------------------- #

    def is_finish_room(self) -> bool:
        """Check whether the current room contains a finish tile.

        Scans all tiles in the active room for the ``is_finish`` attribute.
        Returns ``False`` if no room is currently loaded.

        Returns
        -------
        bool
            ``True`` if at least one tile in the current room has
            ``is_finish == True``; ``False`` otherwise.
        """
        if not self._current_room:
            return False
        for tile in self._current_room.tiles:
            if getattr(tile, 'is_finish', False):
                return True
        return False

    def save_to_csv(self, filename: str = 'dungeon.csv') -> None:
        """Export the generated dungeon layout to a CSV file.

        Delegates to :meth:`~dungeon.dungeonGenerator.DungeonGenerator.save_to_csv`.
        Does nothing if the dungeon has not been generated yet.

        Parameters
        ----------
        filename : str, optional
            Destination file path for the CSV export.  Defaults to
            ``'dungeon.csv'``.
        """
        if self._generated:
            self._generator.save_to_csv(filename)

    # ---------------------------------------------------------------------- #
    #  MonoBehavior lifecycle                                                  #
    # ---------------------------------------------------------------------- #

    def Update(self) -> None:
        """Called once per frame by the component system.

        Decrements the transition cooldown counter when it is active, and
        forwards an ``update`` call to the current room if the room exposes
        that method.
        """
        if self._transition_cooldown > 0:
            self._transition_cooldown -= 1
        if self._current_room and hasattr(self._current_room, 'update'):
            self._current_room.update()