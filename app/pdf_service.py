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
        logger.info(f"PDF metadata removed")
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
