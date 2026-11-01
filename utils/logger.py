import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger("pet_finder_bot")


def configure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, handlers=[handler, logging.StreamHandler()], force=True,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
