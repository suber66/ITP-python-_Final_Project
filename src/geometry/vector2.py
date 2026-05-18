"""
Mathematical representation of 2D vectors and points.

Overview
--------
Provides the :class:`Vector2` class, a fundamental data structure used 
throughout the engine for spatial calculations, positions, velocities, 
and scaling. It supports standard vector arithmetic through operator 
overloading.

A key feature of this specific implementation is its tight integration 
with the engine's event system. A vector can accept an ``on_changed`` 
event, which is automatically invoked whenever its ``x`` or ``y`` 
components are explicitly modified. This reactive pattern is heavily 
utilized by systems like the ``Transform`` component to efficiently 
notify rendering and physics subsystems of spatial updates.

Usage
-----
    >>> from vector2 import Vector2
    >>> v1 = Vector2(10, 5)
    >>> v2 = Vector2(2, 2)
    >>> print(v1 + v2)
    (12.0, 7.0)
    >>> print(v1.magnitude())
    11.180339887498949
"""

import math
import numbers
from typing import Optional, Tuple, Union

from tools.console import Console
from utils.event import Event


class Vector2:
    """A two-dimensional vector for mathematical and spatial operations.

    Supports standard arithmetic operations (addition, subtraction, 
    multiplication, division) with both other vectors and scalar numeric values.

    Parameters
    ----------
    x : numbers.Real, optional
        The initial x-coordinate. Defaults to 0.0.
    y : numbers.Real, optional
        The initial y-coordinate. Defaults to 0.0.
    on_changed : Event, optional
        An event instance to trigger whenever the vector's components are 
        modified. Defaults to a new, empty Event.

    Attributes
    ----------
    x : float
        The vector's coordinate on the X-axis. Setting this property triggers 
        the ``on_changed`` event.
    y : float
        The vector's coordinate on the Y-axis. Setting this property triggers 
        the ``on_changed`` event.
    xy : tuple of float
        A read-only tuple representation of the vector ``(x, y)``.
    """

    def __init__(
        self, 
        x: numbers.Real = 0.0, 
        y: numbers.Real = 0.0, 
        on_changed: Optional[Event] = None
    ) -> None:
        self._x = float(x) if isinstance(x, numbers.Real) else 0.0
        self._y = float(y) if isinstance(y, numbers.Real) else 0.0
        self._on_changed = on_changed if isinstance(on_changed, Event) else Event([])

    # ------------------------------------------------------------------
    # Operator Overloading
    # ------------------------------------------------------------------

    def __add__(self, other: Union['Vector2', numbers.Real]) -> 'Vector2':
        if isinstance(other, Vector2):
            return Vector2(self.x + other.x, self.y + other.y)
        if isinstance(other, numbers.Real):
            return Vector2(self.x + other, self.y + other)
        Console.error("Addition failed: The value can only be a vector or a real number.")
        return NotImplemented

    def __sub__(self, other: Union['Vector2', numbers.Real]) -> 'Vector2':
        if isinstance(other, Vector2):
            return Vector2(self.x - other.x, self.y - other.y)
        if isinstance(other, numbers.Real):
            return Vector2(self.x - other, self.y - other)
        Console.error("Subtraction failed: The value can only be a vector or a real number.")
        return NotImplemented

    def __mul__(self, other: Union['Vector2', numbers.Real]) -> 'Vector2':
        if isinstance(other, Vector2):
            return Vector2(self.x * other.x, self.y * other.y)
        if isinstance(other, numbers.Real):
            return Vector2(self.x * other, self.y * other)
        Console.error("Multiplication failed: The value can only be a vector or a real number.")
        return NotImplemented

    def __truediv__(self, other: Union['Vector2', numbers.Real]) -> 'Vector2':
        if isinstance(other, Vector2):
            return Vector2(
                self.x / other.x if other.x != 0 else float("inf"),
                self.y / other.y if other.y != 0 else float("inf"),
            )
        if isinstance(other, numbers.Real):
            return Vector2(
                self.x / other if other != 0 else float("inf"),
                self.y / other if other != 0 else float("inf"),
            )
        Console.error("Division failed: The value can only be a vector or a real number.")
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Vector2) and self.x == other.x and self.y == other.y

    def __repr__(self) -> str:
        return f"Vector2({self.x}, {self.y})"

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def x(self) -> float:
        return self._x

    @x.setter
    def x(self, value: numbers.Real) -> None:
        if isinstance(value, numbers.Real):
            self._x = float(value)
            if isinstance(self._on_changed, Event):
                self._on_changed.invoke()

    @property
    def y(self) -> float:
        return self._y

    @y.setter
    def y(self, value: numbers.Real) -> None:
        if isinstance(value, numbers.Real):
            self._y = float(value)
            if isinstance(self._on_changed, Event):
                self._on_changed.invoke()

    @property
    def xy(self) -> Tuple[float, float]:
        return (self._x, self._y)

    # ------------------------------------------------------------------
    # Vector Mathematics
    # ------------------------------------------------------------------

    def magnitude(self) -> float:
        """Calculates the magnitude (length) of the vector.

        Returns
        -------
        float
            The Euclidean length of the vector.
        """
        return math.hypot(self.x, self.y)

    def normalize(self) -> 'Vector2':
        """Returns a normalized version of this vector.

        A normalized vector maintains its direction but possesses a magnitude 
        of exactly 1.0. If the vector is a zero vector, it returns a new 
        zero vector to prevent division by zero.

        Returns
        -------
        Vector2
            A new unit vector pointing in the same direction.
        """
        mag = self.magnitude()
        if mag == 0:
            return Vector2(0, 0)
        return self / mag

    def copy(self) -> 'Vector2':
        """Creates an exact duplicate of this vector.

        Returns
        -------
        Vector2
            A new vector instance with identical x and y components. 
            Note that the cloned vector does not inherit the original's 
            ``on_changed`` event bindings.
        """
        return Vector2(self.x, self.y)

    def lerp(self, target: 'Vector2', t: float) -> 'Vector2':
        """Performs linear interpolation between this vector and a target.

        Args
        ----
        target : Vector2
            The destination vector.
        t : float
            The interpolation factor clamped between 0.0 and 1.0. 
            A value of 0.0 returns this vector, 1.0 returns the target, 
            and 0.5 returns the midpoint.

        Returns
        -------
        Vector2
            The newly interpolated vector.
        """
        t = max(0.0, min(1.0, t))  # Clamp t to [0, 1]
        return Vector2(
            self.x + (target.x - self.x) * t,
            self.y + (target.y - self.y) * t
        )

    def distance_to(self, other: 'Vector2') -> float:
        """Calculates the Euclidean distance to another vector/point.

        Args
        ----
        other : Vector2
            The target vector to calculate the distance to.

        Returns
        -------
        float
            The distance between the two points in 2D space.
        """
        return (other - self).magnitude()

    def dot(self, other: 'Vector2') -> float:
        """Calculates the dot product with another vector.

        Args
        ----
        other : Vector2
            The secondary vector for the dot product operation.

        Returns
        -------
        float
            The scalar resulting from the dot product.
        """
        return self.x * other.x + self.y * other.y


# ------------------------------------------------------------------
# Global Vector Constants
# ------------------------------------------------------------------

#: A global constant representing a vector positioned at the origin (0, 0).
zero_vector = Vector2(0, 0)

#: A global constant representing a vector with components (1, 1).
unit_vector = Vector2(1, 1)