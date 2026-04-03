"""
Logging utility for Candi.

Log files are written to:
    backend/Logs/<YYYY>/<MonthName>/candi_<YYYY-MM-DD>.log

Both a file handler (DEBUG+) and a console handler (INFO+) are attached.
Call get_logger(__name__) at the top of any module to get a named logger.
"""
import logging
import os
from datetime import datetime
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger that writes to the date-structured log directory.

    Calling this multiple times with the same name is safe — handlers are
    only attached once.
    """
    logger = logging.getLogger(name)

    # Already configured — return as-is
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ------------------------------------------------------------------ #
    # Build path:  backend/Logs/2026/April/candi_2026-04-03.log           #
    # ------------------------------------------------------------------ #
    now = datetime.now()
    year  = now.strftime("%Y")          # e.g. 2026
    month = now.strftime("%B")          # e.g. April
    date  = now.strftime("%Y-%m-%d")    # e.g. 2026-04-03

    # This file lives at  backend/app/utils/logger.py
    # parents[0] = utils/   parents[1] = app/   parents[2] = backend/
    backend_root = Path(__file__).resolve().parents[2]
    log_dir = backend_root / "Logs" / year / month
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"candi_{date}.log"

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — DEBUG and above
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler — INFO and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Don't propagate to the root logger (avoids duplicate console output)
    logger.propagate = False

    return logger
