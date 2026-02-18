import pytesseract
from pathlib import Path
from PIL import Image, ImageFilter, ExifTags
from app.config import logger

class ImageService:
    @staticmethod
    async def extract_text_ocr(input_path):
        """Perform OCR on image to extract text."""
        with Image.open(input_path) as img:
            # Pre-process for better OCR (grayscale + sharpen)
            img = img.convert('L').filter(ImageFilter.SHARPEN)
            text = pytesseract.image_to_string(img)
        
        logger.info("OCR completed")
        return text.strip() if text.strip() else "No text detected in image."

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
        return output_path

    @staticmethod
    async def resize(input_path, output_path, percentage):
        with Image.open(input_path) as img:
            new_w = max(1, int(img.width * percentage / 100))
            new_h = max(1, int(img.height * percentage / 100))
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                if resized.mode in ("RGBA", "LA", "P"): resized = resized.convert("RGB")
                resized.save(output_path, format=fmt, quality=85)
            else:
                resized.save(output_path, format=fmt, optimize=True)
        return output_path

    @staticmethod
    async def resize_exact(input_path, output_path, width, height):
        with Image.open(input_path) as img:
            resized = img.resize((width, height), Image.LANCZOS)
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG":
                if resized.mode in ("RGBA", "LA", "P"): resized = resized.convert("RGB")
                resized.save(output_path, format=fmt, quality=85)
            else:
                resized.save(output_path, format=fmt, optimize=True)
        return output_path

    @staticmethod
    async def convert(input_path, output_path, target):
        fmt_map = {"JPG": "JPEG", "JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP", "BMP": "BMP"}
        pil_fmt = fmt_map.get(target.upper(), "PNG")
        with Image.open(input_path) as img:
            if pil_fmt == "JPEG":
                if img.mode in ("RGBA", "LA", "P"): img = img.convert("RGB")
                img.save(output_path, format=pil_fmt, quality=85, optimize=True)
            elif pil_fmt == "PNG":
                img.save(output_path, format=pil_fmt, optimize=True, compress_level=9)
            elif pil_fmt == "WEBP":
                img.save(output_path, format=pil_fmt, quality=85, method=6)
            else:
                img.save(output_path, format=pil_fmt)
        return output_path

    @staticmethod
    async def compress(input_path, output_path, level="medium"):
        q = {"low": 30, "medium": 55, "high": 80}.get(level, 55)
        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "LA", "P"): img = img.convert("RGB")
            img.save(output_path, format="JPEG", quality=q, optimize=True)
        orig = input_path.stat().st_size
        new = output_path.stat().st_size
        saved = round((1 - new / orig) * 100, 1) if orig > 0 else 0
        return output_path, orig, new, saved

    @staticmethod
    async def grayscale(input_path, output_path):
        with Image.open(input_path) as img:
            gray = img.convert("L")
            fmt = img.format or "PNG"
            gray.save(output_path, format=fmt, optimize=True)
        return output_path

    @staticmethod
    async def blur(input_path, output_path, level="medium"):
        r = {"light": 5, "medium": 15, "heavy": 30}.get(level, 15)
        with Image.open(input_path) as img:
            blurred = img.filter(ImageFilter.GaussianBlur(radius=r))
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG" and blurred.mode in ("RGBA", "LA", "P"): blurred = blurred.convert("RGB")
            blurred.save(output_path, format=fmt, optimize=True)
        return output_path

    @staticmethod
    async def upscale(input_path, output_path, factor=2):
        with Image.open(input_path) as img:
            upscaled = img.resize((img.width * factor, img.height * factor), Image.LANCZOS)
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG" and upscaled.mode in ("RGBA", "LA", "P"): upscaled = upscaled.convert("RGB")
            upscaled.save(output_path, format=fmt, optimize=True)
        return output_path

    @staticmethod
    async def to_pdf(input_path, output_path):
        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "LA", "P"): img = img.convert("RGB")
            img.save(output_path, format="PDF", resolution=100.0)
        return output_path

    @staticmethod
    async def get_info(input_path):
        with Image.open(input_path) as img:
            info = {"format": img.format or "Unknown", "mode": img.mode, "width": img.width, "height": img.height,
                    "megapixels": round((img.width * img.height) / 1_000_000, 2), "size_bytes": input_path.stat().st_size}
            ex_c = 0; has_gps = False; cam = "Unknown"
            try:
                exif = img._getexif()
                if exif:
                    ex_c = len(exif)
                    for tid, val in exif.items():
                        tag = ExifTags.TAGS.get(tid, "")
                        if tag == "GPSInfo": has_gps = True
                        if tag == "Model": cam = str(val)[:50]
            except: pass
            info.update({"exif_fields": ex_c, "has_gps": has_gps, "camera": cam, "dpi": "Unknown"})
            return info

    @staticmethod
    async def clean_screenshot(input_path, output_path):
        with Image.open(input_path) as img:
            cropped = img.crop((0, int(img.height * 0.06), img.width, img.height - int(img.height * 0.04)))
            clean = Image.new(cropped.mode, cropped.size)
            clean.putdata(list(cropped.getdata()))
            fmt = img.format or "PNG"
            if fmt.upper() == "JPEG" and clean.mode in ("RGBA", "LA", "P"): clean = clean.convert("RGB")
            clean.save(output_path, format=fmt, optimize=True)
        return output_path

    @staticmethod
    async def id_photo(input_path, output_path, size_type="passport"):
        sz = {"passport": (413, 531), "visa": (600, 600), "stamp": (118, 148)}.get(size_type, (413, 531))
        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "LA", "P"): img = img.convert("RGB")
            tr = sz[0]/sz[1]; ir = img.width/img.height
            if ir > tr:
                nw = int(img.height * tr); l = (img.width - nw) // 2
                img = img.crop((l, 0, l + nw, img.height))
            else:
                nh = int(img.width / tr); t = (img.height - nh) // 2
                img = img.crop((0, t, img.width, t + nh))
            img = img.resize(sz, Image.LANCZOS)
            brd = Image.new("RGB", (sz[0] + 20, sz[1] + 20), (255, 255, 255))
            brd.paste(img, (10, 10))
            brd.save(output_path, format="JPEG", quality=95, optimize=True)
        return output_path
