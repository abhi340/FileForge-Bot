"""
DOCX processing — metadata removal, comment removal, text extraction.
"""

from pathlib import Path

from docx import Document

from app.config import logger


class DOCXService:

    @staticmethod
    async def remove_metadata(input_path: Path, output_path: Path) -> Path:
        doc = Document(str(input_path))
        core = doc.core_properties
        core.author = ""
        core.title = ""
        core.subject = ""
        core.keywords = ""
        core.comments = ""
        core.last_modified_by = ""
        core.category = ""
        core.content_status = ""
        doc.save(str(output_path))
        logger.info(f"DOCX metadata removed: {output_path.name}")
        return output_path

    @staticmethod
    async def remove_comments(input_path: Path, output_path: Path) -> Path:
        try:
            from lxml import etree
        except ImportError:
            from xml.etree import ElementTree as etree

        doc = Document(str(input_path))

        # Remove comment markers from body
        comment_tags = (
            "commentRangeStart",
            "commentRangeEnd",
            "commentReference",
        )

        body = doc.element.body
        elements_to_remove = []

        for element in body.iter():
            tag_name = element.tag.split("}")[-1] if "}" in element.tag else element.tag
            if tag_name in comment_tags:
                elements_to_remove.append(element)

        for element in elements_to_remove:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)

        doc.save(str(output_path))
        logger.info(f"DOCX comments removed: {output_path.name}")
        return output_path

    @staticmethod
    async def extract_text(input_path: Path) -> str:
        doc = Document(str(input_path))
        parts = []

        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text)

        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))

        result = "\n".join(parts)
        if not result.strip():
            result = "No extractable text found."
        logger.info(f"DOCX text extracted: {len(result)} chars")
        return result