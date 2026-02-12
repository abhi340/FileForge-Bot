"""
Configuration and logging.
All secrets from environment variables only.
"""

import os
import sys
import logging
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def setup_logger() -> logging.Logger:
    _logger = logging.getLogger("filebot")
    if _logger.handlers:
        return _logger
    _logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    return _logger


logger = setup_logger()


@dataclass(frozen=True)
class BotConfig:
    token: str = field(repr=False)
    admin_id: int = 0
    database_path: str = "data/bot.db"
    max_file_size_mb: int = 20
    temp_dir: str = "tmp"
    port: int = 10000
    max_concurrent: int = 2

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def load_config() -> BotConfig:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logger.critical("BOT_TOKEN is required")
        sys.exit(1)

    admin_id_str = os.getenv("ADMIN_ID", "0").strip()
    if not admin_id_str.isdigit() or int(admin_id_str) == 0:
        logger.critical("ADMIN_ID must be a valid numeric ID")
        sys.exit(1)

    config = BotConfig(
        token=token,
        admin_id=int(admin_id_str),
        database_path=os.getenv("DATABASE_PATH", "data/bot.db").strip(),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20").strip()),
        temp_dir=os.getenv("TEMP_DIR", "tmp").strip(),
        port=int(os.getenv("PORT", "10000").strip()),
    )

    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.temp_dir).mkdir(parents=True, exist_ok=True)

    logger.info(f"Config loaded — Admin: {config.admin_id}, Max size: {config.max_file_size_mb}MB")
    return config
