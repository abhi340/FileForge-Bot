"""
Image processing — metadata removal, resize, format conversion.
"""

from pathlib import Path
from PIL import Image

from app.config import logger


class ImageService:

    @staticmethod
    async def remove_metadata(input_path: Path, output_path: Path) -> Path:
        with Image.open(input_path) as img:
            clean = Image.new(img.mode, img.size)
            clean.putdata(list(img.getdata()))

            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                clean.save(output_path, format=fmt, quality=95)
            else:
                clean.save(output_path, format=fmt)

        logger.info(f"Image metadata removed: {output_path.name}")
        return output_path

    @staticmethod
    async def resize(input_path: Path, output_path: Path, percentage: int) -> Path:
        with Image.open(input_path) as img:
            new_w = max(1, int(img.width * percentage / 100))
            new_h = max(1, int(img.height * percentage / 100))
            resized = img.resize((new_w, new_h), Image.LANCZOS)

            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG" and resized.mode in ("RGBA", "LA", "P"):
                resized = resized.convert("RGB")
            resized.save(output_path, format=fmt)

        logger.info(f"Image resized to {percentage}%: {new_w}x{new_h}")
        return output_path

    @staticmethod
    async def convert(input_path: Path, output_path: Path, target: str) -> Path:
        fmt_map = {"JPG": "JPEG", "JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP", "BMP": "BMP"}
        pil_fmt = fmt_map.get(target.upper(), "PNG")

        with Image.open(input_path) as img:
            if pil_fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(output_path, format=pil_fmt)

        logger.info(f"Image converted to {target}")
        return output_path
