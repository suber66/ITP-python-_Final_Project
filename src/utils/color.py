"""
Mathematical representation of RGBA colors.

Overview
--------
Provides the :class:`Color` class, which encapsulates standard Red, Green, 
Blue, and Alpha (transparency) color channels. It automatically handles 
clamping of values to the valid 8-bit range (0-255) and provides safe 
property accessors to prevent invalid data states.

This class is utilized throughout the engine's rendering and UI systems 
to maintain consistent and safe color manipulation.

Usage
-----
    >>> from color import Color
    >>> c = Color(255, 100, 50)
    >>> print(c.rgb)
    (255, 100, 50)
    >>> c.r = 300  # Will be automatically clamped to 255
    >>> print(c.r)
    255
"""

from numbers import Real
from typing import Optional, Tuple

from tools import Console


class Color:
    """A representation of an RGBA color.

    All color channels (Red, Green, Blue, Alpha) are constrained to integer 
    values between 0 and 255. If floating-point numbers are provided, they 
    are securely cast to integers. Invalid types trigger an error via the console.

    Parameters
    ----------
    r : numbers.Real, optional
        The red component (0-255). Defaults to 0.
    g : numbers.Real, optional
        The green component (0-255). Defaults to 0.
    b : numbers.Real, optional
        The blue component (0-255). Defaults to 0.
    a : numbers.Real, optional
        The alpha (transparency) component (0-255). Defaults to 255.

    Attributes
    ----------
    r : int
        The red color channel.
    g : int
        The green color channel.
    b : int
        The blue color channel.
    a : int
        The alpha color channel.
    rgb : tuple of int
        A read-only tuple representing the (r, g, b) values.
    rgba : tuple of int
        A read-only tuple representing the (r, g, b, a) values.
    """

    __r_default = 0
    __g_default = 0
    __b_default = 0
    __a_default = 255

    def __init__(
        self,
        r: Optional[Real] = None,
        g: Optional[Real] = None,
        b: Optional[Real] = None,
        a: Optional[Real] = None
    ) -> None:
        self._r: int = self._clamp((int(r) if not isinstance(r, int) else r) if isinstance(r, Real) else Color.__r_default)
        self._g: int = self._clamp((int(g) if not isinstance(g, int) else g) if isinstance(g, Real) else Color.__g_default)
        self._b: int = self._clamp((int(b) if not isinstance(b, int) else b) if isinstance(b, Real) else Color.__b_default)
        self._a: int = self._clamp((int(a) if not isinstance(a, int) else a) if isinstance(a, Real) else Color.__a_default)

    @staticmethod
    def _clamp(value: int, min_val: int = 0, max_val: int = 255) -> int:
        """Clamps a numeric value strictly within a specified range.

        Parameters
        ----------
        value : int
            The input value to clamp.
        min_val : int, optional
            The minimum allowable value. Defaults to 0.
        max_val : int, optional
            The maximum allowable value. Defaults to 255.

        Returns
        -------
        int
            The constrained integer value.
        """
        return max(min_val, min(max_val, value))

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def r(self) -> int:
        return self._r
        
    @property
    def g(self) -> int:
        return self._g
        
    @property
    def b(self) -> int:
        return self._b
        
    @property
    def a(self) -> int:
        return self._a
    
    @property
    def rgb(self) -> Tuple[int, int, int]:
        """tuple of int: Returns the RGB components as a tuple."""
        return self._r, self._g, self._b
        
    @property
    def rgba(self) -> Tuple[int, int, int, int]:
        """tuple of int: Returns all RGBA components as a tuple."""
        return self._r, self._g, self._b, self._a
    
    @r.setter
    def r(self, value: Real) -> None:
        if isinstance(value, Real):
            self._r = self._clamp(int(value) if not isinstance(value, int) else value)
        else:
            Console.error("Invalid color value for red component.")

    @g.setter
    def g(self, value: Real) -> None:
        if isinstance(value, Real):
            self._g = self._clamp(int(value) if not isinstance(value, int) else value)
        else:
            Console.error("Invalid color value for green component.")

    @b.setter
    def b(self, value: Real) -> None:
        if isinstance(value, Real):
            self._b = self._clamp(int(value) if not isinstance(value, int) else value)
        else:
            Console.error("Invalid color value for blue component.")

    @a.setter
    def a(self, value: Real) -> None:
        if isinstance(value, Real):
            self._a = self._clamp(int(value) if not isinstance(value, int) else value)
        else:
            Console.error("Invalid color value for alpha component.")

    # ------------------------------------------------------------------
    # Magic Methods
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"Color(r={self._r}, g={self._g}, b={self._b}, a={self._a})"

    def __repr__(self) -> str:
        return f"Color({self._r}, {self._g}, {self._b}, {self._a})"