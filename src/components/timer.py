"""
GameTimer — MonoBehavior component that tracks elapsed game time.

Overview
--------
This module provides the :class:`Timer` component, a lightweight stopwatch
built on top of ``time.time()`` and designed to be attached to any
:class:`~core.gameObject.GameObject` via ``AddComponent``.  It exposes a
simple start / stop / reset API and a human-readable formatter, making it
suitable for in-game countdowns, speed-run timers, and performance
instrumentation alike.

Responsibilities
----------------
* **Time tracking** — records the wall-clock instant at which the timer is
  started and derives :attr:`~Timer.elapsed` on demand, so no per-frame
  accumulation is required.
* **State management** — maintains a ``_running`` flag to distinguish the
  *active* and *paused* states and prevents erroneous reads when the timer
  has not yet been started.
* **Formatting** — converts a raw float (seconds) into a human-readable
  ``'MM:SS.mm'`` string via :meth:`~Timer.format`, usable directly by UI
  label components.

Elapsed time
------------
:attr:`~Timer.elapsed` is computed dynamically from ``time.time()`` while
the timer is running, so its value is always current without requiring an
``Update`` call.  When the timer is stopped, the value captured at the
moment :meth:`~Timer.stop` was called is returned instead, preserving the
final reading until :meth:`~Timer.reset` clears it.

Usage
-----
    >>> timer_obj = GameObject('Timer')
    >>> timer = timer_obj.AddComponent(GameTimer)

    >>> timer.start()
    >>> ...
    >>> elapsed = timer.elapsed        # live float seconds while running
    >>> print(timer.format())          # '00:03.47'

    >>> final = timer.stop()           # stops and returns total seconds
    >>> timer.reset()                  # clears state for reuse
"""

import time
from core.monoBehavior import MonoBehavior
from core.gameObject import GameObject


class Timer(MonoBehavior):
    """Wall-clock stopwatch component attached to a :class:`~core.gameObject.GameObject`.

    :class:`Timer` measures elapsed real-world time between :meth:`start`
    and :meth:`stop` calls.  It does not hook into the game loop's ``Update``
    cycle; instead :attr:`elapsed` is derived on-the-fly from
    ``time.time()``, which means reads are always accurate to the current
    instant without any per-frame bookkeeping.

    .. note::
        Calling :meth:`start` on an already-running timer resets the
        internal start timestamp, discarding any time accumulated in the
        current session.  Call :meth:`stop` first if you need to preserve
        the intermediate reading.

    Parameters
    ----------
    game_object : GameObject
        The owner :class:`~core.gameObject.GameObject`, supplied automatically
        by the component system.

    Attributes
    ----------
    _start_time : float
        ``time.time()`` value recorded at the most recent :meth:`start` call.
        Meaningless while :attr:`running` is ``False``.
    _elapsed : float
        Seconds captured at the moment the timer was last stopped.  Returned
        by :attr:`elapsed` when the timer is not running.
    _running : bool
        ``True`` between a :meth:`start` and a subsequent :meth:`stop` or
        :meth:`reset` call.
    """

    def __init__(self, game_object: GameObject) -> None:
        super().__init__(game_object)
        self._start_time: float = 0.0
        self._elapsed:    float = 0.0
        self._running:    bool  = False

    # ---------------------------------------------------------------- #
    #  Properties                                                        #
    # ---------------------------------------------------------------- #

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since the timer was started.

        While the timer is running, the value is computed live from
        ``time.time()`` and increases on every access.  When the timer is
        stopped, the value captured at the moment :meth:`stop` was called
        is returned unchanged until :meth:`reset` clears it.

        Returns
        -------
        float
            Elapsed seconds, or ``0.0`` if the timer has never been started.

        :type: float
        """
        if self._running:
            return time.time() - self._start_time
        return self._elapsed

    @property
    def running(self) -> bool:
        """Whether the timer is currently counting.

        ``True`` between a :meth:`start` and a subsequent :meth:`stop` or
        :meth:`reset` call; ``False`` otherwise.

        :type: bool
        """
        return self._running

    # ---------------------------------------------------------------- #
    #  Control methods                                                   #
    # ---------------------------------------------------------------- #

    def start(self) -> None:
        """Begin (or restart) the timer.

        Records the current ``time.time()`` as the new start instant and
        sets :attr:`running` to ``True``.

        .. warning::
            If the timer is already running, the previous start instant is
            overwritten without saving the accumulated time.  Call
            :meth:`stop` beforehand to preserve the current reading.
        """
        self._start_time = time.time()
        self._running    = True

    def stop(self) -> float:
        """Stop the timer and return the total elapsed seconds.

        Captures the current elapsed time into ``_elapsed`` and sets
        :attr:`running` to ``False``.  If the timer is already stopped,
        the previously captured value is returned without modification.

        Returns
        -------
        float
            Total seconds elapsed between the most recent :meth:`start` call
            and this call, or the value from the previous :meth:`stop` if
            the timer was not running.
        """
        if self._running:
            self._elapsed = time.time() - self._start_time
            self._running = False
        return self._elapsed

    def reset(self) -> None:
        """Clear all state and return the timer to its initial condition.

        Sets :attr:`elapsed` to ``0.0`` and :attr:`running` to ``False``.
        Does not raise an error if called while the timer is running;
        the running session is simply discarded.
        """
        self._elapsed = 0.0
        self._running = False

    # ---------------------------------------------------------------- #
    #  Formatting                                                        #
    # ---------------------------------------------------------------- #

    def format(self, elapsed: float = None) -> str:
        """Format a duration as a ``'MM:SS.mm'`` string.

        Converts *elapsed* (or the current :attr:`elapsed` value when no
        argument is supplied) into a fixed-width string suitable for display
        in a UI label.  The centisecond field (``mm``) represents hundredths
        of a second, giving two digits of sub-second precision.

        Parameters
        ----------
        elapsed : float, optional
            The duration in seconds to format.  When ``None``, the value
            of :attr:`elapsed` is used, which reflects the live reading
            while the timer is running or the captured reading after it has
            been stopped.  Defaults to ``None``.

        Returns
        -------
        str
            A zero-padded string in the form ``'MM:SS.mm'``, for example
            ``'01:07.09'`` for 67.09 seconds.

        Examples
        --------
        >>> timer.format(67.09)
        '01:07.09'
        >>> timer.format(0.0)
        '00:00.00'
        """
        t       = elapsed if elapsed is not None else self.elapsed
        minutes = int(t) // 60
        seconds = int(t) % 60
        millis  = int((t - int(t)) * 100)
        return f'{minutes:02d}:{seconds:02d}.{millis:02d}'