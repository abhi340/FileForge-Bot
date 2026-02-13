import subprocess
import shutil
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
        logger.info("DOCX metadata removed")
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
        logger.info("DOCX comments removed")
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

    @staticmethod
    async def to_pdf(input_path, output_path):
        input_path = Path(input_path)
        output_path = Path(output_path)

        # LibreOffice outputs to a directory, not a specific file
        out_dir = output_path.parent

        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--norestore",
                    "--convert-to", "pdf",
                    "--outdir", str(out_dir),
                    str(input_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(f"LibreOffice error: {result.stderr}")
                raise Exception(f"Conversion failed: {result.stderr[:200]}")

            # LibreOffice creates file with same name but .pdf extension
            generated_pdf = out_dir / f"{input_path.stem}.pdf"

            if not generated_pdf.exists():
                raise Exception("PDF file was not generated")

            # Move to expected output path
            if generated_pdf != output_path:
                shutil.move(str(generated_pdf), str(output_path))

            logger.info("DOCX converted to PDF via LibreOffice")
            return output_path

        except subprocess.TimeoutExpired:
            raise Exception("Conversion timed out (120s limit)")

    @staticmethod
    async def get_info(input_path):
        doc = Document(str(input_path))
        core = doc.core_properties

        total_text = ""
        for para in doc.paragraphs:
            total_text += para.text + " "

        words = len(total_text.split())
        chars = len(total_text)
        chars_no_space = len(total_text.replace(" ", ""))

        info = {
            "paragraphs": len(doc.paragraphs),
            "tables": len(doc.tables),
            "sections": len(doc.sections),
            "words": words,
            "characters": chars,
            "characters_no_space": chars_no_space,
            "author": core.author or "N/A",
            "title": core.title or "N/A",
            "subject": core.subject or "N/A",
            "created": str(core.created) if core.created else "N/A",
            "modified": str(core.modified) if core.modified else "N/A",
            "last_modified_by": core.last_modified_by or "N/A",
            "size_bytes": input_path.stat().st_size,
        }

        image_count = 0
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                image_count += 1
        info["images"] = image_count

        logger.info("DOCX info retrieved")
        return info

    @staticmethod
    async def word_count(input_path):
        doc = Document(str(input_path))
        total_text = ""
        for para in doc.paragraphs:
            total_text += para.text + " "

        words = total_text.split()
        word_count = len(words)
        char_count = len(total_text)
        char_no_space = len(total_text.replace(" ", ""))
        line_count = len([p for p in doc.paragraphs if p.text.strip()])
        sentence_count = total_text.count(".") + total_text.count("!") + total_text.count("?")

        logger.info(f"Word count: {word_count}")
        return {
            "words": word_count,
            "characters": char_count,
            "characters_no_space": char_no_space,
            "lines": line_count,
            "sentences": sentence_count,
            "avg_word_length": round(char_no_space / word_count, 1) if word_count > 0 else 0,
        }

    @staticmethod
    async def extract_images(input_path, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        doc = Document(str(input_path))
        paths = []
        img_count = 0

        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                img_count += 1
                image = rel.target_part
                ext = image.content_type.split("/")[-1]
                if ext == "jpeg":
                    ext = "jpg"
                img_path = output_dir / f"image_{img_count}.{ext}"
                with open(img_path, "wb") as f:
                    f.write(image.blob)
                paths.append(img_path)

        logger.info(f"DOCX images extracted: {len(paths)}")
        return paths

    @staticmethod
    async def extract_tables_csv(input_path, output_dir):
        import csv
        output_dir.mkdir(parents=True, exist_ok=True)
        doc = Document(str(input_path))
        paths = []

        for idx, table in enumerate(doc.tables):
            csv_path = output_dir / f"table_{idx + 1}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for row in table.rows:
                    writer.writerow([cell.text.strip() for cell in row.cells])
            paths.append(csv_path)

        logger.info(f"DOCX tables extracted: {len(paths)} CSV files")
        return paths
