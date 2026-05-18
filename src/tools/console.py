"""
Utilities for formatted terminal output and debug logging.

Overview
--------
This module provides tools for interacting with the terminal console.
The main :class:`Console` class ensures a centralized way to output
informational messages, warnings, and errors. It displays a full,
colorized call stack hierarchy — similar to Python's native tracebacks —
so you can immediately see every step that led to an error.

The auxiliary :class:`Color` class provides convenient abstractions over
ANSI escape codes for text colorization and styling.

Usage
-----
    >>> from tools.console import Console
    >>> Console.log("Game initialized successfully.")
    [2026-05-13 12:00:00] INFO : Game initialized successfully.

    >>> Console.error("Failed to load texture!")
    Traceback (most recent call last):
    
      File "main.py", line 42, in <module>
        game.run()
    
      File "engine/game.py", line 87, in run
        self.update()
    
      File "engine/game.py", line 104, in update
        self.renderer.draw(scene)
    
    Failed to load texture!
"""

import sys
import os
import inspect
import time
from typing import Optional, Union, List


class Color:
    """ANSI escape code constants for terminal text styling."""

    class Style:
        RESET:          str = '\033[0m'
        BOLD:           str = '\033[1m'
        DIM:            str = '\033[2m'
        ITALIC:         str = '\033[3m'
        UNDERLINE:      str = '\033[4m'
        BLINK:          str = '\033[5m'
        INVERSE:        str = '\033[7m'
        HIDDEN:         str = '\033[8m'
        STRIKETHROUGH:  str = '\033[9m'

    class Fore:
        BLACK:          str = '\033[30m'
        RED:            str = '\033[31m'
        GREEN:          str = '\033[32m'
        YELLOW:         str = '\033[33m'
        BLUE:           str = '\033[34m'
        MAGENTA:        str = '\033[35m'
        CYAN:           str = '\033[36m'
        WHITE:          str = '\033[37m'
        BRIGHT_BLACK:   str = '\033[90m'
        BRIGHT_RED:     str = '\033[91m'
        BRIGHT_GREEN:   str = '\033[92m'
        BRIGHT_YELLOW:  str = '\033[93m'
        BRIGHT_BLUE:    str = '\033[94m'
        BRIGHT_MAGENTA: str = '\033[95m'
        BRIGHT_CYAN:    str = '\033[96m'
        BRIGHT_WHITE:   str = '\033[97m'

    class Back:
        BLACK:          str = '\033[40m'
        RED:            str = '\033[41m'
        GREEN:          str = '\033[42m'
        YELLOW:         str = '\033[43m'
        BLUE:           str = '\033[44m'
        MAGENTA:        str = '\033[45m'
        CYAN:           str = '\033[46m'
        WHITE:          str = '\033[47m'
        BRIGHT_BLACK:   str = '\033[100m'
        BRIGHT_RED:     str = '\033[101m'
        BRIGHT_GREEN:   str = '\033[102m'
        BRIGHT_YELLOW:  str = '\033[103m'
        BRIGHT_BLUE:    str = '\033[104m'
        BRIGHT_MAGENTA: str = '\033[105m'
        BRIGHT_CYAN:    str = '\033[106m'
        BRIGHT_WHITE:   str = '\033[107m'

    @staticmethod
    def reset_if(condition: str) -> str:
        """Returns the style reset code if the condition is truthy."""
        return Color.Style.RESET if condition else ''


class CallerInfo:
    """Container for a single frame in the call stack.

    Parameters
    ----------
    filename : str
        The source file path.
    lineno : int
        The line number within the file.
    function : str
        The name of the function or method at this frame.
    code_context : list of str, str, or None
        The source code line(s) at this location.
    """
    def __init__(
        self,
        filename: str,
        lineno: int,
        function: str,
        code_context: Union[List[str], str, None]
    ) -> None:
        self.filename = filename
        self.lineno = lineno
        self.function = function
        self.code_context = code_context

    def __repr__(self) -> str:
        return (
            f"CallerInfo(filename={self.filename!r}, lineno={self.lineno}, "
            f"function={self.function!r}, code_context={self.code_context!r})"
        )


# Internal module names to exclude from the displayed stack.
# These are Console's own frames — not useful for the user.
_INTERNAL_MODULES = frozenset({
    __name__,           # "console" or "tools.console"
    "console",
    "tools.console",
})


class Console:
    """Static class for advanced application logging and debugging.

    Provides methods for outputting standard logs, warnings, and errors.
    Errors and warnings display a full, colorized call stack hierarchy —
    similar to Python's native traceback format — so every step that led
    to the message is immediately visible.

    Stack filtering
    ---------------
    Internal Console frames are stripped automatically. The remaining frames
    are shown from the outermost caller down to the direct trigger of the
    log call (most-recent-call-last order, matching Python convention).
    """

    # ------------------------------------------------------------------ #
    # Configuration                                                        #
    # ------------------------------------------------------------------ #

    #: Maximum number of stack frames to display (0 = unlimited).
    MAX_FRAMES: int = 0

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def log(message: str) -> None:
        """Outputs a standard informational message with a timestamp.

        Displayed in white without a stack trace, to keep output clean
        for routine game-loop messages.

        Parameters
        ----------
        message : str
            The informational text to output.
        """
        ts = Console._get_formatted_time()
        print(
            f"{Color.Fore.BRIGHT_BLACK}[{ts}]{Color.Style.RESET} "
            f"{Color.Fore.WHITE}INFO :{Color.Style.RESET} {message}",
            flush=True,
        )

    @staticmethod
    def error(
        message: str,
        custom_info: bool = False,
        caller_info: Optional[List[CallerInfo]] = None,
    ) -> None:
        """Outputs a critical error message with a full colorized call stack.

        Parameters
        ----------
        message : str
            The error description.
        custom_info : bool, optional
            If ``True``, uses the explicitly provided ``caller_info`` list
            instead of inspecting the live call stack. Defaults to ``False``.
        caller_info : list of CallerInfo, optional
            Custom stack frames, required when ``custom_info`` is ``True``.
        """
        frames = caller_info if custom_info else Console._collect_frames()
        Console._print_traceback(
            message=message,
            level="ERROR",
            accent=Color.Fore.BRIGHT_RED,
            header_bg=Color.Back.RED,
            frames=frames,
        )

    @staticmethod
    def warning(
        message: str,
        custom_info: bool = False,
        caller_info: Optional[List[CallerInfo]] = None,
    ) -> None:
        """Outputs a warning message with a full colorized call stack.

        Intended for non-critical issues such as missing optional files,
        deprecated function calls, or duplicate components.

        Parameters
        ----------
        message : str
            The warning description.
        custom_info : bool, optional
            If ``True``, uses the explicitly provided ``caller_info`` list.
            Defaults to ``False``.
        caller_info : list of CallerInfo, optional
            Custom stack frames, required when ``custom_info`` is ``True``.
        """
        frames = caller_info if custom_info else Console._collect_frames()
        Console._print_traceback(
            message=message,
            level="WARNING",
            accent=Color.Fore.BRIGHT_YELLOW,
            header_bg=Color.Back.YELLOW,
            frames=frames,
        )

    @staticmethod
    def clear() -> None:
        """Clears the terminal screen.

        Automatically detects the operating system and invokes the
        appropriate system command (``cls`` on Windows, ``clear`` on POSIX).
        """
        os.system("cls" if sys.platform == "win32" else "clear")

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_formatted_time() -> str:
        """Returns the current local time as 'YYYY-MM-DD HH:MM:SS'."""
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    @staticmethod
    def _collect_frames() -> List[CallerInfo]:
        """Inspects the live call stack and returns relevant frames.

        Internal Console frames are filtered out. The result is ordered
        from outermost caller to innermost (most-recent-call-last), which
        mirrors Python's standard traceback convention.

        Returns
        -------
        list of CallerInfo
            Filtered and ordered stack frames.
        """
        raw_stack = inspect.stack()

        frames: List[CallerInfo] = []
        for frame_info in raw_stack:
            # Determine the module name for this frame
            module = frame_info.frame.f_globals.get("__name__", "")
            short_file = os.path.basename(frame_info.filename)

            # Skip our own internals
            if module in _INTERNAL_MODULES:
                continue
            if short_file in ("console.py",):
                continue

            code = ""
            if frame_info.code_context:
                code = frame_info.code_context[0].strip()

            frames.append(CallerInfo(
                filename=frame_info.filename,
                lineno=frame_info.lineno,
                function=frame_info.function,
                code_context=code,
            ))

        # inspect.stack() is innermost-first; reverse to outermost-first
        frames.reverse()

        # Optional cap on frame count (keep the innermost N)
        if Console.MAX_FRAMES > 0:
            frames = frames[-Console.MAX_FRAMES:]

        return frames

    @staticmethod
    def _shorten_path(path: str) -> str:
        """Converts an absolute path to a project-relative one if possible.

        Falls back to the full path when the file is outside the CWD.

        Parameters
        ----------
        path : str
            The absolute file path.

        Returns
        -------
        str
            The relative path string, or the original ``path`` if it cannot
            be made relative to the current working directory.
        """
        try:
            return os.path.relpath(path)
        except ValueError:
            # relpath() raises ValueError on Windows when path is on a
            # different drive from cwd.
            return path

    @staticmethod
    def _print_traceback(
        message: str,
        level: str,
        accent: str,
        header_bg: str,
        frames: List[CallerInfo],
    ) -> None:
        """Renders a full traceback block to stdout.

        Layout (mirrors Python's traceback style)::

            ERROR: Failed to load texture!
            Traceback (most recent call last):

              File "main.py", line 42, in <module>
                game.run()

              File "engine/game.py", line 87, in run
                self.update()

        Parameters
        ----------
        message : str
            The final error/warning message shown at the bottom.
        level : str
            Label shown in the header (e.g. ``"ERROR"``).
        accent : str
            ANSI color code used for the level label and message text.
        header_bg : str
            Unused, kept for API compatibility.
        frames : list of CallerInfo
            Ordered stack frames (outermost first).
        """
        R = Color.Style.RESET
        BRIGHT_RED = Color.Fore.BRIGHT_RED
        CYAN = Color.Fore.CYAN
        GREY = Color.Fore.BRIGHT_BLACK
        WHITE = Color.Fore.WHITE

        lines: List[str] = []

        # ── header: "ERROR: message" ─────────────────────────────────────
        lines.append(f"{accent}{level}: {message}{R}")

        # ── "Traceback" sub-header ───────────────────────────────────────
        lines.append(f"{BRIGHT_RED}Traceback (most recent call last):{R}")

        if not frames:
            lines.append(f"  {GREY}<no frames available>{R}")
        else:
            for frame in frames:
                short = Console._shorten_path(frame.filename)
                lines.append("")

                # Location line  →  File "path", line N, in func
                lines.append(
                    f"{BRIGHT_RED}  File {R}"
                    f"{CYAN}\"{short}\"{R}"
                    f"{BRIGHT_RED}, line {R}"
                    f"{frame.lineno}{R}"
                    f"{BRIGHT_RED}, in {R}"
                    f"{WHITE}{frame.function}{R}"
                )

                # Source line  →  indented code snippet
                if frame.code_context:
                    lines.append(f"    {frame.code_context}{R}")

        lines.append("")
        print("\n".join(lines), flush=True)