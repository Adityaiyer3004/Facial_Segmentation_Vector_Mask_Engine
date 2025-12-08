from __future__ import annotations

from rich.console import Console
from rich.logging import RichHandler
import logging

console = Console()


def setup_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console, markup=True)],
    )
    return logging.getLogger("qoves")


logger = setup_logging()
