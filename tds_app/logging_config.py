"""
Central Rich‑powered logging configuration.
Call `setup_logging()` once at program start (CLI does this).
"""

import logging

from rich.console import Console
from rich.logging import RichHandler

# Colours render only when output is a TTY.
_rich_handler = RichHandler(
    console=Console(width=120),
    markup=True,
    show_time=True,
    show_level=True,
    show_path=False,
)

_LOG_FORMAT = "%(message)s"  # RichHandler already prints time/level


def setup_logging(level: str | int = "INFO") -> None:
    """Configure root logger with a Rich handler."""
    logging.basicConfig(
        handlers=[_rich_handler],
        level=level,
        format=_LOG_FORMAT,
        datefmt="[%X]",
        force=True,  # override previous basicConfig calls
    )

    # Suppress noisy libraries if desired
    logging.getLogger("openai").setLevel(logging.WARNING)
