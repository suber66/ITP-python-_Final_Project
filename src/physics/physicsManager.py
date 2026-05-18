"""
Core physics and collision detection system.

Overview
--------
This module provides the foundational systems for 2D collision detection 
and spatial awareness. It includes layer definitions, a broad-phase 
spatial hashing algorithm to optimize collision queries, and a centralized 
:class:`PhysicsManager` singleton that orchestrates all physical interactions 
and trigger events within the game loop.

Usage
-----
    >>> from physics.physicsManager import PhysicsManager, PhysicsLayers
    >>> physics = PhysicsManager.instance()
    >>> collisions = physics.get_collisions(my_collider, PhysicsLayers.WALL)
"""

from tools import Console
from typing import Iterator, List, Any, Optional


class PhysicsLayers:
    """Static container for physics layer identifiers.

    Layers are used to categorize colliders (e.g., distinguishing players 
    from walls) allowing systems to filter collision queries efficiently.

    Attributes
    ----------
    DEFAULT : int
        The base layer for standard objects (0).
    WALL : int
        Layer for solid, immovable boundary objects (1).
    OBSTACLE : int
        Layer for internal solid objects or props (2).
    PLAYER : int
        Layer specifically reserved for the player entity (3).
    NPC : int
        Layer for non-player characters and enemies (4).
    LAYER_NAMES : dict of int, str
        A mapping of layer integers to their string representations.
    """
    DEFAULT = 0
    WALL = 1
    OBSTACLE = 2
    PLAYER = 3
    NPC = 4
    
    LAYER_NAMES = {
        0: 'Default', 
        1: 'Wall', 
        2: 'Obstacle', 
        3: 'Player', 
        4: 'NPC'
    }

    @staticmethod
    def get_layer_name(layer: int) -> str:
        """Retrieves the human-readable name of a given physics layer.

        Parameters
        ----------
        layer : int
            The integer identifier of the layer.

        Returns
        -------
        str
            The string name of the layer, or 'Unknown' if not found.
        """
        return PhysicsLayers.LAYER_NAMES.get(layer, 'Unknown')


class SpatialHash:
    """Broad-phase collision optimization using a spatial grid.

    Divides the 2D world space into discrete grid cells of a specified size. 
    By registering colliders into these cells, collision queries can be 
    reduced from checking every object against every other object O(N^2) 
    to only checking objects within the same or adjacent cells, approaching 
    O(1) time complexity for sparse scenes.

    Parameters
    ----------
    cell_size : int, optional
        The width and height of each spatial cell in pixels. Ideally, this 
        should match the average size of entities (e.g., 64px). Defaults to 64.

    Attributes
    ----------
    cell_size : int
        The configured size of the grid cells.
    """

    def __init__(self, cell_size: int = 64) -> None:
        self.cell_size = cell_size
        self._grid: dict = {}

    def _cells(self, rect: Any) -> Iterator[tuple[int, int]]:
        """Yields the grid coordinates intersected by a given rectangle.

        Parameters
        ----------
        rect : pygame.Rect
            The bounding box to map onto the spatial grid.

        Yields
        ------
        tuple of int
            The (x, y) index coordinates of the intersected cells.
        """
        x0 = rect.left // self.cell_size
        x1 = rect.right // self.cell_size
        y0 = rect.top // self.cell_size
        y1 = rect.bottom // self.cell_size
        
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                yield (cx, cy)

    def insert(self, collider: Any) -> None:
        """Registers a collider into the spatial grid.

        Parameters
        ----------
        collider : BoxCollider
            The collider component to insert.
        """
        for cell in self._cells(collider.rect):
            bucket = self._grid.get(cell)
            if bucket is None:
                self._grid[cell] = [collider]
            else:
                bucket.append(collider)

    def remove(self, collider: Any) -> None:
        """Removes a collider from the spatial grid.

        Parameters
        ----------
        collider : BoxCollider
            The collider component to remove.
        """
        for cell in self._cells(collider.rect):
            bucket = self._grid.get(cell)
            if bucket and collider in bucket:
                bucket.remove(collider)
                if not bucket:
                    del self._grid[cell]

    def query(self, collider: Any) -> Iterator[Any]:
        """Finds all potential collision candidates for a given collider.

        Yields unique colliders that occupy the same spatial cells as the 
        target collider, filtering out duplicates automatically.

        Parameters
        ----------
        collider : BoxCollider
            The reference collider generating the query.

        Yields
        ------
        BoxCollider
            A candidate collider residing in overlapping spatial cells.
        """
        seen = set()
        for cell in self._cells(collider.rect):
            for other in self._grid.get(cell, ()):
                oid = id(other)
                if oid not in seen:
                    seen.add(oid)
                    yield other

    def rebuild(self, colliders: List[Any]) -> None:
        """Completely reconstructs the spatial grid.

        Useful for refreshing the grid after massive scene shifts or level loads.

        Parameters
        ----------
        colliders : list of BoxCollider
            The full list of currently active colliders in the engine.
        """
        self._grid.clear()
        for c in colliders:
            if c.enabled:
                self.insert(c)


class PhysicsManager:
    """Singleton manager orchestrating all physics and collision logic.

    Acts as the centralized registry for all physical bodies in the game. 
    It maintains the broad-phase spatial hash and is responsible for firing 
    trigger events (``on_trigger_enter``, ``on_trigger_exit``) by comparing 
    collider states across frames.
    """
    
    _instance = None

    @classmethod
    def instance(cls) -> 'PhysicsManager':
        """Retrieves the global singleton instance of the PhysicsManager.

        Returns
        -------
        PhysicsManager
            The active physics manager instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        if PhysicsManager._instance is not None:
            raise Exception('PhysicsManager is a singleton!')
            
        self._colliders: List[Any] = []
        # Spatial hash cell size configured to accommodate typical entity dimensions
        self._spatial = SpatialHash(cell_size=64)
        PhysicsManager._instance = self

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_collider(self, collider: Any) -> None:
        """Registers a new collider with the physics system.

        Parameters
        ----------
        collider : BoxCollider
            The collider component to begin tracking.
        """
        if collider not in self._colliders:
            self._colliders.append(collider)
            if collider.enabled:
                self._spatial.insert(collider)

    def unregister_collider(self, collider: Any) -> None:
        """Unregisters and removes a collider from the physics system.

        Parameters
        ----------
        collider : BoxCollider
            The collider component to stop tracking.
        """
        if collider in self._colliders:
            self._colliders.remove(collider)
            self._spatial.remove(collider)

    # ------------------------------------------------------------------
    # Collision Query
    # ------------------------------------------------------------------

    def get_collisions(self, source_collider: Any, target_layer: Optional[int] = None) -> List[Any]:
        """Finds all active overlapping colliders against a source collider.

        Utilizes the spatial hash to perform a rapid broad-phase check, 
        followed by a precise AABB (Axis-Aligned Bounding Box) intersection check.

        Parameters
        ----------
        source_collider : BoxCollider
            The collider checking for overlaps.
        target_layer : int, optional
            If provided, filters the results to only include colliders residing 
            on this specific physics layer. Defaults to None.

        Returns
        -------
        list of BoxCollider
            A list of valid, overlapping colliders.
        """
        result = []
        for other in self._spatial.query(source_collider):
            if other is source_collider or not other.enabled:
                continue
            if target_layer is not None and other.layer != target_layer:
                continue
            if source_collider.rect.colliderect(other.rect):
                result.append(other)
        return result

    # ------------------------------------------------------------------
    # Trigger Event Dispatch
    # ------------------------------------------------------------------

    def process_triggers(self) -> None:
        """Evaluates and dispatches trigger interaction events.

        Must be called once per frame from the main game loop. It cross-references 
        the current and previous positional states of all trigger and solid 
        colliders to accurately detect entry (``on_trigger_enter``) and exit 
        (``on_trigger_exit``) events, robustly handling teleports and rapid movements.
        """
        trigger_cols = [c for c in self._colliders if c.enabled and c.is_trigger]
        solid_cols   = [c for c in self._colliders if c.enabled and not c.is_trigger]

        for trigger in trigger_cols:
            trigger_rect      = trigger.rect
            trigger_prev_rect = trigger._prev_rect

            for solid in solid_cols:
                solid_rect      = solid.rect
                solid_prev_rect = solid._prev_rect

                currently_overlapping = trigger_rect.colliderect(solid_rect)

                # Overlap in the previous frame is considered valid only if both 
                # previous rects exist and actually intersected.
                was_overlapping = (
                    trigger_prev_rect is not None and
                    solid_prev_rect   is not None and
                    trigger_prev_rect.colliderect(solid_prev_rect)
                )

                if currently_overlapping and not was_overlapping:
                    self._fire(trigger.gameObject, 'on_trigger_enter', solid)
                    self._fire(solid.gameObject,   'on_trigger_enter', trigger)
                elif not currently_overlapping and was_overlapping:
                    self._fire(trigger.gameObject, 'on_trigger_exit', solid)
                    self._fire(solid.gameObject,   'on_trigger_exit', trigger)

        # Cache the current bounds for the next frame's comparison
        for c in self._colliders:
            if c.enabled:
                c._prev_rect = c.rect.copy()
            else:
                c._prev_rect = None

    @staticmethod
    def _fire(game_object: Any, method: str, other_collider: Any) -> None:
        """Safely invokes a specific method on all components of a GameObject.

        Parameters
        ----------
        game_object : GameObject
            The target entity possessing components to trigger.
        method : str
            The exact string name of the method to invoke 
            (e.g., 'on_trigger_enter').
        other_collider : BoxCollider
            The external collider that initiated the event, passed as an argument.
        """
        if game_object is None:
            return
            
        for comp in list(game_object._components.values()):
            fn = getattr(comp, method, None)
            if callable(fn):
                try:
                    fn(other_collider)
                except Exception as e:
                    Console.error(f'{method} error on {game_object.name}: {e}')

    # ------------------------------------------------------------------
    # Spatial Hash Refresh
    # ------------------------------------------------------------------

    def rebuild_spatial(self) -> None:
        """Forces a complete rebuild of the internal spatial hash grid.

        Should be called manually if bulk movements or massive positional 
        resets occur outside the standard update cycle.
        """
        self._spatial.rebuild(self._colliders)