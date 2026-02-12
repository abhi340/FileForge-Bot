from pathlib import Path
from PIL import Image, ImageFilter, ExifTags
from app.config import logger


class ImageService:

    @staticmethod
    async def remove_metadata(input_path, output_path):
        with Image.open(input_path) as img:
            clean = Image.new(img.mode, img.size)
            clean.putdata(list(img.getdata()))
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                clean.save(output_path, format=fmt, quality=95)
            else:
                clean.save(output_path, format=fmt, optimize=True)
        logger.info(f"Image metadata removed")
        return output_path

    @staticmethod
    async def resize(input_path, output_path, percentage):
        with Image.open(input_path) as img:
            new_w = max(1, int(img.width * percentage / 100))
            new_h = max(1, int(img.height * percentage / 100))
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                if resized.mode in ("RGBA", "LA", "P"):
                    resized = resized.convert("RGB")
                resized.save(output_path, format=fmt, quality=85)
            else:
                resized.save(output_path, format=fmt, optimize=True)
        logger.info(f"Image resized to {percentage}%")
        return output_path

    @staticmethod
    async def resize_exact(input_path, output_path, width, height):
        with Image.open(input_path) as img:
            resized = img.resize((width, height), Image.LANCZOS)
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                if resized.mode in ("RGBA", "LA", "P"):
                    resized = resized.convert("RGB")
                resized.save(output_path, format=fmt, quality=85)
            else:
                resized.save(output_path, format=fmt, optimize=True)
        logger.info(f"Image resized to {width}x{height}")
        return output_path

    @staticmethod
    async def convert(input_path, output_path, target):
        fmt_map = {"JPG": "JPEG", "JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP", "BMP": "BMP"}
        pil_fmt = fmt_map.get(target.upper(), "PNG")
        with Image.open(input_path) as img:
            if pil_fmt == "JPEG":
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                img.save(output_path, format=pil_fmt, quality=85, optimize=True)
            elif pil_fmt == "PNG":
                img.save(output_path, format=pil_fmt, optimize=True, compress_level=9)
            elif pil_fmt == "WEBP":
                img.save(output_path, format=pil_fmt, quality=85, method=6)
            else:
                img.save(output_path, format=pil_fmt)
        logger.info(f"Image converted to {target}")
        return output_path

    @staticmethod
    async def compress(input_path, output_path, level="medium"):
        quality_map = {
            "low": 30,
            "medium": 55,
            "high": 80,
        }
        quality = quality_map.get(level, 55)

        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(output_path, format="JPEG", quality=quality, optimize=True)

        original_size = input_path.stat().st_size
        new_size = output_path.stat().st_size
        saved = round((1 - new_size / original_size) * 100, 1) if original_size > 0 else 0
        logger.info(f"Image compressed ({level}): saved {saved}%")
        return output_path, original_size, new_size, saved

    @staticmethod
    async def grayscale(input_path, output_path):
        with Image.open(input_path) as img:
            gray = img.convert("L")
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                gray.save(output_path, format=fmt, quality=90, optimize=True)
            else:
                gray.save(output_path, format=fmt, optimize=True)
        logger.info(f"Image converted to grayscale")
        return output_path

    @staticmethod
    async def blur(input_path, output_path, level="medium"):
        radius_map = {
            "light": 5,
            "medium": 15,
            "heavy": 30,
        }
        radius = radius_map.get(level, 15)

        with Image.open(input_path) as img:
            blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                if blurred.mode in ("RGBA", "LA", "P"):
                    blurred = blurred.convert("RGB")
                blurred.save(output_path, format=fmt, quality=90, optimize=True)
            else:
                blurred.save(output_path, format=fmt, optimize=True)
        logger.info(f"Image blurred ({level})")
        return output_path

    @staticmethod
    async def upscale(input_path, output_path, factor=2):
        with Image.open(input_path) as img:
            new_w = img.width * factor
            new_h = img.height * factor
            upscaled = img.resize((new_w, new_h), Image.LANCZOS)
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                if upscaled.mode in ("RGBA", "LA", "P"):
                    upscaled = upscaled.convert("RGB")
                upscaled.save(output_path, format=fmt, quality=95, optimize=True)
            else:
                upscaled.save(output_path, format=fmt, optimize=True)
        logger.info(f"Image upscaled {factor}x to {new_w}x{new_h}")
        return output_path

    @staticmethod
    async def to_pdf(input_path, output_path):
        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(output_path, format="PDF", resolution=100.0)
        logger.info(f"Image converted to PDF")
        return output_path

    @staticmethod
    async def get_info(input_path):
        with Image.open(input_path) as img:
            info = {
                "format": img.format or "Unknown",
                "mode": img.mode,
                "width": img.width,
                "height": img.height,
                "megapixels": round((img.width * img.height) / 1_000_000, 2),
                "size_bytes": input_path.stat().st_size,
            }

            # Check for EXIF
            exif_count = 0
            has_gps = False
            camera = "Unknown"
            try:
                exif = img._getexif()
                if exif:
                    exif_count = len(exif)
                    for tag_id, value in exif.items():
                        tag = ExifTags.TAGS.get(tag_id, "")
                        if tag == "GPSInfo":
                            has_gps = True
                        if tag == "Model":
                            camera = str(value)[:50]
            except Exception:
                pass

            info["exif_fields"] = exif_count
            info["has_gps"] = has_gps
            info["camera"] = camera

            # DPI
            try:
                dpi = img.info.get("dpi", (0, 0))
                info["dpi"] = f"{int(dpi[0])}x{int(dpi[1])}"
            except Exception:
                info["dpi"] = "Unknown"

            return info

    @staticmethod
    async def clean_screenshot(input_path, output_path):
        with Image.open(input_path) as img:
            # Remove top ~6% (status bar area)
            crop_top = int(img.height * 0.06)
            # Remove bottom ~4% (navigation bar)
            crop_bottom = int(img.height * 0.04)
            cropped = img.crop((0, crop_top, img.width, img.height - crop_bottom))

            # Remove metadata
            clean = Image.new(cropped.mode, cropped.size)
            clean.putdata(list(cropped.getdata()))

            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                if clean.mode in ("RGBA", "LA", "P"):
                    clean = clean.convert("RGB")
                clean.save(output_path, format=fmt, quality=90, optimize=True)
            else:
                clean.save(output_path, format=fmt, optimize=True)
        logger.info(f"Screenshot cleaned")
        return output_path

    @staticmethod
    async def id_photo(input_path, output_path, size_type="passport"):
        sizes = {
            "passport": (413, 531),       # 35x45mm at 300dpi
            "visa": (600, 600),            # 2x2 inch at 300dpi
            "stamp": (118, 148),           # 1x1.25 inch at 118dpi
        }
        target_w, target_h = sizes.get(size_type, (413, 531))

        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")

            # Calculate crop to match aspect ratio
            target_ratio = target_w / target_h
            img_ratio = img.width / img.height

            if img_ratio > target_ratio:
                new_w = int(img.height * target_ratio)
                left = (img.width - new_w) // 2
                img = img.crop((left, 0, left + new_w, img.height))
            else:
                new_h = int(img.width / target_ratio)
                top = (img.height - new_h) // 2
                img = img.crop((0, top, img.width, top + new_h))

            # Resize to target
            img = img.resize((target_w, target_h), Image.LANCZOS)

            # Add white border (10px)
            bordered = Image.new("RGB", (target_w + 20, target_h + 20), (255, 255, 255))
            bordered.paste(img, (10, 10))

            bordered.save(output_path, format="JPEG", quality=95, optimize=True)

        logger.info(f"ID photo created ({size_type})")
        return output_path
