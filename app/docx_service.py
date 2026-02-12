from pathlib import Path
from docx import Document
from app.config import logger


class DOCXService:

    @staticmethod
    async def remove_metadata(input_path, output_path):
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
        logger.info(f"DOCX metadata removed")
        return output_path

    @staticmethod
    async def remove_comments(input_path, output_path):
        doc = Document(str(input_path))
        body = doc.element.body
        comment_tags = ("commentRangeStart", "commentRangeEnd", "commentReference")
        to_remove = []
        for element in body.iter():
            tag_name = element.tag.split("}")[-1] if "}" in element.tag else element.tag
            if tag_name in comment_tags:
                to_remove.append(element)
        for element in to_remove:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
        doc.save(str(output_path))
        logger.info(f"DOCX comments removed")
        return output_path

    @staticmethod
    async def extract_text(input_path):
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
