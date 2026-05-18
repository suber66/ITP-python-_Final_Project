"""
Base class for custom user-defined game scripts.

Overview
--------
This module provides the :class:`MonoBehavior` class, which inherits from the 
base :class:`Component`. It serves as the primary abstraction and entry 
point for writing all custom game logic within the engine's architecture.

All scripts managing object behavior, input handling, game mechanics, and 
scene interactions are expected to inherit from this class rather than 
the base component directly.

Usage
-----
    >>> from core.gameObject import GameObject
    >>> from core.monoBehavior import MonoBehavior
    >>> class PlayerMovement(MonoBehavior):
    ...     def Awake(self) -> None:
    ...         self.speed = 10.0
    ...
    ...     def Update(self) -> None:
    ...         self.transform.position.x += self.speed
    >>>
    >>> obj = GameObject()
    >>> movement_script = PlayerMovement(obj)
"""

from core.component import Component


class MonoBehavior(Component):
    """Base class for all user scripts and game logic.

    Provides an extended foundation on top of the standard :class:`Component`, 
    designed specifically for implementing unique game object behaviors.

    While the class currently does not add new properties relative to the 
    base component, it architecturally separates user-defined code from 
    system-level engine modules. Future iterations of the engine will include 
    specific helpers and high-level APIs (e.g., coroutines, delayed calls, 
    child component lookups).

    Parameters
    ----------
    game_object : GameObject
        The owner game object to which this script is attached. 
        Passed to the base :class:`Component` during initialization.

    Notes
    -----
    - **Extensibility**: Future plans include the implementation of 
      delayed execution methods (like ``Invoke()``, ``CancelInvoke()``), 
      coroutine support, and search methods like ``GetComponentInChildren()``.
    - **Inheritance**: Game developers are encouraged to always inherit 
      from :class:`MonoBehavior` when creating game mechanics to ensure 
      compatibility with all future high-level engine features.
    """
    
    # Specific helpers for user scripts (e.g., coroutines, delayed method 
    # invocation, or hierarchy lookups) will be implemented here in the future.
    pass