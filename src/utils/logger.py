"""Lightweight application logging utility."""
import logging
import sys
from ..config.settings import settings


def setup_logger(name: str = "pet_animal", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a logger instance writing to console and optional log file."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    try:
        settings.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(settings.LOG_FILE), encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # If file logging cannot be initialized, console logging is still active
        pass

    return logger


def get_logger(name: str = "pet_animal") -> logging.Logger:
    """Gets an existing logger or sets up the default one."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
