"""
Main gameplay scene setup and initialization.

Overview
--------
This module defines and registers the primary gameplay loop scene for the 
engine. Upon being loaded by the scene manager, it orchestrates the 
instantiation of all critical game systems and entities required for 
the dungeon level.

Boot Sequence
-------------
1.  **Dungeon Generation**: Instantiates the ``DungeonManager`` to procedurally 
    generate the level and loads the required environmental sprites.
2.  **Timer Setup**: Creates the global game timer for speedrunning mechanics.
3.  **Player Instantiation**: Spawns the player character, assigns physical 
    colliders, rigidbodies, and input controllers, and registers the finish 
    detection logic.
4.  **Camera Setup**: Creates the main camera and attaches a follow component 
    to track the player smoothly.
5.  **HUD Creation**: Initializes the UI canvas, attaching live timers and 
    a minimap to display spatial awareness and progress.
"""

import os
import pygame
from components.Minimap import Minimap
from components.liveTimerText import LiveTimerText
import constants

from core.ui.ui_anchor import UIAnchor
from managers.sceneManager import SceneManager, SceneContext
from core.gameObject import GameObject
from core.gameManager import GameManager
from core import Sprite
from core.camera import Camera
from core.spriteRenderer import SpriteRenderer
from core.ui.canvas import Canvas
from components.cameraFollow import CameraFollow
from components.playerController import PlayerController
from components.boxCollider import BoxCollider
from components.rigidbody import Rigidbody
from components.timer import Timer
from components.finish import Finish
from dungeon import DungeonManager
from geometry import Vector2
from physics import PhysicsLayers
from tools import Console

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')


# ------------------------------------------------------------------ #
#  Registration                                                      #
# ------------------------------------------------------------------ #

def register_game_scene(sm: SceneManager) -> None:
    """Registers the core gameplay scene with the provided SceneManager.

    This function binds the internal scene builder logic to the ``'game'`` 
    scene identifier. It should be called exactly once during the 
    application's initial bootstrap sequence.

    Parameters
    ----------
    sm : SceneManager
        The global scene manager instance responsible for routing and 
        caching scene states.
    """

    @sm.scene('game')
    def game_scene(_: SceneContext) -> None:
        """Constructs the gameplay level, instantiating all required ECS entities.

        Parameters
        ----------
        _ : SceneContext
            Contextual parameters passed during the scene transition 
            (currently unused).
        """
        renderer = GameManager.instance().renderer

        # --------------------------------------------------------------
        # Dungeon Controller Setup
        # --------------------------------------------------------------
        Console.log('Generating dungeon...')
        dungeon_obj = GameObject('DungeonController')
        dm = dungeon_obj.AddComponent(
            DungeonManager,
            total_rooms=15,
            min_room_size=9,
            max_room_size=15,
        )
        dm.generate_dungeon()

        # Load and register base environmental textures
        wall_sprite   = Sprite.load(path=os.path.join(ASSETS_DIR, 'wall.png'))
        floor_sprite  = Sprite.load(path=os.path.join(ASSETS_DIR, 'floor.png'))
        door_sprite   = Sprite.load(path=os.path.join(ASSETS_DIR, 'door.png'))
        finish_sprite = Sprite.load(path=os.path.join(ASSETS_DIR, 'finish.png'))
        
        dm.load_tile_sprites(
            wall_sprite=wall_sprite,
            floor_sprite=floor_sprite,
            door_sprite=door_sprite,
            finish_sprite=finish_sprite,
        )
        renderer.register_object(dungeon_obj)

        # --------------------------------------------------------------
        # Global Timer Setup
        # --------------------------------------------------------------
        timer_obj = GameObject('GameTimer')
        timer = timer_obj.AddComponent(Timer)
        renderer.register_object(timer_obj)

        # --------------------------------------------------------------
        # Player Setup
        # --------------------------------------------------------------
        player = GameObject('Player')
        
        # Position the player in the center of the starting room
        if dm.current_room:
            room = dm.current_room
            cx = room.width  * room.tile_size / 2 * constants.World.GLOBAL_SCALE
            cy = room.height * room.tile_size / 2 * constants.World.GLOBAL_SCALE
            player.transform.position = Vector2(cx, cy)

        player.transform.scale = Vector2(
            constants.World.GLOBAL_SCALE, constants.World.GLOBAL_SCALE)

        player_sprite = Sprite.load(path=os.path.join(ASSETS_DIR, 'Skeleton.png'))
        player.AddComponent(SpriteRenderer, sprite=player_sprite, sorting_layer=10)
        
        # Attach physics and logic controllers
        player.AddComponent(
            BoxCollider,
            layer=PhysicsLayers.PLAYER,
            position_offset=Vector2(0, 10),
            size_offset=Vector2(-12, -24),
        )
        player.AddComponent(Rigidbody)
        player.AddComponent(PlayerController, move_speed=3)

        # Attach finish detection logic
        fd = player.AddComponent(Finish)
        fd.set_timer(timer)
        fd.set_dungeon_manager(dm)

        renderer.register_object(player)
        GameManager.instance().set_player(player)
        dm.set_player(player)

        # --------------------------------------------------------------
        # Main Camera Setup
        # --------------------------------------------------------------
        camera_obj = GameObject('MainCamera')
        camera_obj.transform.position = Vector2(
            player.transform.position.x,
            player.transform.position.y,
        )
        camera_obj.AddComponent(Camera, zoom=1.5)
        camera_obj.AddComponent(CameraFollow, target=player, lerp_speed=0.1)
        renderer.register_object(camera_obj)

        # --------------------------------------------------------------
        # Heads-Up Display (HUD) Canvas Setup
        # --------------------------------------------------------------
        hud_obj = GameObject('HUDCanvas')
        hud_obj.AddComponent(Canvas, sort_layer=200)
        renderer.register_object(hud_obj)

        # Live Timer (Top-Center)
        timer_label_obj = GameObject('HUD_Timer')
        timer_label_obj.AddComponent(
            LiveTimerText,
            game_timer=timer,
            anchor=UIAnchor(anchor_x=0.5, anchor_y=0.0, offset_x=0.0, offset_y=37.0, width=240, height=50),
            ui_layer=1,
        )
        renderer.register_object(timer_label_obj)

        # Minimap (Top-Right)
        minimap_obj = GameObject('HUD_Minimap')
        minimap_obj.AddComponent(
            Minimap,
            dungeon_manager=dm,
            anchor=UIAnchor(
                anchor_x=1.0, anchor_y=0.0,
                offset_x=-125-20,
                offset_y=125+20,
                width=250, height=250,
            ),
            ui_layer=1,
        )
        renderer.register_object(minimap_obj)
        
        # Start the level timer
        timer.start()

        Console.log('[Game] Scene loaded.')