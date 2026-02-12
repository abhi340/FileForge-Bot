import asyncio
from pathlib import Path

from aiogram import Router, Bot, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)

from app.config import BotConfig, logger
from app.database import UsageRepo
from app.file_manager import FileManager, Timer, format_size, detect_category
from app.image_service import ImageService
from app.pdf_service import PDFService
from app.docx_service import DOCXService

router = Router(name="files")

_pending = {}
_semaphore = asyncio.Semaphore(2)


def _keyboard(category):
    buttons = {
        "image": [
            [InlineKeyboardButton(text="Remove Metadata", callback_data="img_meta")],
            [InlineKeyboardButton(text="Resize 50%", callback_data="img_r50")],
            [InlineKeyboardButton(text="Resize 25%", callback_data="img_r25")],
            [
                InlineKeyboardButton(text="PNG", callback_data="img_png"),
                InlineKeyboardButton(text="JPG", callback_data="img_jpg"),
                InlineKeyboardButton(text="WEBP", callback_data="img_webp"),
            ],
            [InlineKeyboardButton(text="Cancel", callback_data="cancel")],
        ],
        "pdf": [
            [InlineKeyboardButton(text="Remove Metadata", callback_data="pdf_meta")],
            [InlineKeyboardButton(text="Extract Text", callback_data="pdf_text")],
            [InlineKeyboardButton(text="Extract Images", callback_data="pdf_imgs")],
            [InlineKeyboardButton(text="Split Pages", callback_data="pdf_split")],
            [InlineKeyboardButton(text="Cancel", callback_data="cancel")],
        ],
        "docx": [
            [InlineKeyboardButton(text="Remove Metadata", callback_data="docx_meta")],
            [InlineKeyboardButton(text="Remove Comments", callback_data="docx_comments")],
            [InlineKeyboardButton(text="Extract Text", callback_data="docx_text")],
            [InlineKeyboardButton(text="Cancel", callback_data="cancel")],
        ],
    }
    return InlineKeyboardMarkup(
        inline_keyboard=buttons.get(category, [
            [InlineKeyboardButton(text="Unsupported", callback_data="cancel")]
        ])
    )


def register_file_handlers(rt, config, fm, usage, bot):
    img = ImageService()
    pdf = PDFService()
    docx = DOCXService()

    @rt.message(F.document)
    async def on_file(message: Message):
        doc = message.document
        user_id = message.from_user.id

        if doc.file_size and doc.file_size > config.max_file_size_bytes:
            max_mb = config.max_file_size_mb
            actual = round(doc.file_size / (1024 * 1024), 2)
            await message.reply(f"File too large: {actual}MB (max {max_mb}MB)")
            return

        category = detect_category(doc.mime_type)
        if not category:
            await message.reply(f"Unsupported type: {doc.mime_type}\nSupported: image, pdf, docx")
            return

        _pending[user_id] = {
            "file_id": doc.file_id,
            "file_name": doc.file_name or "file",
            "file_size": doc.file_size or 0,
            "mime_type": doc.mime_type,
            "category": category,
        }

        size_str = format_size(doc.file_size or 0)
        await message.reply(
            f"File received!\n"
            f"Name: {doc.file_name}\n"
            f"Size: {size_str}\n"
            f"Type: {category.upper()}\n\n"
            f"Choose operation:",
            reply_markup=_keyboard(category),
        )

    @rt.callback_query(F.data == "cancel")
    async def on_cancel(cb: CallbackQuery):
        _pending.pop(cb.from_user.id, None)
        await cb.message.edit_text("Cancelled.")
        await cb.answer()

    @rt.callback_query(F.data == "img_meta")
    async def h1(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "remove_metadata",
                  lambda i, o: img.remove_metadata(i, o))

    @rt.callback_query(F.data == "img_r50")
    async def h2(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "resize_50",
                  lambda i, o: img.resize(i, o, 50))

    @rt.callback_query(F.data == "img_r25")
    async def h3(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "resize_25",
                  lambda i, o: img.resize(i, o, 25))

    @rt.callback_query(F.data == "img_png")
    async def h4(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "to_png",
                  lambda i, o: img.convert(i, o, "PNG"), out_ext=".png")

    @rt.callback_query(F.data == "img_jpg")
    async def h5(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "to_jpg",
                  lambda i, o: img.convert(i, o, "JPEG"), out_ext=".jpg")

    @rt.callback_query(F.data == "img_webp")
    async def h6(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "to_webp",
                  lambda i, o: img.convert(i, o, "WEBP"), out_ext=".webp")

    @rt.callback_query(F.data == "pdf_meta")
    async def h7(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "pdf", "remove_metadata",
                  lambda i, o: pdf.remove_metadata(i, o), out_ext=".pdf")

    @rt.callback_query(F.data == "pdf_text")
    async def h8(cb: CallbackQuery):
        await _do_text(cb, bot, fm, usage, "pdf", "extract_text",
                       lambda i: pdf.extract_text(i), in_ext=".pdf")

    @rt.callback_query(F.data == "pdf_imgs")
    async def h9(cb: CallbackQuery):
        await _do_multi(cb, bot, fm, usage)

    @rt.callback_query(F.data == "pdf_split")
    async def h10(cb: CallbackQuery):
        await _do_split(cb, bot, fm, usage)

    @rt.callback_query(F.data == "docx_meta")
    async def h11(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "docx", "remove_metadata",
                  lambda i, o: docx.remove_metadata(i, o), out_ext=".docx")

    @rt.callback_query(F.data == "docx_comments")
    async def h12(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "docx", "remove_comments",
                  lambda i, o: docx.remove_comments(i, o), out_ext=".docx")

    @rt.callback_query(F.data == "docx_text")
    async def h13(cb: CallbackQuery):
        await _do_text(cb, bot, fm, usage, "docx", "extract_text",
                       lambda i: docx.extract_text(i), in_ext=".docx")


async def _do(cb, bot, config, fm, usage, ftype, tool, process_fn, out_ext=""):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("No file pending. Upload again.", show_alert=True)
        return
    await cb.answer("Processing...")
    await cb.message.edit_text(f"Processing {tool}...")
    inp = None
    out = None
    try:
        async with _semaphore:
            timer = Timer()
            name = data["file_name"]
            in_ext = Path(name).suffix if name else ""
            if not out_ext:
                out_ext = in_ext
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(out_ext)
            with timer:
                await process_fn(inp, out)
            out_name = f"{Path(name).stem}_{tool}{out_ext}"
            result = FSInputFile(path=str(out), filename=out_name)
            await bot.send_document(
                chat_id=cb.message.chat.id,
                document=result,
                caption=f"{tool} done ({timer.elapsed_ms}ms)",
            )
            await usage.log(uid, ftype, tool, data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"{tool} done! ({timer.elapsed_ms}ms)")
    except Exception as e:
        logger.error(f"Process error ({tool}): {e}", exc_info=True)
        await usage.log(uid, ftype, tool, data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        if out:
            fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_text(cb, bot, fm, usage, ftype, tool, extract_fn, in_ext=""):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("No file pending.", show_alert=True)
        return
    await cb.answer("Extracting...")
    await cb.message.edit_text("Extracting text...")
    inp = None
    txt_out = None
    try:
        async with _semaphore:
            timer = Timer()
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            with timer:
                text = await extract_fn(inp)
            if len(text) <= 4000:
                await bot.send_message(
                    chat_id=cb.message.chat.id,
                    text=f"Extracted Text:\n\n{text[:3900]}",
                )
            else:
                txt_out = fm.temp_path(".txt")
                with open(txt_out, "w", encoding="utf-8") as f:
                    f.write(text)
                stem = Path(data["file_name"]).stem
                result = FSInputFile(path=str(txt_out), filename=f"{stem}_text.txt")
                await bot.send_document(
                    chat_id=cb.message.chat.id,
                    document=result,
                    caption=f"{len(text)} characters extracted",
                )
            await usage.log(uid, ftype, tool, data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"Text extracted ({timer.elapsed_ms}ms)")
    except Exception as e:
        logger.error(f"Text extract error: {e}", exc_info=True)
        await usage.log(uid, ftype, tool, data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        if txt_out:
            fm.cleanup(txt_out)
        _pending.pop(uid, None)


async def _do_multi(cb, bot, fm, usage):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("No file pending.", show_alert=True)
        return
    await cb.answer("Extracting images...")
    await cb.message.edit_text("Extracting images...")
    inp = None
    out_dir = None
    try:
        async with _semaphore:
            timer = Timer()
            pdf_svc = PDFService()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out_dir = fm.temp_path("_images")
            out_dir.mkdir(parents=True, exist_ok=True)
            with timer:
                img_paths = await pdf_svc.extract_images(inp, out_dir)
            if not img_paths:
                await cb.message.edit_text("No images found in PDF.")
            else:
                sent = 0
                for ip in img_paths[:10]:
                    try:
                        f = FSInputFile(path=str(ip), filename=ip.name)
                        await bot.send_document(chat_id=cb.message.chat.id, document=f)
                        sent += 1
                    except Exception as e:
                        logger.warning(f"Send image failed: {e}")
                msg = f"{sent} image(s) extracted ({timer.elapsed_ms}ms)"
                await cb.message.edit_text(msg)
            await usage.log(uid, "pdf", "extract_images", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"Image extract error: {e}", exc_info=True)
        await usage.log(uid, "pdf", "extract_images", data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        if out_dir:
            fm.cleanup(out_dir)
        _pending.pop(uid, None)


async def _do_split(cb, bot, fm, usage):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("No file pending.", show_alert=True)
        return
    await cb.answer("Splitting...")
    await cb.message.edit_text("Splitting pages...")
    inp = None
    out_dir = None
    try:
        async with _semaphore:
            timer = Timer()
            pdf_svc = PDFService()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out_dir = fm.temp_path("_pages")
            out_dir.mkdir(parents=True, exist_ok=True)
            with timer:
                pages = await pdf_svc.split_pages(inp, out_dir)
            sent = 0
            for pp in pages[:20]:
                try:
                    f = FSInputFile(path=str(pp), filename=pp.name)
                    await bot.send_document(chat_id=cb.message.chat.id, document=f)
                    sent += 1
                except Exception as e:
                    logger.warning(f"Send page failed: {e}")
            await cb.message.edit_text(f"Split into {sent} page(s) ({timer.elapsed_ms}ms)")
            await usage.log(uid, "pdf", "split_pages", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"Split error: {e}", exc_info=True)
        await usage.log(uid, "pdf", "split_pages", data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        if out_dir:
            fm.cleanup(out_dir)
        _pending.pop(uid, None)
