from pathlib import Path
from typing import List

import pikepdf
import pdfplumber
import fitz

from app.config import logger


class PDFService:

    @staticmethod
    async def remove_metadata(input_path, output_path):
        with pikepdf.open(input_path) as pdf:
            with pdf.open_metadata() as meta:
                for key in list(meta.keys()):
                    del meta[key]
            if "/Info" in pdf.trailer:
                del pdf.trailer["/Info"]
            pdf.save(output_path)
        logger.info("PDF metadata removed")
        return output_path

    @staticmethod
    async def extract_text(input_path):
        parts = []
        with pdfplumber.open(input_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    parts.append(f"--- Page {i + 1} ---\n{text}")
        result = "\n\n".join(parts)
        if not result.strip():
            result = "No extractable text found."
        logger.info(f"PDF text extracted: {len(result)} chars")
        return result

    @staticmethod
    async def extract_images(input_path, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        doc = fitz.open(str(input_path))
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                images = page.get_images(full=True)
                for idx, img in enumerate(images):
                    try:
                        base = doc.extract_image(img[0])
                        img_path = output_dir / f"p{page_num + 1}_img{idx + 1}.{base['ext']}"
                        with open(img_path, "wb") as f:
                            f.write(base["image"])
                        paths.append(img_path)
                    except Exception as e:
                        logger.warning(f"Image extract failed: {e}")
        finally:
            doc.close()
        logger.info(f"PDF images extracted: {len(paths)}")
        return paths

    @staticmethod
    async def split_pages(input_path, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        with pikepdf.open(input_path) as pdf:
            for i, page in enumerate(pdf.pages):
                new_pdf = pikepdf.Pdf.new()
                new_pdf.pages.append(page)
                page_path = output_dir / f"page_{i + 1}.pdf"
                new_pdf.save(page_path)
                paths.append(page_path)
        logger.info(f"PDF split: {len(paths)} pages")
        return paths

    @staticmethod
    async def merge(input_paths, output_path):
        merged = pikepdf.Pdf.new()
        for path in input_paths:
            with pikepdf.open(path) as pdf:
                merged.pages.extend(pdf.pages)
        merged.save(output_path)
        logger.info(f"PDF merged: {len(input_paths)} files → {len(merged.pages)} pages")
        return output_path

    @staticmethod
    async def protect(input_path, output_path, password):
        with pikepdf.open(input_path) as pdf:
            permissions = pikepdf.Permissions(
                extract=False,
                modify_annotation=False,
                modify_assembly=False,
                modify_form=False,
                modify_other=False,
                print_lowres=True,
                print_highres=True,
            )
            pdf.save(
                output_path,
                encryption=pikepdf.Encryption(
                    user=password,
                    owner=password,
                    R=6,
                    allow=permissions,
                ),
            )
        logger.info("PDF password protected")
        return output_path

    @staticmethod
    async def remove_password(input_path, output_path, password):
        try:
            with pikepdf.open(input_path, password=password) as pdf:
                pdf.save(output_path)
            logger.info("PDF password removed")
            return output_path, True
        except pikepdf.PasswordError:
            logger.warning("Wrong PDF password")
            return None, False

    @staticmethod
    async def to_images(input_path, output_dir, dpi=150):
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        doc = fitz.open(str(input_path))
        try:
            for i in range(len(doc)):
                page = doc[i]
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img_path = output_dir / f"page_{i + 1}.png"
                pix.save(str(img_path))
                paths.append(img_path)
        finally:
            doc.close()
        logger.info(f"PDF to images: {len(paths)} pages")
        return paths

    @staticmethod
    async def get_info(input_path):
        info = {
            "size_bytes": input_path.stat().st_size,
        }
        with pdfplumber.open(input_path) as pdf:
            info["pages"] = len(pdf.pages)
            info["metadata"] = {}
            if pdf.metadata:
                for k, v in pdf.metadata.items():
                    if v:
                        info["metadata"][k] = str(v)[:100]

        # Check if encrypted
        try:
            with pikepdf.open(input_path) as pdf:
                info["encrypted"] = False
        except pikepdf.PasswordError:
            info["encrypted"] = True

        # Get page dimensions
        try:
            doc = fitz.open(str(input_path))
            if len(doc) > 0:
                page = doc[0]
                rect = page.rect
                info["width"] = round(rect.width * 25.4 / 72, 1)
                info["height"] = round(rect.height * 25.4 / 72, 1)
            doc.close()
        except Exception:
            info["width"] = 0
            info["height"] = 0

        logger.info("PDF info retrieved")
        return info

    @staticmethod
    async def compress(input_path, output_path):
        doc = fitz.open(str(input_path))
        try:
            doc.save(
                str(output_path),
                garbage=4,
                deflate=True,
                clean=True,
                linear=True,
            )
        finally:
            doc.close()

        original_size = input_path.stat().st_size
        new_size = output_path.stat().st_size
        saved = round((1 - new_size / original_size) * 100, 1) if original_size > 0 else 0
        logger.info(f"PDF compressed: saved {saved}%")
        return output_path, original_size, new_size, saved

    @staticmethod
    async def rotate_pages(input_path, output_path, angle=90):
        with pikepdf.open(input_path) as pdf:
            for page in pdf.pages:
                current = int(page.get("/Rotate", 0))
                page["/Rotate"] = (current + angle) % 360
            pdf.save(output_path)
        logger.info(f"PDF rotated {angle} degrees")
        return output_path

    @staticmethod
    async def extract_page_range(input_path, output_path, start, end):
        with pikepdf.open(input_path) as pdf:
            total = len(pdf.pages)
            if start < 1:
                start = 1
            if end > total:
                end = total
            if start > end:
                start, end = end, start

            new_pdf = pikepdf.Pdf.new()
            for i in range(start - 1, end):
                new_pdf.pages.append(pdf.pages[i])
            new_pdf.save(output_path)

        logger.info(f"PDF pages {start}-{end} extracted")
        return output_path, start, end

    @staticmethod
    async def images_to_pdf(image_paths, output_path):
        from PIL import Image

        images = []
        for path in image_paths:
            img = Image.open(path)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            images.append(img)

        if not images:
            return None

        first = images[0]
        if len(images) > 1:
            first.save(output_path, format="PDF", save_all=True, append_images=images[1:])
        else:
            first.save(output_path, format="PDF")

        for img in images:
            img.close()

        logger.info(f"Images to PDF: {len(image_paths)} images")
        return output_path
