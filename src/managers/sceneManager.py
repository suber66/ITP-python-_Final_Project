"""
Engine-integrated scene manager with a decorator-based API.

Overview
--------
This module provides the :class:`SceneManager` singleton and the associated 
:class:`SceneContext`. It is responsible for orchestrating the lifecycle 
of different game states (scenes) such as menus, levels, and loading screens.

Scenes are loaded lazily: the registered function acts purely as an 
initialization callback. When a scene is transitioned, the engine safely 
clears all currently active game objects from the previous scene, invoking 
their destruction routines, before calling the new scene's initialization.

Usage
-----
    >>> from managers.sceneManager import SceneManager
    >>> sm = SceneManager.instance()
    >>>
    >>> @sm.scene('menu')
    ... def menu_scene(scene_ctx):
    ...     # Called once when the scene loads.
    ...     # scene_ctx.renderer is available, register GameObjects here.
    ...     pass
    >>>
    >>> # Load a scene (safe to call from mid-frame callbacks/components):
    >>> SceneManager.instance().load_scene('menu')
"""

from typing import Callable, Dict, Optional, List
from tools import Console


class SceneContext:
    """Contextual state passed to scene initialization functions.

    This object serves as a bridge between the scene's setup logic and 
    the engine's core systems. It tracks all entities instantiated during 
    the scene's lifespan to ensure they are properly cleaned up when the 
    scene is eventually unloaded.

    Parameters
    ----------
    name : str
        The string identifier of the scene currently being loaded.

    Attributes
    ----------
    name : str
        The name of the scene.
    renderer : Renderer
        A property providing quick access to the global rendering system.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._owned_objects: List = []   # GameObjects registered in this scene
        self._pending_load: Optional[str] = None  # Queued next scene

    def _register_object(self, obj) -> None:
        """Internally tracks a game object belonging to this scene.

        Parameters
        ----------
        obj : GameObject
            The game object to track for lifecycle management.
        """
        self._owned_objects.append(obj)

    def request_load(self, scene_name: str) -> None:
        """Queues a scene transition via the context.

        This is an alternative, safe method to request a scene change from 
        within the current scene's logic, identical to calling 
        ``SceneManager.load_scene()``.

        Parameters
        ----------
        scene_name : str
            The identifier of the target scene to load.
        """
        self._pending_load = scene_name

    @property
    def renderer(self):
        """Renderer: Quick access to the global rendering pipeline."""
        from core.gameManager import GameManager
        return GameManager.instance().renderer


class SceneManager:
    """Singleton manager controlling the registration and loading of scenes.

    Implements a queued loading mechanism to ensure that scenes are not 
    swapped abruptly in the middle of a frame update, which could cause 
    iterator invalidation and rendering glitches.
    """
    
    _instance: Optional['SceneManager'] = None

    @classmethod
    def instance(cls) -> 'SceneManager':
        """Retrieves the global singleton instance of the SceneManager.

        Returns
        -------
        SceneManager
            The active scene manager instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        if SceneManager._instance is not None:
            raise Exception('SceneManager is a singleton!')
        SceneManager._instance = self

        self._scenes: Dict[str, Callable] = {}
        self._active_scene_name: Optional[str] = None
        self._active_ctx: Optional[SceneContext] = None
        self._pending_load: Optional[str] = None

    # ------------------------------------------------------------------ #
    #  Decorator API                                                       #
    # ------------------------------------------------------------------ #

    def scene(self, name: str) -> Callable:
        """Decorator for registering a scene initialization function.

        Binds the decorated function to a string identifier in the scene 
        registry. The function will be executed whenever the target scene 
        is loaded.

        Parameters
        ----------
        name : str
            The unique string identifier for the scene.

        Returns
        -------
        Callable
            A decorator that registers the function into the internal dictionary.
            
        Examples
        --------
        >>> @sm.scene('main_menu')
        ... def setup_menu(ctx: SceneContext):
        ...     pass
        """
        def decorator(init_func: Callable) -> Callable:
            self._scenes[name] = init_func
            return init_func
        return decorator

    # ------------------------------------------------------------------ #
    #  Load / Unload                                                       #
    # ------------------------------------------------------------------ #

    def load_scene(self, name: str) -> None:
        """Queues a scene to be loaded on the next safe frame boundary.

        This method is safe to call at any point during the game loop, 
        as it merely flags the transition. The actual tear-down and setup 
        occur at the end of the frame via :meth:`flush_pending`.

        Parameters
        ----------
        name : str
            The identifier of the scene to transition to.
        """
        self._pending_load = name

    def _do_load_scene(self, name: str) -> None:
        """Executes the actual scene transition and memory cleanup.

        Unloads the currently active scene by destroying all tracked objects, 
        clears the renderer, creates a new :class:`SceneContext`, and invokes 
        the registered initialization callback for the new scene.

        Parameters
        ----------
        name : str
            The identifier of the scene being loaded.
        """
        if name not in self._scenes:
            Console.error(f'SceneManager: scene "{name}" not found!')
            return

        from core.gameManager import GameManager
        renderer = GameManager.instance().renderer

        # Unload the currently active scene context
        if self._active_ctx:
            Console.log(f'[Scene] Unloading "{self._active_scene_name}"')
            for obj in list(self._active_ctx._owned_objects):
                try:
                    renderer.unregister_object(obj)
                    obj.Destroy()
                except Exception:
                    pass
            self._active_ctx._owned_objects.clear()

        # Wipe remaining artifacts from the rendering pipeline
        renderer.clear_scene()

        # Initialize the new scene context
        ctx = SceneContext(name)
        self._active_ctx = ctx
        self._active_scene_name = name

        Console.log(f'[Scene] Loading "{name}"')
        self._scenes[name](ctx)

    def flush_pending(self) -> None:
        """Applies any queued scene transitions.

        Must be called precisely once per frame (typically at the very end 
        of the Update cycle) to ensure that the scene state changes only 
        when all game logic has stabilized.
        """
        pending = self._pending_load
        if pending:
            self._pending_load = None
            self._do_load_scene(pending)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @property
    def active_scene(self) -> Optional[str]:
        """Optional[str]: The name identifier of the currently running scene."""
        return self._active_scene_name

    @property
    def active_ctx(self) -> Optional[SceneContext]:
        """Optional[SceneContext]: The context object of the currently running scene."""
        return self._active_ctx