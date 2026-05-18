"""
Application entry point and engine initialization sequence.

Overview
--------
This module serves as the primary entry point for the application 
(Project Doomsday). It is responsible for bootstrapping the engine's 
core subsystems in a strict sequence to ensure that the rendering pipeline, 
game managers, and scene registries are fully operational before the 
main execution loop begins.

Boot Order
----------
1. Initialize the underlying Pygame subsystems.
2. Instantiate the main :class:`Renderer` and link it to the global :class:`GameManager`.
3. Retrieve the :class:`SceneManager` singleton.
4. Register all available scenes (e.g., menu, game) via their registration functions.
5. Setup global entities (such as the :class:`CanvasScaler` for UI resolution scaling).
6. Load the initial starting scene (``'menu'``).
7. Transfer control to the :class:`Renderer` to begin the blocking game loop.
"""

import pygame
from core.renderer import Renderer
from core.gameManager import GameManager
from managers.sceneManager import SceneManager
from constants import WindowConfig

# Scene registrations
from scenes.menu_scene import register_menu_scene
from scenes.game_scene import register_game_scene


def main() -> None:
    """Executes the primary engine bootstrap and starts the game loop.

    This function acts as the orchestrator for the engine's startup phase. 
    It applies the window configuration using constants defined in 
    ``WindowConfig``, wires up the singleton managers, registers the 
    application's scenes, and triggers the transition into the first 
    interactive scene.

    Notes
    -----
    The invocation of ``renderer.run()`` at the end of this function is 
    a blocking call. It will capture the main thread and continually 
    execute the frame update and render cycles until the application 
    is explicitly closed by the user or an exit signal is dispatched.
    """
    pygame.init()

    # ------------------------------------------------------------------
    # Core systems initialization
    # ------------------------------------------------------------------
    renderer = Renderer(
        width=WindowConfig.WIDTH,
        height=WindowConfig.HEIGHT,
        refresh_rate=WindowConfig.REFRESH_RATE,
        vsync=WindowConfig.VSYNC,
        title=WindowConfig.TITLE,
        flags=pygame.DOUBLEBUF | pygame.HWSURFACE | pygame.RESIZABLE,
    )
    GameManager.instance().set_renderer(renderer)

    # ------------------------------------------------------------------
    # Scene manager setup
    # ------------------------------------------------------------------
    sm = SceneManager.instance()

    # ------------------------------------------------------------------
    # Register available scenes
    # ------------------------------------------------------------------
    register_menu_scene(sm)
    register_game_scene(sm)

    # ------------------------------------------------------------------
    # Boot sequence finalization
    # ------------------------------------------------------------------
    sm.load_scene('menu')

    # ------------------------------------------------------------------
    # Enter the main execution loop
    # ------------------------------------------------------------------
    renderer.run()


if __name__ == '__main__':
    main()