"""
C#-style event and delegate system for the Observer pattern.

Overview
--------
This module provides the :class:`Event` class, which acts as a lightweight 
implementation of the Observer design pattern (similar to C# events or 
UnityEvents). It allows different game systems to declare highly decoupled 
callbacks.

Components and engine subsystems can subscribe to an event and be 
notified automatically when the event is triggered, passing along any 
relevant contextual data through positional and keyword arguments.

Usage
-----
    >>> from event import Event
    >>> on_player_death = Event()
    >>> 
    >>> def play_death_sound(volume: float) -> None:
    ...     print(f"Playing sound at volume {volume}")
    ...
    >>> on_player_death.add_listener(play_death_sound)
    >>> on_player_death.invoke(volume=0.8)
    Playing sound at volume 0.8
"""

from typing import List, Callable, Optional, Any


class Event:
    """An observable event that manages a subscription list of callbacks.

    Provides a safe and predictable mechanism to register, unregister, 
    and dispatch events to multiple listener functions synchronously.

    Parameters
    ----------
    listeners : List[Callable], optional
        An initial list of callback functions to register upon creation. 
        Defaults to an empty list.

    Attributes
    ----------
    _listeners : List[Callable]
        The internal list of currently subscribed callback functions.
    """

    def __init__(self, listeners: Optional[List[Callable]] = None) -> None:
        # We copy the list if provided to prevent unexpected mutations 
        # from external references.
        self._listeners: List[Callable] = [] if listeners is None else listeners.copy()

    def add_listener(self, callback: Callable) -> None:
        """Subscribes a new callback function to the event.

        If the provided callback is already registered, this method 
        silently ignores the request to prevent duplicate invocations 
        during dispatch.

        Parameters
        ----------
        callback : Callable
            The function or method to be executed when the event is invoked.
        """
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable) -> None:
        """Unsubscribes a callback function from the event.

        If the provided callback is not currently registered, this method 
        silently returns without raising an error.

        Parameters
        ----------
        callback : Callable
            The function or method to remove from the subscription list.
        """
        if callback in self._listeners:
            self._listeners.remove(callback)

    def invoke(self, *args: Any, **kwargs: Any) -> None:
        """Triggers the event, synchronously calling all registered listeners.

        All positional and keyword arguments passed to this method are 
        forwarded directly to every subscribed callback function. It is 
        the responsibility of the subscriber to ensure their function 
        signature matches the emitted arguments.

        Parameters
        ----------
        *args : Any
            Positional arguments to pass to the listeners.
        **kwargs : Any
            Keyword arguments to pass to the listeners.
        """
        for listener in self._listeners:
            listener(*args, **kwargs)