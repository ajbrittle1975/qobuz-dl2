"""Lightweight ANSI color constants.

Previously backed by ``colorama``; we emit raw ANSI escape codes instead to
drop the dependency. On Windows 10+ we enable virtual-terminal processing so
the codes render in the classic console too (modern terminals already do).
"""

import os
import sys


def _enable_windows_ansi() -> None:  # pragma: no cover - platform specific
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        for handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            kernel32.SetConsoleMode(kernel32.GetStdHandle(handle), 7)
    except Exception:
        pass


_enable_windows_ansi()

# Disable colors when output is not a TTY (pipes, redirects, CI logs).
_COLOR = sys.stdout.isatty()


def _code(seq: str) -> str:
    return seq if _COLOR else ""


# Styles
DF = _code("\033[22m")  # normal intensity
BG = _code("\033[1m")  # bright/bold
RESET = _code("\033[0m")
OFF = _code("\033[2m")  # dim

# Foreground colors
RED = _code("\033[31m")
BLUE = _code("\033[34m")
GREEN = _code("\033[32m")
YELLOW = _code("\033[33m")
CYAN = _code("\033[36m")
MAGENTA = _code("\033[35m")
