import asyncio
import zipfile
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
_waiting_resize = {}
_waiting_password = {}
_waiting_unlock = {}
_waiting_pages = {}
_merge_queue = {}


def _keyboard(category):
    buttons = {
        "image": [
            [InlineKeyboardButton(text="🧹 Remove Metadata", callback_data="img_meta")],
            [
                InlineKeyboardButton(text="📐 50%", callback_data="img_r50"),
                InlineKeyboardButton(text="📐 25%", callback_data="img_r25"),
                InlineKeyboardButton(text="📐 Custom", callback_data="img_rcustom"),
            ],
            [
                InlineKeyboardButton(text="→ PNG", callback_data="img_png"),
                InlineKeyboardButton(text="→ JPG", callback_data="img_jpg"),
                InlineKeyboardButton(text="→ WEBP", callback_data="img_webp"),
            ],
            [
                InlineKeyboardButton(text="📷 Low", callback_data="img_comp_low"),
                InlineKeyboardButton(text="📷 Med", callback_data="img_comp_med"),
                InlineKeyboardButton(text="📷 High", callback_data="img_comp_high"),
            ],
            [
                InlineKeyboardButton(text="⬛ Grayscale", callback_data="img_gray"),
                InlineKeyboardButton(text="📏 Info", callback_data="img_info"),
            ],
            [
                InlineKeyboardButton(text="🔒 Blur Light", callback_data="img_blur_light"),
                InlineKeyboardButton(text="🔒 Blur Med", callback_data="img_blur_med"),
                InlineKeyboardButton(text="🔒 Blur Heavy", callback_data="img_blur_heavy"),
            ],
            [
                InlineKeyboardButton(text="🔍 Upscale 2x", callback_data="img_up2"),
                InlineKeyboardButton(text="🔍 Upscale 4x", callback_data="img_up4"),
            ],
            [
                InlineKeyboardButton(text="📄 To PDF", callback_data="img_pdf"),
                InlineKeyboardButton(text="📸 Clean Screenshot", callback_data="img_screenshot"),
            ],
            [
                InlineKeyboardButton(text="🪪 Passport", callback_data="img_id_passport"),
                InlineKeyboardButton(text="🪪 Visa", callback_data="img_id_visa"),
                InlineKeyboardButton(text="🪪 Stamp", callback_data="img_id_stamp"),
            ],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")],
        ],
        "pdf": [
            [InlineKeyboardButton(text="🧹 Remove Metadata", callback_data="pdf_meta")],
            [InlineKeyboardButton(text="📝 Extract Text", callback_data="pdf_text")],
            [InlineKeyboardButton(text="🖼 Extract Images", callback_data="pdf_imgs")],
            [InlineKeyboardButton(text="✂️ Split Pages", callback_data="pdf_split")],
            [InlineKeyboardButton(text="📊 PDF Info", callback_data="pdf_info")],
            [InlineKeyboardButton(text="🗜 Compress PDF", callback_data="pdf_compress")],
            [InlineKeyboardButton(text="🖼 PDF → Images", callback_data="pdf_to_img")],
            [
                InlineKeyboardButton(text="🔄 Rotate 90°", callback_data="pdf_rot90"),
                InlineKeyboardButton(text="🔄 Rotate 180°", callback_data="pdf_rot180"),
            ],
            [InlineKeyboardButton(text="📄 Extract Pages", callback_data="pdf_extract_pages")],
            [InlineKeyboardButton(text="🔒 Password Protect", callback_data="pdf_protect")],
            [InlineKeyboardButton(text="🔓 Remove Password", callback_data="pdf_unlock")],
            [InlineKeyboardButton(text="📎 Merge PDFs (start)", callback_data="pdf_merge_start")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")],
        ],
        "docx": [
            [InlineKeyboardButton(text="🧹 Remove Metadata", callback_data="docx_meta")],
            [InlineKeyboardButton(text="💬 Remove Comments", callback_data="docx_comments")],
            [InlineKeyboardButton(text="📝 Extract Text", callback_data="docx_text")],
            [InlineKeyboardButton(text="📄 Convert to PDF", callback_data="docx_to_pdf")],
            [InlineKeyboardButton(text="📊 DOCX Info", callback_data="docx_info")],
            [InlineKeyboardButton(text="🔢 Word Count", callback_data="docx_wordcount")],
            [InlineKeyboardButton(text="🖼 Extract Images", callback_data="docx_images")],
            [InlineKeyboardButton(text="📋 Tables to CSV", callback_data="docx_tables")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")],
        ],
    }
    return InlineKeyboardMarkup(
        inline_keyboard=buttons.get(category, [
            [InlineKeyboardButton(text="❌ Unsupported", callback_data="cancel")]
        ])
    )


def register_file_handlers(rt, config, fm, usage, bot):
    img = ImageService()
    pdf = PDFService()
    docx = DOCXService()

    # ── File upload handlers ──

    @rt.message(F.photo)
    async def on_photo(message: Message):
        user_id = message.from_user.id
        if user_id in _waiting_resize or user_id in _waiting_password or user_id in _waiting_unlock or user_id in _waiting_pages:
            return
        photo = message.photo[-1]
        if photo.file_size and photo.file_size > config.max_file_size_bytes:
            await message.reply(f"❌ Photo too large (max {config.max_file_size_mb}MB)")
            return
        _pending[user_id] = {
            "file_id": photo.file_id,
            "file_name": "photo.jpg",
            "file_size": photo.file_size or 0,
            "mime_type": "image/jpeg",
            "category": "image",
        }
        size_str = format_size(photo.file_size or 0)
        await message.reply(
            f"🖼 Photo received! ({size_str})\n"
            f"⚠️ Send as File for full quality\n\n"
            f"Choose operation:",
            reply_markup=_keyboard("image"),
        )

    @rt.message(F.document)
    async def on_file(message: Message):
        doc = message.document
        user_id = message.from_user.id

        if user_id in _merge_queue:
            if doc.mime_type == "application/pdf":
                path = fm.temp_path(".pdf")
                tg_file = await bot.get_file(doc.file_id)
                await bot.download_file(tg_file.file_path, destination=str(path))
                _merge_queue[user_id]["files"].append(path)
                count = len(_merge_queue[user_id]["files"])
                await message.reply(
                    f"📎 PDF #{count} added!\n\nSend more or click Done:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=f"✅ Merge {count} PDFs", callback_data="pdf_merge_done")],
                        [InlineKeyboardButton(text="❌ Cancel", callback_data="pdf_merge_cancel")],
                    ]),
                )
            else:
                await message.reply("❌ Only PDF files for merge.")
            return

        if doc.file_size and doc.file_size > config.max_file_size_bytes:
            await message.reply(f"❌ File too large (max {config.max_file_size_mb}MB)")
            return
        category = detect_category(doc.mime_type)
        if not category:
            await message.reply(f"❌ Unsupported: {doc.mime_type}\nSupported: image, pdf, docx")
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
            f"📁 File received!\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📄 {doc.file_name}\n"
            f"📦 {size_str}\n"
            f"🏷 {category.upper()}\n\n"
            f"Choose operation:",
            reply_markup=_keyboard(category),
        )

    # ── Text input handler ──

    @rt.message(F.text)
    async def on_text(message: Message):
        user_id = message.from_user.id
        text = message.text.strip()

        if user_id in _waiting_resize:
            data = _waiting_resize.pop(user_id)
            try:
                if "x" in text.lower():
                    parts = text.lower().split("x")
                    w = int(parts[0].strip())
                    h = int(parts[1].strip())
                    if w < 1 or h < 1 or w > 10000 or h > 10000:
                        await message.reply("❌ Size must be 1-10000")
                        return
                    await _do_resize_exact(message, bot, config, fm, usage, data, w, h)
                else:
                    pct = int(text)
                    if pct < 1 or pct > 500:
                        await message.reply("❌ Percentage must be 1-500")
                        return
                    await _do_resize_pct(message, bot, config, fm, usage, data, pct)
            except ValueError:
                await message.reply("❌ Invalid. Use '50' or '800x600'")
            return

        if user_id in _waiting_password:
            data = _waiting_password.pop(user_id)
            if len(text) < 1:
                await message.reply("❌ Password cannot be empty")
                return
            await _do_protect(message, bot, fm, usage, data, text)
            return

        if user_id in _waiting_unlock:
            data = _waiting_unlock.pop(user_id)
            await _do_unlock(message, bot, fm, usage, data, text)
            return

        if user_id in _waiting_pages:
            data = _waiting_pages.pop(user_id)
            try:
                if "-" in text:
                    parts = text.split("-")
                    start = int(parts[0].strip())
                    end = int(parts[1].strip())
                else:
                    start = int(text)
                    end = start
                await _do_extract_pages(message, bot, fm, usage, data, start, end)
            except ValueError:
                await message.reply("❌ Invalid. Use '3' or '2-5'")
            return

    # ── Cancel ──

    @rt.callback_query(F.data == "cancel")
    async def on_cancel(cb: CallbackQuery):
        uid = cb.from_user.id
        _pending.pop(uid, None)
        _waiting_resize.pop(uid, None)
        _waiting_password.pop(uid, None)
        _waiting_unlock.pop(uid, None)
        _waiting_pages.pop(uid, None)
        if uid in _merge_queue:
            for f in _merge_queue[uid].get("files", []):
                fm.cleanup(f)
            _merge_queue.pop(uid, None)
        await cb.message.edit_text("❌ Cancelled.")
        await cb.answer()

    # ══════════════════════════════════════
    # IMAGE HANDLERS
    # ══════════════════════════════════════

    @rt.callback_query(F.data == "img_meta")
    async def h1(cb): await _do(cb, bot, config, fm, usage, "image", "remove_metadata", lambda i, o: img.remove_metadata(i, o))
    @rt.callback_query(F.data == "img_r50")
    async def h2(cb): await _do(cb, bot, config, fm, usage, "image", "resize_50", lambda i, o: img.resize(i, o, 50))
    @rt.callback_query(F.data == "img_r25")
    async def h3(cb): await _do(cb, bot, config, fm, usage, "image", "resize_25", lambda i, o: img.resize(i, o, 25))
    @rt.callback_query(F.data == "img_png")
    async def h4(cb): await _do(cb, bot, config, fm, usage, "image", "to_png", lambda i, o: img.convert(i, o, "PNG"), out_ext=".png")
    @rt.callback_query(F.data == "img_jpg")
    async def h5(cb): await _do(cb, bot, config, fm, usage, "image", "to_jpg", lambda i, o: img.convert(i, o, "JPEG"), out_ext=".jpg")
    @rt.callback_query(F.data == "img_webp")
    async def h6(cb): await _do(cb, bot, config, fm, usage, "image", "to_webp", lambda i, o: img.convert(i, o, "WEBP"), out_ext=".webp")

    @rt.callback_query(F.data == "img_rcustom")
    async def h_rc(cb: CallbackQuery):
        uid = cb.from_user.id
        data = _pending.get(uid)
        if not data:
            await cb.answer("❌ No file pending.", show_alert=True)
            return
        _waiting_resize[uid] = data
        await cb.message.edit_text("📐 Send size:\n\n• Percentage: 75\n• Exact: 800x600")
        await cb.answer()

    @rt.callback_query(F.data == "img_comp_low")
    async def hcl(cb): await _do_compress(cb, bot, config, fm, usage, img, "low")
    @rt.callback_query(F.data == "img_comp_med")
    async def hcm(cb): await _do_compress(cb, bot, config, fm, usage, img, "medium")
    @rt.callback_query(F.data == "img_comp_high")
    async def hch(cb): await _do_compress(cb, bot, config, fm, usage, img, "high")

    @rt.callback_query(F.data == "img_gray")
    async def hg(cb): await _do(cb, bot, config, fm, usage, "image", "grayscale", lambda i, o: img.grayscale(i, o))
    @rt.callback_query(F.data == "img_info")
    async def hi(cb): await _do_img_info(cb, bot, fm, usage, img)

    @rt.callback_query(F.data == "img_blur_light")
    async def hbl(cb): await _do(cb, bot, config, fm, usage, "image", "blur_light", lambda i, o: img.blur(i, o, "light"))
    @rt.callback_query(F.data == "img_blur_med")
    async def hbm(cb): await _do(cb, bot, config, fm, usage, "image", "blur_medium", lambda i, o: img.blur(i, o, "medium"))
    @rt.callback_query(F.data == "img_blur_heavy")
    async def hbh(cb): await _do(cb, bot, config, fm, usage, "image", "blur_heavy", lambda i, o: img.blur(i, o, "heavy"))

    @rt.callback_query(F.data == "img_up2")
    async def hu2(cb): await _do(cb, bot, config, fm, usage, "image", "upscale_2x", lambda i, o: img.upscale(i, o, 2))
    @rt.callback_query(F.data == "img_up4")
    async def hu4(cb): await _do(cb, bot, config, fm, usage, "image", "upscale_4x", lambda i, o: img.upscale(i, o, 4))

    @rt.callback_query(F.data == "img_pdf")
    async def hipdf(cb): await _do(cb, bot, config, fm, usage, "image", "to_pdf", lambda i, o: img.to_pdf(i, o), out_ext=".pdf")
    @rt.callback_query(F.data == "img_screenshot")
    async def hss(cb): await _do(cb, bot, config, fm, usage, "image", "clean_screenshot", lambda i, o: img.clean_screenshot(i, o))

    @rt.callback_query(F.data == "img_id_passport")
    async def hidp(cb): await _do(cb, bot, config, fm, usage, "image", "id_passport", lambda i, o: img.id_photo(i, o, "passport"), out_ext=".jpg")
    @rt.callback_query(F.data == "img_id_visa")
    async def hidv(cb): await _do(cb, bot, config, fm, usage, "image", "id_visa", lambda i, o: img.id_photo(i, o, "visa"), out_ext=".jpg")
    @rt.callback_query(F.data == "img_id_stamp")
    async def hids(cb): await _do(cb, bot, config, fm, usage, "image", "id_stamp", lambda i, o: img.id_photo(i, o, "stamp"), out_ext=".jpg")

    # ══════════════════════════════════════
    # PDF HANDLERS
    # ══════════════════════════════════════

    @rt.callback_query(F.data == "pdf_meta")
    async def p1(cb): await _do(cb, bot, config, fm, usage, "pdf", "remove_metadata", lambda i, o: pdf.remove_metadata(i, o), out_ext=".pdf")
    @rt.callback_query(F.data == "pdf_text")
    async def p2(cb): await _do_text(cb, bot, fm, usage, "pdf", "extract_text", lambda i: pdf.extract_text(i), in_ext=".pdf")
    @rt.callback_query(F.data == "pdf_imgs")
    async def p3(cb): await _do_multi(cb, bot, fm, usage, pdf)
    @rt.callback_query(F.data == "pdf_split")
    async def p4(cb): await _do_split(cb, bot, fm, usage, pdf)
    @rt.callback_query(F.data == "pdf_info")
    async def p5(cb): await _do_pdf_info(cb, bot, fm, usage, pdf)
    @rt.callback_query(F.data == "pdf_compress")
    async def p6(cb): await _do_pdf_compress(cb, bot, fm, usage, pdf)
    @rt.callback_query(F.data == "pdf_to_img")
    async def p7(cb): await _do_pdf_to_images(cb, bot, fm, usage, pdf)
    @rt.callback_query(F.data == "pdf_rot90")
    async def p8a(cb): await _do(cb, bot, config, fm, usage, "pdf", "rotate_90", lambda i, o: pdf.rotate_pages(i, o, 90), out_ext=".pdf")
    @rt.callback_query(F.data == "pdf_rot180")
    async def p8b(cb): await _do(cb, bot, config, fm, usage, "pdf", "rotate_180", lambda i, o: pdf.rotate_pages(i, o, 180), out_ext=".pdf")

    @rt.callback_query(F.data == "pdf_extract_pages")
    async def p9(cb: CallbackQuery):
        uid = cb.from_user.id
        data = _pending.get(uid)
        if not data:
            await cb.answer("❌ No file pending.", show_alert=True)
            return
        _waiting_pages[uid] = data
        await cb.message.edit_text("📄 Extract Pages\n\nSend page range:\n• Single: 3\n• Range: 2-5")
        await cb.answer()

    @rt.callback_query(F.data == "pdf_protect")
    async def p10(cb: CallbackQuery):
        uid = cb.from_user.id
        data = _pending.get(uid)
        if not data:
            await cb.answer("❌ No file pending.", show_alert=True)
            return
        _waiting_password[uid] = data
        await cb.message.edit_text("🔒 Send the password you want to set:")
        await cb.answer()

    @rt.callback_query(F.data == "pdf_unlock")
    async def p11(cb: CallbackQuery):
        uid = cb.from_user.id
        data = _pending.get(uid)
        if not data:
            await cb.answer("❌ No file pending.", show_alert=True)
            return
        _waiting_unlock[uid] = data
        await cb.message.edit_text("🔓 Send the current password:")
        await cb.answer()

    @rt.callback_query(F.data == "pdf_merge_start")
    async def p12(cb: CallbackQuery):
        uid = cb.from_user.id
        data = _pending.get(uid)
        if not data:
            await cb.answer("❌ No file pending.", show_alert=True)
            return
        path = fm.temp_path(".pdf")
        tg_file = await bot.get_file(data["file_id"])
        await bot.download_file(tg_file.file_path, destination=str(path))
        _merge_queue[uid] = {"files": [path]}
        _pending.pop(uid, None)
        await cb.message.edit_text(
            "📎 Merge PDFs\n━━━━━━━━━━━━━━━━━━━━━\nPDF #1 added!\n\nSend more PDFs, click Done when ready.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Merge 1 PDF", callback_data="pdf_merge_done")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="pdf_merge_cancel")],
            ]),
        )
        await cb.answer()

    @rt.callback_query(F.data == "pdf_merge_done")
    async def p12_done(cb: CallbackQuery):
        uid = cb.from_user.id
        if uid not in _merge_queue:
            await cb.answer("❌ No merge in progress.", show_alert=True)
            return
        files = _merge_queue[uid]["files"]
        if len(files) < 2:
            await cb.answer("❌ Need at least 2 PDFs.", show_alert=True)
            return
        await cb.answer("⏳ Merging...")
        await cb.message.edit_text(f"⏳ Merging {len(files)} PDFs...")
        out = None
        try:
            async with _semaphore:
                timer = Timer()
                out = fm.temp_path(".pdf")
                with timer: await pdf.merge(files, out)
                result = FSInputFile(path=str(out), filename="merged.pdf")
                await bot.send_document(chat_id=cb.message.chat.id, document=result,
                    caption=f"✅ Merged {len(files)} PDFs ({timer.elapsed_ms}ms)")
                await usage.log(uid, "pdf", "merge", 0, "success", "", timer.elapsed_ms)
                await cb.message.edit_text(f"✅ Merged {len(files)} PDFs! ({timer.elapsed_ms}ms)")
        except Exception as e:
            logger.error(f"Merge error: {e}", exc_info=True)
            await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
        finally:
            for f in files: fm.cleanup(f)
            if out: fm.cleanup(out)
            _merge_queue.pop(uid, None)

    @rt.callback_query(F.data == "pdf_merge_cancel")
    async def p12_cancel(cb: CallbackQuery):
        uid = cb.from_user.id
        if uid in _merge_queue:
            for f in _merge_queue[uid].get("files", []): fm.cleanup(f)
            _merge_queue.pop(uid, None)
        await cb.message.edit_text("❌ Merge cancelled.")
        await cb.answer()

    # ══════════════════════════════════════
    # DOCX HANDLERS
    # ══════════════════════════════════════

    @rt.callback_query(F.data == "docx_meta")
    async def d1(cb): await _do(cb, bot, config, fm, usage, "docx", "remove_metadata", lambda i, o: docx.remove_metadata(i, o), out_ext=".docx")
    @rt.callback_query(F.data == "docx_comments")
    async def d2(cb): await _do(cb, bot, config, fm, usage, "docx", "remove_comments", lambda i, o: docx.remove_comments(i, o), out_ext=".docx")
    @rt.callback_query(F.data == "docx_text")
    async def d3(cb): await _do_text(cb, bot, fm, usage, "docx", "extract_text", lambda i: docx.extract_text(i), in_ext=".docx")
    @rt.callback_query(F.data == "docx_to_pdf")
    async def d4(cb): await _do(cb, bot, config, fm, usage, "docx", "to_pdf", lambda i, o: docx.to_pdf(i, o), out_ext=".pdf")
    @rt.callback_query(F.data == "docx_info")
    async def d5(cb): await _do_docx_info(cb, bot, fm, usage, docx)
    @rt.callback_query(F.data == "docx_wordcount")
    async def d6(cb): await _do_word_count(cb, bot, fm, usage, docx)
    @rt.callback_query(F.data == "docx_images")
    async def d7(cb): await _do_docx_images(cb, bot, fm, usage, docx)
    @rt.callback_query(F.data == "docx_tables")
    async def d8(cb): await _do_docx_tables(cb, bot, fm, usage, docx)


# ══════════════════════════════════════════════
# CORE PROCESSING FUNCTIONS
# ══════════════════════════════════════════════

async def _do(cb, bot, config, fm, usage, ftype, tool, process_fn, out_ext=""):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text(f"⏳ {tool}...")
    inp = out = None
    try:
        async with _semaphore:
            timer = Timer()
            name = data["file_name"]
            in_ext = Path(name).suffix if name else ".jpg"
            if not out_ext: out_ext = in_ext
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(out_ext)
            with timer: await process_fn(inp, out)
            doc = FSInputFile(path=str(out), filename=f"{Path(name).stem}_{tool}{out_ext}")
            await bot.send_document(chat_id=cb.message.chat.id, document=doc, caption=f"✅ {tool} ({timer.elapsed_ms}ms)")
            await usage.log(uid, ftype, tool, data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"✅ {tool} done! ({timer.elapsed_ms}ms)")
    except Exception as e:
        logger.error(f"Error ({tool}): {e}", exc_info=True)
        await usage.log(uid, ftype, tool, data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out: fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_compress(cb, bot, config, fm, usage, img_svc, level):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text(f"⏳ Compressing ({level})...")
    inp = out = None
    try:
        async with _semaphore:
            timer = Timer()
            name = data["file_name"]
            inp = fm.temp_path(Path(name).suffix if name else ".jpg")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(".jpg")
            with timer: _, orig, new, saved = await img_svc.compress(inp, out, level)
            doc = FSInputFile(path=str(out), filename=f"{Path(name).stem}_compressed.jpg")
            await bot.send_document(chat_id=cb.message.chat.id, document=doc,
                caption=f"✅ Compressed ({level})\n📦 {format_size(orig)} → {format_size(new)}\n💾 Saved: {saved}%")
            await usage.log(uid, "image", f"compress_{level}", data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"✅ Compressed! Saved {saved}%")
    except Exception as e:
        logger.error(f"Compress error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out: fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_img_info(cb, bot, fm, usage, img_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("🔍")
    inp = None
    try:
        async with _semaphore:
            name = data["file_name"]
            inp = fm.temp_path(Path(name).suffix if name else ".jpg")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            info = await img_svc.get_info(inp)
            gps = "⚠️ YES!" if info["has_gps"] else "✅ No"
            await cb.message.edit_text(
                f"📏 Image Info\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📄 {name}\n🖼 {info['format']}\n📐 {info['width']}x{info['height']}\n"
                f"📊 {info['megapixels']}MP\n📦 {format_size(info['size_bytes'])}\n"
                f"🎨 {info['mode']}\n📏 DPI: {info['dpi']}\n📷 {info['camera']}\n"
                f"🏷 EXIF: {info['exif_fields']} fields\n📍 GPS: {gps}")
            await usage.log(uid, "image", "info", data["file_size"], "success")
    except Exception as e:
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        _pending.pop(uid, None)


async def _do_text(cb, bot, fm, usage, ftype, tool, extract_fn, in_ext=""):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text("⏳ Extracting text...")
    inp = txt_out = None
    try:
        async with _semaphore:
            timer = Timer()
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            with timer: text = await extract_fn(inp)
            if len(text) <= 4000:
                await bot.send_message(chat_id=cb.message.chat.id, text=f"📝 Extracted:\n\n{text[:3900]}")
            else:
                txt_out = fm.temp_path(".txt")
                with open(txt_out, "w", encoding="utf-8") as f: f.write(text)
                result = FSInputFile(path=str(txt_out), filename=f"{Path(data['file_name']).stem}_text.txt")
                await bot.send_document(chat_id=cb.message.chat.id, document=result, caption=f"📝 {len(text)} chars")
            await usage.log(uid, ftype, tool, data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"✅ Extracted ({timer.elapsed_ms}ms)")
    except Exception as e:
        logger.error(f"Extract error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if txt_out: fm.cleanup(txt_out)
        _pending.pop(uid, None)


async def _do_multi(cb, bot, fm, usage, pdf_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text("⏳ Extracting images...")
    inp = out_dir = zip_path = None
    try:
        async with _semaphore:
            timer = Timer()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out_dir = fm.temp_path("_imgs")
            out_dir.mkdir(parents=True, exist_ok=True)
            with timer: paths = await pdf_svc.extract_images(inp, out_dir)
            if not paths:
                await cb.message.edit_text("ℹ️ No images found.")
            elif len(paths) <= 10:
                sent = 0
                for p in paths:
                    try:
                        f = FSInputFile(path=str(p), filename=p.name)
                        await bot.send_document(chat_id=cb.message.chat.id, document=f)
                        sent += 1
                    except: pass
                await cb.message.edit_text(f"✅ {sent} image(s) ({timer.elapsed_ms}ms)")
            else:
                zip_path = fm.temp_path(".zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in paths: zf.write(p, p.name)
                f = FSInputFile(path=str(zip_path), filename=f"{Path(data['file_name']).stem}_images.zip")
                await bot.send_document(chat_id=cb.message.chat.id, document=f,
                    caption=f"✅ {len(paths)} images (zipped) ({timer.elapsed_ms}ms)")
                await cb.message.edit_text(f"✅ {len(paths)} images → ZIP ({timer.elapsed_ms}ms)")
            await usage.log(uid, "pdf", "extract_images", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"Extract error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out_dir: fm.cleanup(out_dir)
        if zip_path: fm.cleanup(zip_path)
        _pending.pop(uid, None)


async def _do_split(cb, bot, fm, usage, pdf_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text("⏳ Splitting...")
    inp = out_dir = zip_path = None
    try:
        async with _semaphore:
            timer = Timer()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out_dir = fm.temp_path("_pages")
            out_dir.mkdir(parents=True, exist_ok=True)
            with timer: pages = await pdf_svc.split_pages(inp, out_dir)
            if len(pages) <= 10:
                sent = 0
                for p in pages:
                    try:
                        f = FSInputFile(path=str(p), filename=p.name)
                        await bot.send_document(chat_id=cb.message.chat.id, document=f)
                        sent += 1
                    except: pass
                await cb.message.edit_text(f"✅ {sent} pages ({timer.elapsed_ms}ms)")
            else:
                zip_path = fm.temp_path(".zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in pages: zf.write(p, p.name)
                f = FSInputFile(path=str(zip_path), filename=f"{Path(data['file_name']).stem}_split.zip")
                await bot.send_document(chat_id=cb.message.chat.id, document=f,
                    caption=f"✅ {len(pages)} pages (zipped) ({timer.elapsed_ms}ms)")
                await cb.message.edit_text(f"✅ {len(pages)} pages → ZIP ({timer.elapsed_ms}ms)")
            await usage.log(uid, "pdf", "split", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"Split error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out_dir: fm.cleanup(out_dir)
        if zip_path: fm.cleanup(zip_path)
        _pending.pop(uid, None)


async def _do_pdf_info(cb, bot, fm, usage, pdf_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("🔍")
    inp = None
    try:
        async with _semaphore:
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            info = await pdf_svc.get_info(inp)
            meta_str = "\n".join([f"  {k}: {v}" for k, v in info.get("metadata", {}).items()]) or "  None"
            encrypted = "🔒 Yes" if info.get("encrypted") else "🔓 No"
            await cb.message.edit_text(
                f"📊 PDF Info\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📄 {data['file_name']}\n📦 {format_size(info['size_bytes'])}\n"
                f"📑 Pages: {info['pages']}\n📐 {info.get('width', 0)}x{info.get('height', 0)} mm\n"
                f"🔐 Encrypted: {encrypted}\n\n📋 Metadata:\n{meta_str}")
            await usage.log(uid, "pdf", "info", data["file_size"], "success")
    except Exception as e:
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        _pending.pop(uid, None)


async def _do_pdf_compress(cb, bot, fm, usage, pdf_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text("⏳ Compressing PDF...")
    inp = out = None
    try:
        async with _semaphore:
            timer = Timer()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(".pdf")
            with timer: _, orig, new, saved = await pdf_svc.compress(inp, out)
            doc = FSInputFile(path=str(out), filename=f"{Path(data['file_name']).stem}_compressed.pdf")
            await bot.send_document(chat_id=cb.message.chat.id, document=doc,
                caption=f"✅ PDF Compressed\n📦 {format_size(orig)} → {format_size(new)}\n💾 Saved: {saved}%")
            await usage.log(uid, "pdf", "compress", data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"✅ Compressed! Saved {saved}%")
    except Exception as e:
        logger.error(f"PDF compress error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out: fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_pdf_to_images(cb, bot, fm, usage, pdf_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text("⏳ Converting to images...")
    inp = out_dir = zip_path = None
    try:
        async with _semaphore:
            timer = Timer()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out_dir = fm.temp_path("_pdfimg")
            out_dir.mkdir(parents=True, exist_ok=True)
            with timer: paths = await pdf_svc.to_images(inp, out_dir)
            if not paths:
                await cb.message.edit_text("ℹ️ No pages found.")
            elif len(paths) <= 10:
                sent = 0
                for p in paths:
                    try:
                        f = FSInputFile(path=str(p), filename=p.name)
                        await bot.send_document(chat_id=cb.message.chat.id, document=f)
                        sent += 1
                    except Exception as e:
                        logger.warning(f"Send failed: {e}")
                await cb.message.edit_text(f"✅ {sent} page(s) as images ({timer.elapsed_ms}ms)")
            else:
                zip_path = fm.temp_path(".zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in paths: zf.write(p, p.name)
                f = FSInputFile(path=str(zip_path), filename=f"{Path(data['file_name']).stem}_pages.zip")
                await bot.send_document(chat_id=cb.message.chat.id, document=f,
                    caption=f"✅ {len(paths)} pages as images (zipped)\n⏱ {timer.elapsed_ms}ms")
                await cb.message.edit_text(f"✅ {len(paths)} pages → ZIP ({timer.elapsed_ms}ms)")
            await usage.log(uid, "pdf", "to_images", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"PDF to images error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out_dir: fm.cleanup(out_dir)
        if zip_path: fm.cleanup(zip_path)
        _pending.pop(uid, None)


async def _do_protect(message, bot, fm, usage, data, password):
    uid = message.from_user.id
    inp = out = None
    try:
        async with _semaphore:
            timer = Timer()
            pdf_svc = PDFService()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(".pdf")
            with timer: await pdf_svc.protect(inp, out, password)
            doc = FSInputFile(path=str(out), filename=f"{Path(data['file_name']).stem}_protected.pdf")
            await bot.send_document(chat_id=message.chat.id, document=doc,
                caption=f"🔒 Protected ({timer.elapsed_ms}ms)\n⚠️ Remember your password!")
            await usage.log(uid, "pdf", "protect", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out: fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_unlock(message, bot, fm, usage, data, password):
    uid = message.from_user.id
    inp = out = None
    try:
        async with _semaphore:
            timer = Timer()
            pdf_svc = PDFService()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(".pdf")
            with timer: result, success = await pdf_svc.remove_password(inp, out, password)
            if success:
                doc = FSInputFile(path=str(out), filename=f"{Path(data['file_name']).stem}_unlocked.pdf")
                await bot.send_document(chat_id=message.chat.id, document=doc,
                    caption=f"🔓 Unlocked ({timer.elapsed_ms}ms)")
                await usage.log(uid, "pdf", "unlock", data["file_size"], "success", "", timer.elapsed_ms)
            else:
                await message.reply("❌ Wrong password.")
                await usage.log(uid, "pdf", "unlock", data["file_size"], "failure", "wrong password")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out: fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_extract_pages(message, bot, fm, usage, data, start, end):
    uid = message.from_user.id
    inp = out = None
    try:
        async with _semaphore:
            timer = Timer()
            pdf_svc = PDFService()
            inp = fm.temp_path(".pdf")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(".pdf")
            with timer: _, s, e = await pdf_svc.extract_page_range(inp, out, start, end)
            doc = FSInputFile(path=str(out), filename=f"{Path(data['file_name']).stem}_p{s}-{e}.pdf")
            await bot.send_document(chat_id=message.chat.id, document=doc,
                caption=f"✅ Pages {s}-{e} extracted ({timer.elapsed_ms}ms)")
            await usage.log(uid, "pdf", f"pages_{s}-{e}", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out: fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_resize_pct(message, bot, config, fm, usage, data, pct):
    uid = message.from_user.id
    inp = out = None
    try:
        async with _semaphore:
            timer = Timer()
            img_svc = ImageService()
            name = data["file_name"]
            in_ext = Path(name).suffix if name else ".jpg"
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(in_ext)
            with timer: await img_svc.resize(inp, out, pct)
            doc = FSInputFile(path=str(out), filename=f"{Path(name).stem}_{pct}pct{in_ext}")
            await bot.send_document(chat_id=message.chat.id, document=doc, caption=f"✅ Resized to {pct}% ({timer.elapsed_ms}ms)")
            await usage.log(uid, "image", f"resize_{pct}", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out: fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_resize_exact(message, bot, config, fm, usage, data, w, h):
    uid = message.from_user.id
    inp = out = None
    try:
        async with _semaphore:
            timer = Timer()
            img_svc = ImageService()
            name = data["file_name"]
            in_ext = Path(name).suffix if name else ".jpg"
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(in_ext)
            with timer: await img_svc.resize_exact(inp, out, w, h)
            doc = FSInputFile(path=str(out), filename=f"{Path(name).stem}_{w}x{h}{in_ext}")
            await bot.send_document(chat_id=message.chat.id, document=doc, caption=f"✅ Resized to {w}x{h} ({timer.elapsed_ms}ms)")
            await usage.log(uid, "image", f"resize_{w}x{h}", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out: fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_docx_info(cb, bot, fm, usage, docx_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("🔍")
    inp = None
    try:
        async with _semaphore:
            inp = fm.temp_path(".docx")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            info = await docx_svc.get_info(inp)
            await cb.message.edit_text(
                f"📊 DOCX Info\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📄 {data['file_name']}\n📦 {format_size(info['size_bytes'])}\n"
                f"📝 Paragraphs: {info['paragraphs']}\n📊 Tables: {info['tables']}\n"
                f"📑 Sections: {info['sections']}\n🖼 Images: {info['images']}\n"
                f"🔢 Words: {info['words']}\n🔤 Characters: {info['characters']}\n\n"
                f"👤 Author: {info['author']}\n📌 Title: {info['title']}\n"
                f"📅 Created: {info['created']}\n📅 Modified: {info['modified']}\n"
                f"👤 Modified by: {info['last_modified_by']}")
            await usage.log(uid, "docx", "info", data["file_size"], "success")
    except Exception as e:
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        _pending.pop(uid, None)


async def _do_word_count(cb, bot, fm, usage, docx_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("🔢")
    inp = None
    try:
        async with _semaphore:
            inp = fm.temp_path(".docx")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            wc = await docx_svc.word_count(inp)
            await cb.message.edit_text(
                f"🔢 Word Count\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📄 {data['file_name']}\n\n"
                f"📝 Words: {wc['words']}\n🔤 Characters: {wc['characters']}\n"
                f"🔤 No spaces: {wc['characters_no_space']}\n📃 Lines: {wc['lines']}\n"
                f"💬 Sentences: {wc['sentences']}\n📏 Avg word: {wc['avg_word_length']} chars")
            await usage.log(uid, "docx", "word_count", data["file_size"], "success")
    except Exception as e:
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        _pending.pop(uid, None)


async def _do_docx_images(cb, bot, fm, usage, docx_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text("⏳ Extracting images...")
    inp = out_dir = zip_path = None
    try:
        async with _semaphore:
            timer = Timer()
            inp = fm.temp_path(".docx")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out_dir = fm.temp_path("_docximgs")
            out_dir.mkdir(parents=True, exist_ok=True)
            with timer: paths = await docx_svc.extract_images(inp, out_dir)
            if not paths:
                await cb.message.edit_text("ℹ️ No images found.")
            elif len(paths) <= 10:
                sent = 0
                for p in paths:
                    try:
                        f = FSInputFile(path=str(p), filename=p.name)
                        await bot.send_document(chat_id=cb.message.chat.id, document=f)
                        sent += 1
                    except: pass
                await cb.message.edit_text(f"✅ {sent} image(s) ({timer.elapsed_ms}ms)")
            else:
                zip_path = fm.temp_path(".zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in paths: zf.write(p, p.name)
                f = FSInputFile(path=str(zip_path), filename=f"{Path(data['file_name']).stem}_images.zip")
                await bot.send_document(chat_id=cb.message.chat.id, document=f,
                    caption=f"✅ {len(paths)} images (zipped) ({timer.elapsed_ms}ms)")
                await cb.message.edit_text(f"✅ {len(paths)} images → ZIP ({timer.elapsed_ms}ms)")
            await usage.log(uid, "docx", "extract_images", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"DOCX images error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out_dir: fm.cleanup(out_dir)
        if zip_path: fm.cleanup(zip_path)
        _pending.pop(uid, None)


async def _do_docx_tables(cb, bot, fm, usage, docx_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳")
    await cb.message.edit_text("⏳ Extracting tables...")
    inp = out_dir = zip_path = None
    try:
        async with _semaphore:
            timer = Timer()
            inp = fm.temp_path(".docx")
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out_dir = fm.temp_path("_tables")
            out_dir.mkdir(parents=True, exist_ok=True)
            with timer: paths = await docx_svc.extract_tables_csv(inp, out_dir)
            if not paths:
                await cb.message.edit_text("ℹ️ No tables found.")
            elif len(paths) <= 10:
                sent = 0
                for p in paths:
                    try:
                        f = FSInputFile(path=str(p), filename=p.name)
                        await bot.send_document(chat_id=cb.message.chat.id, document=f)
                        sent += 1
                    except: pass
                await cb.message.edit_text(f"✅ {sent} table(s) as CSV ({timer.elapsed_ms}ms)")
            else:
                zip_path = fm.temp_path(".zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in paths: zf.write(p, p.name)
                f = FSInputFile(path=str(zip_path), filename=f"{Path(data['file_name']).stem}_tables.zip")
                await bot.send_document(chat_id=cb.message.chat.id, document=f,
                    caption=f"✅ {len(paths)} tables (zipped) ({timer.elapsed_ms}ms)")
                await cb.message.edit_text(f"✅ {len(paths)} tables → ZIP ({timer.elapsed_ms}ms)")
            await usage.log(uid, "docx", "extract_tables", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"DOCX tables error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp: fm.cleanup(inp)
        if out_dir: fm.cleanup(out_dir)
        if zip_path: fm.cleanup(zip_path)
        _pending.pop(uid, None)
