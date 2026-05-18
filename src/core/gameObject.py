"""
Core container for components and scene entities.

Overview
--------
The module provides the :class:`GameObject` class, which acts as the primary 
entity in the game scene. Following standard Entity-Component System (ECS) 
architecture, a game object itself contains minimal logic; instead, it acts 
as a container for various :class:`Component` instances that define its behavior, 
rendering, and physics.

Every :class:`GameObject` is guaranteed to have a ``Transform`` component 
upon instantiation, representing its position, rotation, and scale in the game world.

Usage
-----
    >>> from core.gameObject import GameObject
    >>> from core.monoBehavior import MonoBehavior
    >>> class PlayerHealth(MonoBehavior):
    ...     def Awake(self) -> None:
    ...         self.hp = 100
    >>>
    >>> player = GameObject("Player")
    >>> health_comp = player.AddComponent(PlayerHealth)
    >>> print(player.name)
    Player
    >>> print(player.GetComponent(PlayerHealth).hp)
    100
"""

from typing import Dict, Type, TypeVar, Optional

from core.component import Component
from core.transform import Transform

from tools import Console


T = TypeVar('T', bound='Component')


class GameObject:
    """Component container representing a distinct entity in the game scene.

    The Game Object manages the lifecycle of all attached components, routing 
    initialization, update, and destruction events to them. It also maintains 
    its own active state, which cascades down to affect the execution of its 
    child components.

    Parameters
    ----------
    name : str, optional
        The name of the game object for identification and debugging purposes. 
        Default is "GameObject".

    Attributes
    ----------
    name : str
        The string identifier of the game object.
    activeSelf : bool
        The local active state of the game object. Read-only property; use 
        :meth:`SetActive` to modify.
    transform : Transform
        Direct reference to the object's mandatory Transform component.
    """

    def __init__(self, name: str = "GameObject") -> None:
        self.name = name
        self._components: Dict[Type, 'Component'] = {}
        self._activeSelf = True
        self._started = False
        
        # Every Entity in this architecture always has a Transform by default.
        self._transform = self.AddComponent(Transform)

    @property
    def activeSelf(self) -> bool:
        """bool: The local active state of this game object."""
        return self._activeSelf

    def SetActive(self, value: bool) -> None:
        """Toggles the active state of the object and triggers lifecycle methods.

        When a game object is deactivated, all of its enabled components will 
        receive an ``OnDisable()`` call. When activated, they receive an 
        ``OnEnable()`` call. If the new state matches the current state, 
        this method does nothing.

        Parameters
        ----------
        value : bool
            The desired active state (``True`` to activate, ``False`` to deactivate).
        """
        if self._activeSelf != value:
            self._activeSelf = value
            for comp in self._components.values():
                if comp.enabled:
                    if self._activeSelf:
                        comp.OnEnable()
                    else:
                        comp.OnDisable()

    @property
    def transform(self) -> 'Transform':
        """Transform: Quick access to the object's spatial transformation data."""
        return self._transform

    def AddComponent(self, component_class: Type[T], *args, **kwargs) -> T:
        """Instantiates and attaches a new component to the game object.

        Components are stored and indexed strictly by their class type (Type), 
        not by string names. This ensures type safety and prevents duplicate 
        components of the same exact class from being added.

        Upon addition, the component's ``Awake()`` method is immediately called. 
        If the object and component are active, ``OnEnable()`` and ``Start()`` 
        are also invoked appropriately.

        Parameters
        ----------
        component_class : Type[T]
            The class (type) of the component to add. Must inherit from :class:`Component`.
        *args
            Positional arguments to pass to the component's constructor.
        **kwargs
            Keyword arguments to pass to the component's constructor.

        Returns
        -------
        T
            The newly created and attached component instance.

        Notes
        -----
        If a component of the specified class already exists on this object, 
        a warning is logged to the console, and the existing instance is returned.
        """
        if component_class in self._components:
            Console.warning(f"Component {component_class.__name__} already exists on {self.name}")
            return self._components[component_class]

        component = component_class(self, *args, **kwargs)
        self._components[component_class] = component

        # Trigger lifecycle events upon creation
        component.Awake()
        if self._activeSelf and component.enabled:
            component.OnEnable()
        if self._started and self._activeSelf and component.enabled:
            component.Start()

        return component

    def GetComponent(self, component_class: Type[T]) -> Optional[T]:
        """Retrieves a component of the specified type if it exists.

        Parameters
        ----------
        component_class : Type[T]
            The class (type) of the component to retrieve.

        Returns
        -------
        Optional[T]
            The component instance if found; otherwise, ``None``.
        """
        return self._components.get(component_class)

    def RemoveComponent(self, component_class: Type[T]) -> bool:
        """Removes a component of the specified type from the game object.

        If the component exists, its ``OnDestroy()`` method is called before 
        it is permanently removed from the internal dictionary.

        Parameters
        ----------
        component_class : Type[T]
            The class (type) of the component to remove.

        Returns
        -------
        bool
            ``True`` if the component was successfully found and removed, 
            ``False`` otherwise.
        """
        if component_class in self._components:
            component = self._components[component_class]
            component.OnDestroy()
            del self._components[component_class]
            return True
        return False

    def Update(self) -> None:
        """Executes the standard frame update routine.

        This method is typically called by the engine's main loop. It ensures 
        that all attached components receive their ``Start()`` call (if not 
        already triggered) and then iterates through all enabled components 
        to call their ``Update()`` methods.
        
        If the game object is inactive (``activeSelf == False``), this method 
        returns immediately without updating components.
        """
        if not self._activeSelf:
            return
            
        if not self._started:
            for comp in self._components.values():
                if comp.enabled:
                    comp.Start()
            self._started = True

        for comp in self._components.values():
            if comp.enabled:
                comp.Update()

    def LateUpdate(self) -> None:
        """Executes the post-update frame routine.

        Called by the engine's main loop after all objects have finished their 
        standard ``Update()``. Iterates through all enabled components and 
        calls their ``LateUpdate()`` methods.
        
        If the game object is inactive (``activeSelf == False``), this method 
        returns immediately.
        """
        if not self._activeSelf:
            return
            
        for comp in self._components.values():
            if comp.enabled:
                comp.LateUpdate()

    def Destroy(self) -> None:
        """Safely destroys the game object and all of its components.

        Iterates through every attached component, invoking its ``OnDestroy()`` 
        method to ensure proper memory cleanup, event unsubscribing, and state 
        resolution before clearing the internal component registry.
        """
        for comp in list(self._components.values()):
            comp.OnDestroy()
        self._components.clear()