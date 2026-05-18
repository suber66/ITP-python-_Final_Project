# Project Doomsday — Engine Technical Documentation

**Developed by:**
- **Sabirzhanov Emil** (AlmazCode)
- **Tyo Evgeniy** (Onicolli)
- **Akhynbay Dias** (suber66)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Engine Architecture](#2-engine-architecture)
3. [Module `core` — Engine Core](#3-module-core--engine-core)
4. [Module `physics` — Physics & Collisions](#4-module-physics--physics--collisions)
5. [Module `components` — Game Components](#5-module-components--game-components)
6. [Module `dungeon` — Dungeon Generation](#6-module-dungeon--dungeon-generation)
7. [Module `managers` — Managers](#7-module-managers--managers)
8. [Module `geometry` — Math Utilities](#8-module-geometry--math-utilities)
9. [Module `utils` — Utilities](#9-module-utils--utilities)
10. [Module `tools` — Developer Tools](#10-module-tools--developer-tools)
11. [Game Prototype — Project Doomsday](#11-game-prototype--project-doomsday)
12. [Entry Point & Scene Setup](#12-entry-point--scene-setup)

---

## 1. Overview

**Project Doomsday Engine** is a custom 2D game engine written in Python on top of Pygame. It implements a **component-object model (COM)** architecture inspired by Unity, featuring a full game object hierarchy, AABB physics with spatial hashing, a resolution-adaptive UI canvas system, a scene manager, procedural dungeon generation, and encrypted save data.

### Technology Stack

| Dependency        | Purpose                                          |
|-------------------|--------------------------------------------------|
| `pygame`          | Rendering, input handling, window management     |
| `pygame.freetype` | Font rendering for UI text                       |
| `cryptography`    | Fernet-based save file encryption                |
| Python 3.11+      | Implementation language                          |

### Key Engine Features

- Component-oriented `GameObject` + `Component` system
- Unity-style lifecycle: `Awake → OnEnable → Start → Update → LateUpdate`
- 2D AABB physics: solid colliders, triggers, depenetration
- Spatial hashing grid for broadphase collision optimization
- UI subsystem with canvases, anchors, and automatic resize handling
- Procedural dungeon generation with shape masks and BFS connectivity repair
- Scene manager with deferred hot-loading
- Encrypted save/load system (Fernet + pickle)
- Tilemap baking — all tiles composited into a single `pygame.Surface` per room

---

## 2. Engine Architecture

```
src/
├── main.py                   # Application entry point
├── constants.py              # Global configuration constants
├── core/                     # Engine core
│   ├── gameObject.py         # Component container
│   ├── component.py          # Abstract base component
│   ├── monoBehavior.py       # Behavior component alias
│   ├── transform.py          # Position, scale, size
│   ├── camera.py             # Camera + world/screen projection
│   ├── renderer.py           # Main game loop + rendering pipeline
│   ├── sprite.py             # Sprite loading and storage
│   ├── spriteRenderer.py     # Sprite draw component
│   ├── tilemapRenderer.py    # Tilemap bake + render component
│   ├── gameManager.py        # Global singleton manager
│   └── ui/
│       ├── canvas.py         # UI canvas (container)
│       ├── ui_anchor.py      # Anchor-based layout system
│       └── components/
│           ├── ui_component.py   # Abstract UI element base
│           ├── tmp_text.py       # Text label element
│           └── button.py         # Interactive button element
├── components/               # Game-specific components
│   ├── playerController.py   # Keyboard movement input
│   ├── rigidbody.py          # Physics movement + depenetration
│   ├── boxCollider.py        # AABB collider
│   ├── cameraFollow.py       # Smooth camera tracking
│   ├── door.py               # Door trigger, room transition
│   ├── finish.py             # Finish tile trigger, timer stop
│   ├── timer.py              # Stopwatch component
│   ├── liveTimerText.py      # HUD live timer display
│   ├── Minimap.py            # HUD minimap renderer
│   └── backgroundPanel.py    # UI decorative panel
├── dungeon/
│   ├── dungeonGenerator.py   # Procedural map generation
│   ├── dungeonManager.py     # Room loading, transitions
│   └── room.py               # Single room build + tile management
├── managers/
│   ├── sceneManager.py       # Scene registration and loading
│   └── saveManager.py        # Encrypted persistent storage
├── physics/
│   └── physicsManager.py     # Collider registry, spatial hash, triggers
├── geometry/
│   └── vector2.py            # 2D vector math
├── utils/
│   ├── color.py              # RGBA color type
│   └── event.py              # Observer/callback event
├── tools/
│   └── console.py            # Colored console logger with stack trace
└── scenes/
    ├── menu_scene.py         # Main menu scene factory
    └── game_scene.py         # Gameplay scene factory
```

### Data Flow Per Frame

```
Renderer.run()  [main loop]
 ├─ _flush_pending()          add/remove GameObjects queued last frame
 ├─ _handle_events()          push pygame events into GameManager
 ├─ GameObject.Update()       all active objects
 │    └─ Component.Update()   PlayerController, DungeonManager, Door, ...
 ├─ PhysicsManager
 │    .process_triggers()     fire on_trigger_enter / on_trigger_exit
 ├─ GameObject.LateUpdate()   CameraFollow runs here
 ├─ Canvas.Update()           UIComponent.UIUpdate() for all UI elements
 ├─ screen.fill()
 ├─ Render world              TilemapRenderer, SpriteRenderer (sorted by layer)
 ├─ Canvas.Render()           UIComponent.UIRender() for all UI elements
 ├─ pygame.display.flip()
 └─ SceneManager.flush_pending()   deferred scene switch if queued
```

---

## 3. Module `core` — Engine Core

### 3.1 `Component` (`core/component.py`)

Abstract base class for every engine component.

| Member | Type | Description |
|---|---|---|
| `gameObject` | `GameObject` | Owning object reference |
| `transform` | `Transform` | Shortcut to `gameObject.transform` |
| `enabled` | `bool` | Toggling calls `OnEnable` / `OnDisable` |

**Lifecycle methods** (all no-ops by default, overridden in subclasses):

| Method | When called |
|---|---|
| `Awake()` | Immediately after `AddComponent()` |
| `OnEnable()` | When enabled or object activated |
| `Start()` | Once, before first `Update()` |
| `Update()` | Every frame |
| `LateUpdate()` | After all `Update()` calls each frame |
| `OnDisable()` | When disabled or object deactivated |
| `OnDestroy()` | On `GameObject.Destroy()` |

---

### 3.2 `MonoBehavior` (`core/monoBehavior.py`)

A pass-through subclass of `Component`. Acts as the semantic equivalent of Unity's `MonoBehaviour` — all gameplay scripts inherit from it rather than `Component` directly. This creates a clear distinction between engine-internal components (`Transform`, `SpriteRenderer`, `Camera`) and user-defined behaviour scripts (`PlayerController`, `Door`, `Finish`).

---

### 3.3 `GameObject` (`core/gameObject.py`)

The fundamental entity in the world. Holds a dictionary of components keyed by their class, so each type can appear at most once per object.

```python
obj = GameObject("Player")
rb  = obj.AddComponent(Rigidbody)
rb2 = obj.GetComponent(Rigidbody)   # returns the same instance
obj.RemoveComponent(Rigidbody)       # calls OnDestroy on the component
obj.SetActive(False)                 # disables all components
obj.Destroy()                        # calls OnDestroy on all components
```

**Lifecycle guarantees:**
- `Awake` fires immediately inside `AddComponent`.
- `Start` fires on the first `Update` call after the object enters the renderer.
- If a component is added after `Start` has already run on the object, `Start` is called immediately on the new component.

---

### 3.4 `Transform` (`core/transform.py`)

Stores and exposes the spatial state of a `GameObject`.

| Property | Type | Description |
|---|---|---|
| `position` | `Vector2` | World-space center position |
| `scale` | `Vector2` | Multiplicative scale factor |
| `size` | `Vector2` | Base size in pixels before scaling |
| `rotation` | `float` | Rotation in degrees (visual reference only; physics uses AABB) |
| `on_changed_callbacks` | `list[Callable]` | Fired on any property change |

`_set_position_silent(v)` sets position without firing callbacks — used internally by `Rigidbody` during depenetration to avoid triggering redundant surface rebuilds mid-frame.

---

### 3.5 `Camera` (`core/camera.py`)

Component that defines the viewport into the world.

| Method | Description |
|---|---|
| `WorldToScreen(world_pos)` | Converts world coordinates to screen pixel coordinates |
| `ScreenToWorld(screen_pos)` | Inverse projection |

**Projection formula:**
```
screen_x = (world_x - camera_x) * zoom + screen_width  / 2
screen_y = (world_y - camera_y) * zoom + screen_height / 2
```

The `Renderer` calls `_get_main_camera()` each frame. If no camera exists it falls back to a `DummyCamera` with zoom = 1 and an identity transform.

---

### 3.6 `Renderer` (`core/renderer.py`)

The central game loop. Created once in `main.py` and owns the Pygame display surface.

**Key responsibilities:**
- Deferred object management: `register_object` / `unregister_object` append to pending lists; `_flush_pending()` applies changes at the safe start of each frame.
- Lazy render list: `_render_components` is sorted by `sorting_layer` and rebuilt only when `_render_list_dirty` is set (on any object add/remove).
- Frustum culling via `_is_visible()` — skips `blit` for sprites whose screen bounds fall entirely outside the window.
- Optional debug overlay: when `GameManager._debug_show_colliders` is true, all active colliders are drawn as colored rectangles (blue for triggers, red for solids).
- `clear_scene()` wipes all objects, canvases, and the physics collider registry — called by `SceneManager` between scene loads.

---

### 3.7 `Sprite` (`core/sprite.py`)

Thin wrapper around a `pygame.Surface` loaded from disk.

```python
sprite = Sprite.load("assets/player.png")  # returns None on failure
sprite.surface   # the pygame.Surface
sprite.size      # Vector2(width, height)
```

Supported formats: `.jpg`, `.jpeg`, `.png`, `.bmp`. All loaded with `convert_alpha()` for per-pixel transparency support.

---

### 3.8 `SpriteRenderer` (`core/spriteRenderer.py`)

Renders a `Sprite` centered at the object's world position as seen through the active camera.

**Cached surface pipeline:**

```
source_surface
  -> _rebuild_scaled()       on transform size or scale change
  -> _rebuild_flipped()      on flip_x or flip_y change
  -> _get_render_surface(zoom)   zoom-scaled surface, cached per zoom value
```

Each stage stores its result and only rebuilds when its inputs change, avoiding repeated `pygame.transform.scale` calls per frame.

`sorting_layer` controls draw order — lower values render first (further back).

---

### 3.9 `TilemapRenderer` (`core/tilemapRenderer.py`)

Optimised renderer for tile-based rooms.

**`bake(tiles)`** composites all tile sprites into one large `pygame.Surface` at their relative world positions. `_world_topleft` records the surface's top-left corner in world space. After baking, individual tile `SpriteRenderer`s are disabled, removing them from the render loop entirely.

On `Render()`, only a single `screen.blit()` is issued per room regardless of tile count, which drastically reduces draw calls compared to rendering each tile individually.

---

### 3.10 UI Subsystem (`core/ui/`)

#### `UIAnchor` (`ui_anchor.py`)

Declarative layout descriptor. Positions and sizes a UI element proportionally to the screen.

```python
UIAnchor(
    anchor_x=0.5,    # 0.0 = left edge, 1.0 = right edge
    anchor_y=0.0,    # 0.0 = top edge,  1.0 = bottom edge
    offset_x=0.0,    # additional pixel offset from anchor point
    offset_y=37.0,
    width=240,
    height=50
)
```

`resolve(screen_w, screen_h)` returns a `pygame.Rect`. Called once on construction and again on every `VIDEORESIZE` event so all UI elements reposition automatically on window resize.

---

#### `Canvas` (`ui/canvas.py`)

A `Component` that acts as an ordered container for `UIComponent`s. Registered with the `Renderer` on `OnEnable`. Multiple canvases are sorted by `sort_layer` (e.g., game HUD at 200 renders on top of menu at 100).

Each frame: calls `UIUpdate()` on all elements, then `UIRender()`.

---

#### `UIComponent` (`ui/components/ui_component.py`)

Abstract base for all UI elements. On `Start` / `OnEnable`, auto-registers with the nearest `Canvas` on the same `GameObject`, falling back to `CanvasRegistry.get_primary()`.

Subclasses implement:
- `UIUpdate()` — per-frame logic (state checks, text refresh)
- `UIRender(screen)` — draw onto the display surface

`on_resize(w, h)` re-resolves the anchor rect and marks the element dirty for a surface rebuild next frame.

---

#### `TMP_Text` (`ui/components/tmp_text.py`)

Rich text label. Features: word-wrap, truncation, multi-line, 8-direction outline, drop shadow, and full horizontal/vertical alignment control. Text is rendered into a cached `pygame.Surface` and only rebuilt when marked dirty.

`_FontCache` stores `pygame.freetype.SysFont` instances keyed by `(name, bold, italic)` — repeated font lookups after the first are free.

---

#### `Button` (`ui/components/button.py`)

Interactive button with four pre-built state surfaces: `NORMAL`, `HOVERED`, `PRESSED`, `DISABLED`. State transitions are evaluated from mouse position and button state each frame. Click fires on mouse-up inside the rect (not on press) to prevent accidental double-triggers during scene transitions.

Supports callbacks: `on_click`, `on_hover`, `on_exit`.

---

## 4. Module `physics` — Physics & Collisions

### 4.1 `PhysicsLayers`

Integer constants used to categorise colliders and filter collision queries.

| Constant | Value | Description |
|---|---|---|
| `DEFAULT` | 0 | Generic objects, door triggers |
| `WALL` | 1 | Impassable solid tiles |
| `OBSTACLE` | 2 | Impassable non-tile objects |
| `PLAYER` | 3 | The player character |
| `NPC` | 4 | Non-player characters |

---

### 4.2 `SpatialHash`

Uniform grid broadphase structure. Divides world space into square cells of `cell_size` pixels (default 64 px).

| Method | Description |
|---|---|
| `insert(collider)` | Places the collider into all cells its AABB overlaps |
| `remove(collider)` | Removes the collider from its cells |
| `query(collider)` | Yields all colliders sharing at least one cell, deduplicated |
| `rebuild(colliders)` | Full rebuild from a fresh collider list |

The `query` generator uses an `id`-based `seen` set so each candidate is returned at most once regardless of how many cells it shares with the source.

---

### 4.3 `PhysicsManager`

Singleton. Owns the master collider list and the spatial hash.

**`process_triggers()`** — called once per frame after all `Update()` calls:

1. Separates all enabled colliders into triggers and solids.
2. For each trigger/solid pair, compares current-frame and previous-frame AABB overlap.
3. Fires `on_trigger_enter` or `on_trigger_exit` on every component of both GameObjects via `_fire()`.
4. Stores current rects as `_prev_rect` for the next comparison.

**`get_collisions(source, target_layer)`** performs a narrowphase `pygame.Rect.colliderect` check on spatial hash candidates.

---

### 4.4 `BoxCollider` (`components/boxCollider.py`)

AABB collider component. The `rect` property is computed from `Transform` on every access:

```
width  = transform.size.x * |transform.scale.x| + size_offset.x
height = transform.size.y * |transform.scale.y| + size_offset.y
center = transform.position + position_offset
```

`is_trigger = True` → participates in trigger events only, not in solid depenetration.

Registers with `PhysicsManager` on `OnEnable`, unregisters on `OnDisable` / `OnDestroy`.

---

### 4.5 `Rigidbody` (`components/rigidbody.py`)

Kinematic physics body. Applies axis-separated movement and depenetration.

**`move(delta: Vector2)`:**
1. Apply X component of delta → `_depenetrate('x')` → push out of all overlapping solid colliders on the X axis.
2. Apply Y component of delta → `_depenetrate('y')` → push out on Y.
3. Fire `_notify_changed()` once at the end.
4. Update the collider's entry in the spatial hash.

**Depenetration (`_resolve_x` / `_resolve_y`):**
- Iterates overlapping solid colliders.
- Chooses the smaller overlap direction (push left vs right, push up vs down).
- Accumulates the total push and shifts `my_rect` in simulation to correctly handle multiple simultaneous contacts (e.g., a corner against two walls).

Solid layers checked: `WALL` and `OBSTACLE`.

---

## 5. Module `components` — Game Components

### 5.1 `PlayerController`

Reads `pygame.key.get_pressed()` every frame and builds a direction vector from WASD / arrow keys. Diagonal movement is not normalized (intentional — allows slightly faster diagonal speed typical in classic top-down games). Flips `SpriteRenderer.flip_x` based on horizontal direction. Delegates movement to `Rigidbody.move()`.

---

### 5.2 `CameraFollow`

Executes in `LateUpdate` (after all physics and transforms have settled). Applies lerp toward the target each frame:

```
new_x = current_x + (target_x - current_x) * lerp_speed
new_y = current_y + (target_y - current_y) * lerp_speed
```

With `lerp_speed = 0.1`, the camera closes 10% of the remaining distance per frame, producing a smooth elastic feel.

---

### 5.3 `Timer`

Wall-clock stopwatch using `time.time()`. Frame-rate independent — no drift from variable frame timing or pauses.

```python
timer.start()            # begin
elapsed = timer.stop()   # stop and return seconds as float
timer.elapsed            # current elapsed (reads live while running)
timer.format(t)          # formats seconds to "MM:SS.ms"
```

---

### 5.4 `Door`

Attached to every door tile. On `on_trigger_enter`, verifies the entering collider is on the `PLAYER` layer, then calls `DungeonManager.transition_to_room(direction)`. A 30-frame cooldown prevents re-triggering immediately after the room loads (the player spawns near the opposite door).

---

### 5.5 `Finish`

Attached to the finish tile (`TILE_FINISH`). Single-fire (`_triggered` flag). On activation:
1. Stops the game timer and reads elapsed time.
2. Compares against `SaveManager.Get('best_time')`.
3. Writes a new best if improved.
4. Loads the menu scene.

---

### 5.6 `LiveTimerText`

HUD UI component displaying the running timer. Polls `timer.elapsed` every `UIUpdate`, formats it to `MM:SS.ms`, and rebuilds its surface only when the string changes. Renders yellow text with a dark outline for readability over any background.

---

### 5.7 `Minimap`

HUD UI component that draws a bird's-eye map of the known dungeon. Rebuilds only when the player's current room or the set of visited rooms changes, or on window resize.

**Render pipeline:**
1. Compute the bounding grid of all rooms in `_world_map`.
2. Draw connector lines between adjacent rooms (solid colour if both sides have matching doors, dim if uncertain).
3. Draw room icons: current room (gold border), finish room (green `F`), visited (blue), unvisited (dark `?`).
4. Draw a gold dot at the player's position.
5. Smooth-scale the raw surface to fit the anchor rect.

---

### 5.8 `BackgroundPanel`

Decorative UI panel. Draws a rounded rectangle with optional border into a cached `pygame.Surface`, rebuilt only on resize.

---

## 6. Module `dungeon` — Dungeon Generation

### 6.1 `DungeonGenerator` (`dungeon/dungeonGenerator.py`)

Produces a `WorldMap` — a `dict` mapping `(grid_x, grid_y)` integer coordinates to 2D tile matrices (lists of lists of ints).

#### Tile Types

| Constant | Value | Description |
|---|---|---|
| `TILE_FLOOR` | 0 | Walkable floor |
| `TILE_WALL` | 1 | Solid wall |
| `TILE_DOOR` | 2 | Door (trigger) |
| `TILE_FINISH` | 3 | Level exit |
| `TILE_VOID` | 4 | Outside the room shape |

#### Generation Steps

**Step 1 — BFS room expansion.** Starting at `(0, 0)`, a queue drives outward expansion. Each dequeued position generates one room, which adds its exits to the queue. If the queue empties before `total_rooms` is reached, the algorithm randomly picks an existing room and resumes growth from there.

**Step 2 — Shape selection.** Each normal room draws a shape from a weighted list:

| Shape | Weight | Description |
|---|---|---|
| `rect` | 28 | Full rectangle |
| `L`, `J` | 8 each | L-shaped rooms |
| `T` | 8 | T-shaped corridor room |
| `plus`, `S`, `U` | 8 each | Cross, stepped, U-shapes |
| `Z`, `F`, `H` | 6 each | Zigzag, asymmetric shapes |
| `diagonal_cut` | 6 | Corner-cut rectangle |
| `octagon` | 6 | Octagonal room |

Shapes with minimum dimension requirements are excluded if the generated room is too small.

**Step 3 — Shape mask.** `_build_shape_mask()` returns a boolean grid. Tiles outside the mask become `TILE_VOID`; border tiles adjacent to void become `TILE_WALL`.

**Step 4 — Interior obstacles.** Normal rooms randomly receive one of 14 obstacle structures (`diamond`, `columns`, `cross`, `box`, `ring`, `spiral_arms`, `alcoves`, `scattered`, etc.) placed around the room center.

**Step 5 — Door placement.** `_open_door()` finds the border tile closest to the room's midpoint on the requested edge and sets it to `TILE_DOOR`.

**Step 6 — Path carving.** `_clear_door_paths()` BFS-checks whether a walkable path exists from just inside the door to the room center. If not, it carves an L-shaped corridor to guarantee intra-room connectivity.

**Step 7 — Void leak sealing.** Removes any floor tiles directly adjacent to void tiles.

**Step 8 — Connectivity repair.** `_check_connectivity()` BFS-traverses the full dungeon graph. Isolated rooms are automatically reconnected by opening a door to a reachable neighbour and carving a path. A `RuntimeWarning` is emitted if any room cannot be repaired.

---

### 6.2 `Room` (`dungeon/room.py`)

Instantiates `GameObject`s for every tile in the room matrix.

**Per tile type:**
- Floor (`0`) → `SpriteRenderer` only, added to the bake list.
- Wall (`1`) → `SpriteRenderer` + `BoxCollider(layer=WALL, is_trigger=False)`.
- Door (`2`) → `SpriteRenderer` + `BoxCollider(is_trigger=True)` + `Door` component.
- Finish (`3`) → `BoxCollider(is_trigger=True)`, `tile.is_finish = True`.

**`bake_background()`** calls `TilemapRenderer.bake()` on all tiles, then disables individual `SpriteRenderer`s — reducing N draw calls to 1.

**`unload()` / `reload()`** toggle collider states and register/unregister the tilemap from the renderer. Previously visited rooms are cached and reloaded instantly without regeneration.

---

### 6.3 `DungeonManager` (`dungeon/dungeonManager.py`)

MonoBehavior orchestrating generation, room loading, and player teleportation.

**`generate_dungeon()`** — runs `DungeonGenerator.generate()` and loads the starting room at `(0, 0)`.

**`transition_to_room(direction)`:**
1. Verifies the current room has a door facing that direction.
2. Computes the neighbouring grid position.
3. Calls `_load_room()` to swap the active room.
4. Teleports the player to just inside the opposite door of the new room.

**`_teleport_player_to_door(door_direction)`** positions the player `1.5 × tile_size` inward from the door tile, preventing immediate re-trigger of the door they just entered through.

---

## 7. Module `managers` — Managers

### 7.1 `SceneManager` (`managers/sceneManager.py`)

Singleton that stores named scene factory functions and handles deferred loading.

```python
sm = SceneManager.instance()

@sm.scene('game')
def game_scene(ctx: SceneContext) -> None:
    # create and register GameObjects
    ...

sm.load_scene('game')   # deferred — actual load at end of current frame
```

**Why deferred?** `load_scene()` is often called from inside `Update()` (e.g. a button click). Immediately destroying all objects mid-update would corrupt active iterations. Instead the load is queued and executed by `flush_pending()` after rendering is complete.

`_do_load_scene()` workflow:
1. Destroys all objects owned by the previous `SceneContext`.
2. Calls `renderer.clear_scene()` to reset renderer and physics state.
3. Creates a new `SceneContext` and invokes the registered factory function.

---

### 7.2 `SaveManager` (`managers/saveManager.py`)

Singleton for persistent, encrypted save data.

**File storage:** `<project_root>/save_data/`. Each key is HMAC-SHA256 hashed with the master key to produce a 24-character filename, making save files opaque on disk.

**Encryption:** Uses `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256). The master key is auto-generated on first run and stored in `save_data/.key`, or read from the `SAVE_MASTER_KEY` environment variable.

**Serialisation:** Values are `pickle`-serialised (any Python object), then encrypted. Writes are atomic via `tempfile.mkstemp` + `os.replace` to prevent corruption on crash.

```python
SaveManager.Set('best_time', 134.72)
t = SaveManager.Get('best_time', None)
SaveManager.Has('best_time')     # True
SaveManager.Delete('best_time')
```

---

## 8. Module `geometry` — Math Utilities

### `Vector2` (`geometry/vector2.py`)

2D vector with full operator overloading supporting both vector-vector and vector-scalar operations.

| Method / Operator | Description |
|---|---|
| `+`, `-`, `*`, `/` | Vector or scalar operand |
| `==` | Component-wise equality |
| `magnitude()` | Euclidean length |
| `normalize()` | Unit vector; returns `(0, 0)` for zero-length |
| `lerp(target, t)` | Linear interpolation, t clamped to [0, 1] |
| `distance_to(other)` | Euclidean distance |
| `dot(other)` | Dot product |
| `copy()` | Returns a new independent `Vector2` |

Properties `x` and `y` fire an optional `Event` on change — used by `Transform.on_changed_callbacks` to notify `SpriteRenderer` to rebuild surfaces. The `xy` property returns a plain `(float, float)` tuple for direct Pygame compatibility.

---

## 9. Module `utils` — Utilities

### `Color` (`utils/color.py`)

RGBA color type with integer components clamped to `[0, 255]`. Provides `.rgb` and `.rgba` tuple accessors for direct use in Pygame draw calls.

### `Event` (`utils/event.py`)

Lightweight observer. Stores a list of callables and invokes all of them on `invoke(*args, **kwargs)`. Used by `Vector2` setters to propagate changes through `Transform` → `SpriteRenderer`.

---

## 10. Module `tools` — Developer Tools

### `Console` (`tools/console.py`)

Structured logger with ANSI color output and automatic stack trace collection.

| Method | Output |
|---|---|
| `Console.log(msg)` | Timestamped white info message |
| `Console.warning(msg)` | Yellow warning + filtered call stack |
| `Console.error(msg)` | Red error + filtered call stack |
| `Console.clear()` | Clears the terminal |

Frames are collected with `inspect.stack()`, filtered to remove internal engine modules, reversed to show the call chain innermost-last (matching Python's standard traceback style). `Console.MAX_FRAMES` limits how many frames are printed.

---

## 11. Game Prototype — Project Doomsday

The engine ships with a complete playable prototype that exercises every major system.

### Concept

A top-down dungeon speedrunner. The player navigates a procedurally generated dungeon of 15 rooms and must reach the exit as quickly as possible. A personal best time is saved between sessions and displayed on the main menu.

### Game Flow

```
Main Menu
  └─ [START GAME] ─→ Game Scene
       ├─ 15-room dungeon generated
       ├─ Timer starts automatically
       ├─ Player moves through rooms via door triggers
       ├─ Minimap updates as rooms are visited
       └─ Finish tile reached
            ├─ Timer stops
            ├─ Best time saved if improved
            └─ Return to Main Menu
```

### Controls

| Input | Action |
|---|---|
| `W` / `Arrow Up` | Move up |
| `S` / `Arrow Down` | Move down |
| `A` / `Arrow Left` | Move left (sprite mirrors) |
| `D` / `Arrow Right` | Move right |

### Scene Object Roster

| Object Name | Components |
|---|---|
| `DungeonController` | `DungeonManager` |
| `GameTimer` | `Timer` |
| `Player` | `Transform`, `SpriteRenderer`, `BoxCollider`, `Rigidbody`, `PlayerController`, `Finish` |
| `MainCamera` | `Transform`, `Camera` (zoom 1.5×), `CameraFollow` |
| `HUDCanvas` | `Canvas` (sort layer 200) |
| `HUD_Timer` | `LiveTimerText` (top-center) |
| `HUD_Minimap` | `Minimap` (top-right, 250×250 px) |

### Assets

| File | Purpose |
|---|---|
| `assets/Skeleton.png` | Player character sprite |
| `assets/floor.png` | Floor tile texture |
| `assets/wall.png` | Wall tile texture |
| `assets/door.png` | Door tile texture (baked, invisible trigger) |
| `assets/finish.png` | Finish tile texture |

### Dungeon & Scene Parameters

| Parameter | Value |
|---|---|
| Total rooms | 15 |
| Min room size | 9 × 9 tiles |
| Max room size | 15 × 15 tiles |
| Tile size | 32 px |
| Global scale | 2× (all tiles and sprites) |
| Camera zoom | 1.5× |
| Player speed | 3 units / frame |
| Camera lerp speed | 0.1 |
| Window resolution | 1280 × 720 (resizable) |
| Target frame rate | 60 FPS (VSync on) |

---

## 12. Entry Point & Scene Setup

### `main.py`

```python
pygame.init()
renderer = Renderer(
    width=1280, height=720,
    refresh_rate=60, vsync=1,
    title='Project Doomsday',
    flags=DOUBLEBUF | HWSURFACE | RESIZABLE
)
GameManager.instance().set_renderer(renderer)

sm = SceneManager.instance()
register_menu_scene(sm)    # registers the 'menu' factory
register_game_scene(sm)    # registers the 'game' factory

sm.load_scene('menu')
renderer.run()             # enters the blocking main loop
```

### `constants.py`

```python
class WindowConfig:
    WIDTH, HEIGHT             = 1280, 720
    REFERENCE_WIDTH, HEIGHT   = 1920, 1080   # baseline for UIAnchor math
    REFRESH_RATE              = 60
    VSYNC                     = 1
    BG_FILL_COLOR             = Colors.BLACK
    TITLE                     = 'Project Doomsday'

class World:
    GLOBAL_SCALE = 2    # uniform tile and sprite scale factor
```

### Scene Registration Pattern

Scenes are defined as decorated factory functions, keeping all scene setup code self-contained:

```python
def register_game_scene(sm: SceneManager) -> None:
    @sm.scene('game')
    def game_scene(ctx: SceneContext) -> None:
        renderer = GameManager.instance().renderer
        # Create, configure, and register all GameObjects here
        renderer.register_object(some_game_object)
        ...
```

The `SceneContext` tracks owned objects so the `SceneManager` can cleanly destroy them when the scene is unloaded.

---

*Documentation prepared for academic defense. All engine and prototype code authored by Sabirzhanov Emil (AlmazCode), Tyo Evgeniy (Onicolli), and Akhynbay Dias (suber66).*