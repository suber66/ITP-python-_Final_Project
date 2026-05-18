"""
Base component architecture for game objects.

Overview
--------
The module provides an abstract :class:`Component` class, which serves as 
the foundation for creating all custom components within the engine. 
Each component is strictly bound to a single :class:`GameObject` instance 
and provides direct access to its spatial data via the :attr:`transform`.

The component's lifecycle is managed externally (typically by the main 
game loop). Depending on the object's current state and the frame, 
the corresponding methods are invoked: :meth:`Awake`, :meth:`Start`, 
:meth:`Update`, etc.

Usage
-----
    >>> from core.gameObject import GameObject
    >>> from component import Component
    >>> class PlayerController(Component):
    ...     def Awake(self) -> None:
    ...         self.speed = 5.0
    ...
    ...     def Update(self) -> None:
    ...         self.transform.position.x += self.speed
    >>>
    >>> obj = GameObject()
    >>> controller = PlayerController(obj)
"""

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.gameObject import GameObject
    from core.transform import Transform


class Component(ABC):
    """Base abstract class for all game object components.

    Components define the behavior, logic, and properties of a :class:`GameObject`. 
    This class encapsulates the base functionality for state management 
    (enabled/disabled) and declares template lifecycle methods.

    Parameters
    ----------
    game_object : GameObject
        The owner game object to which this component is attached upon 
        initialization.

    Attributes
    ----------
    gameObject : GameObject
        Reference to the parent game object. Wrapped in a property (read-only).
    transform : Transform
        Shortcut for quick access to the parent object's transform component. 
        Wrapped in a property (read-only).
    enabled : bool
        The activity state of the component. Changing this property directly 
        automatically invokes the :meth:`OnEnable` or :meth:`OnDisable` methods.

    Notes
    -----
    User scripts should inherit from :class:`Component` and override only 
    the lifecycle methods they actually require.
    """

    def __init__(self, game_object: 'GameObject') -> None:
        self._game_object = game_object
        self._enabled = True

    # ------------------------------------------------------------------
    # Public API & Properties
    # ------------------------------------------------------------------

    @property
    def gameObject(self) -> 'GameObject':
        """GameObject: The game object to which this component is attached."""
        return self._game_object

    @property
    def transform(self) -> 'Transform':
        """Transform: The transform component of the parent object."""
        return self._game_object.transform

    @property
    def enabled(self) -> bool:
        """bool: The current activity status of the component."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if self._enabled != value:
            self._enabled = value
            # State-pattern: trigger OnEnable/OnDisable upon toggling
            if self._enabled:
                self.OnEnable()
            else:
                self.OnDisable()

    # ------------------------------------------------------------------
    # Engine Lifecycle Methods
    # ------------------------------------------------------------------

    def Awake(self) -> None:
        """Called when the component is initialized.

        Guaranteed to be called exactly once during the component's lifetime, 
        before the first :meth:`Start` call. The optimal place for the initial 
        setup of references and internal variables.
        """
        pass

    def OnEnable(self) -> None:
        """Called when the component is activated.

        Triggers immediately after initialization (if the component is created 
        active), and every time the :attr:`enabled` property switches from 
        ``False`` to ``True``.
        """
        pass

    def Start(self) -> None:
        """Called before the first frame update.

        Triggers once during the component's lifetime, provided it is active. 
        Ideal for logic that depends on other components or objects having 
        already passed the :meth:`Awake` stage.
        """
        pass

    def Update(self) -> None:
        """Called every game frame.

        The primary place for implementing frame-by-frame logic, handling 
        user input, and object movement. The method is executed only if the 
        component is active (:attr:`enabled` == ``True``).
        """
        pass

    def LateUpdate(self) -> None:
        """Called every frame after all Update methods have finished.

        Used for logic that must strictly execute after main calculations 
        (e.g., camera tracking scripts to avoid jitter when moving the 
        character in :meth:`Update`).
        """
        pass

    def OnDisable(self) -> None:
        """Called when the component is deactivated.

        Triggers every time the :attr:`enabled` property switches from 
        ``True`` to ``False``, and immediately before the component or 
        object is destroyed.
        """
        pass

    def OnDestroy(self) -> None:
        """Called before the component is finally destroyed.

        Used for memory cleanup, unsubscribing from global events, and 
        gracefully shutting down the script to avoid memory leaks.
        """
        pass