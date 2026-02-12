import uuid
import time
import shutil
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.types import Document, FSInputFile

from app.config import logger


class FileManager:
    def __init__(self, temp_dir="tmp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def temp_path(self, extension=""):
        return self.temp_dir / f"{uuid.uuid4().hex}{extension}"

    async def download(self, bot, document):
        ext = ""
        if document.file_name:
            ext = Path(document.file_name).suffix
        path = self.temp_path(ext)
        tg_file = await bot.get_file(document.file_id)
        await bot.download_file(tg_file.file_path, destination=str(path))
        logger.info(f"Downloaded: {path.name}")
        return path

    def cleanup(self, *paths):
        for p in paths:
            try:
                if p and Path(p).exists():
                    if Path(p).is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        Path(p).unlink()
            except Exception as e:
                logger.warning(f"Cleanup failed {p}: {e}")

    def cleanup_all(self):
        if not self.temp_dir.exists():
            return 0
        count = 0
        for item in self.temp_dir.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink()
                count += 1
            except Exception as e:
                logger.warning(f"Cleanup failed {item}: {e}")
        return count

    @staticmethod
    def input_file(path, filename=None):
        return FSInputFile(path=str(path), filename=filename)


class Timer:
    def __init__(self):
        self.start_time = 0
        self.elapsed_ms = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = int((time.perf_counter() - self.start_time) * 1000)


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


SUPPORTED_TYPES = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/bmp": "image",
    "image/tiff": "image",
    "image/gif": "image",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def detect_category(mime_type):
    if not mime_type:
        return None
    return SUPPORTED_TYPES.get(mime_type)
