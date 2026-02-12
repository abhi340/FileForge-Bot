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
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")],
        ],
        "docx": [
            [InlineKeyboardButton(text="🧹 Remove Metadata", callback_data="docx_meta")],
            [InlineKeyboardButton(text="💬 Remove Comments", callback_data="docx_comments")],
            [InlineKeyboardButton(text="📝 Extract Text", callback_data="docx_text")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")],
        ],
    }
    return InlineKeyboardMarkup(
        inline_keyboard=buttons.get(category, [
            [InlineKeyboardButton(text="❌ Unsupported", callback_data="cancel")]
        ])
    )


# Store for custom resize waiting
_waiting_resize = {}


def register_file_handlers(rt, config, fm, usage, bot):
    img = ImageService()
    pdf = PDFService()
    docx = DOCXService()

    @rt.message(F.photo)
    async def on_photo(message: Message):
        user_id = message.from_user.id

        # Check if waiting for custom resize input
        if user_id in _waiting_resize:
            return

        photo = message.photo[-1]
        if photo.file_size and photo.file_size > config.max_file_size_bytes:
            max_mb = config.max_file_size_mb
            actual = round(photo.file_size / (1024 * 1024), 2)
            await message.reply(f"❌ Photo too large: {actual}MB (max {max_mb}MB)")
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
            f"🖼 Photo received!\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Size: {size_str}\n"
            f"⚠️ Tip: Send as File for full quality\n\n"
            f"Choose operation:",
            reply_markup=_keyboard("image"),
        )

    @rt.message(F.document)
    async def on_file(message: Message):
        doc = message.document
        user_id = message.from_user.id

        if doc.file_size and doc.file_size > config.max_file_size_bytes:
            max_mb = config.max_file_size_mb
            actual = round(doc.file_size / (1024 * 1024), 2)
            await message.reply(f"❌ File too large: {actual}MB (max {max_mb}MB)")
            return

        category = detect_category(doc.mime_type)
        if not category:
            await message.reply(f"❌ Unsupported type: {doc.mime_type}\nSupported: image, pdf, docx")
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

    # Handle custom resize text input
    @rt.message(F.text)
    async def on_text(message: Message):
        user_id = message.from_user.id
        if user_id not in _waiting_resize:
            return

        text = message.text.strip()
        data = _waiting_resize.pop(user_id)

        # Parse input: "50" or "800x600"
        try:
            if "x" in text.lower():
                parts = text.lower().split("x")
                width = int(parts[0].strip())
                height = int(parts[1].strip())
                if width < 1 or height < 1 or width > 10000 or height > 10000:
                    await message.reply("❌ Dimensions must be 1-10000. Try again.")
                    return
                # Exact resize
                await _do_custom_resize_exact(message, bot, config, fm, usage, data, width, height)
            else:
                pct = int(text)
                if pct < 1 or pct > 500:
                    await message.reply("❌ Percentage must be 1-500. Try again.")
                    return
                await _do_custom_resize_pct(message, bot, config, fm, usage, data, pct)
        except ValueError:
            await message.reply("❌ Invalid format. Use '50' for 50% or '800x600' for exact size.")

    @rt.callback_query(F.data == "cancel")
    async def on_cancel(cb: CallbackQuery):
        _pending.pop(cb.from_user.id, None)
        _waiting_resize.pop(cb.from_user.id, None)
        await cb.message.edit_text("❌ Cancelled.")
        await cb.answer()

    # ── Original handlers ──
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

    # ── New handlers ──

    # Custom resize
    @rt.callback_query(F.data == "img_rcustom")
    async def h_rcustom(cb: CallbackQuery):
        uid = cb.from_user.id
        data = _pending.get(uid)
        if not data:
            await cb.answer("❌ No file pending.", show_alert=True)
            return
        _waiting_resize[uid] = data
        await cb.message.edit_text(
            "📐 Custom Resize\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send me one of these:\n\n"
            "• A number for percentage: 75\n"
            "• Exact dimensions: 800x600\n\n"
            "Type and send:"
        )
        await cb.answer()

    # Compress
    @rt.callback_query(F.data == "img_comp_low")
    async def h_cl(cb: CallbackQuery):
        await _do_compress(cb, bot, config, fm, usage, img, "low")

    @rt.callback_query(F.data == "img_comp_med")
    async def h_cm(cb: CallbackQuery):
        await _do_compress(cb, bot, config, fm, usage, img, "medium")

    @rt.callback_query(F.data == "img_comp_high")
    async def h_ch(cb: CallbackQuery):
        await _do_compress(cb, bot, config, fm, usage, img, "high")

    # Grayscale
    @rt.callback_query(F.data == "img_gray")
    async def h_gray(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "grayscale",
                  lambda i, o: img.grayscale(i, o))

    # Info
    @rt.callback_query(F.data == "img_info")
    async def h_info(cb: CallbackQuery):
        await _do_info(cb, bot, fm, usage, img)

    # Blur
    @rt.callback_query(F.data == "img_blur_light")
    async def h_bl(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "blur_light",
                  lambda i, o: img.blur(i, o, "light"))

    @rt.callback_query(F.data == "img_blur_med")
    async def h_bm(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "blur_medium",
                  lambda i, o: img.blur(i, o, "medium"))

    @rt.callback_query(F.data == "img_blur_heavy")
    async def h_bh(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "blur_heavy",
                  lambda i, o: img.blur(i, o, "heavy"))

    # Upscale
    @rt.callback_query(F.data == "img_up2")
    async def h_u2(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "upscale_2x",
                  lambda i, o: img.upscale(i, o, 2))

    @rt.callback_query(F.data == "img_up4")
    async def h_u4(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "upscale_4x",
                  lambda i, o: img.upscale(i, o, 4))

    # Image to PDF
    @rt.callback_query(F.data == "img_pdf")
    async def h_pdf(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "to_pdf",
                  lambda i, o: img.to_pdf(i, o), out_ext=".pdf")

    # Screenshot cleaner
    @rt.callback_query(F.data == "img_screenshot")
    async def h_ss(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "clean_screenshot",
                  lambda i, o: img.clean_screenshot(i, o))

    # ID Photos
    @rt.callback_query(F.data == "img_id_passport")
    async def h_idp(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "id_passport",
                  lambda i, o: img.id_photo(i, o, "passport"), out_ext=".jpg")

    @rt.callback_query(F.data == "img_id_visa")
    async def h_idv(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "id_visa",
                  lambda i, o: img.id_photo(i, o, "visa"), out_ext=".jpg")

    @rt.callback_query(F.data == "img_id_stamp")
    async def h_ids(cb: CallbackQuery):
        await _do(cb, bot, config, fm, usage, "image", "id_stamp",
                  lambda i, o: img.id_photo(i, o, "stamp"), out_ext=".jpg")

    # ── PDF handlers ──
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

    # ── DOCX handlers ──
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


# ── Processing Functions ──

async def _do(cb, bot, config, fm, usage, ftype, tool, process_fn, out_ext=""):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending. Upload again.", show_alert=True)
        return
    await cb.answer("⏳ Processing...")
    await cb.message.edit_text(f"⏳ Processing {tool}...")
    inp = None
    out = None
    try:
        async with _semaphore:
            timer = Timer()
            name = data["file_name"]
            in_ext = Path(name).suffix if name else ".jpg"
            if not out_ext:
                out_ext = in_ext
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(out_ext)
            with timer:
                result = await process_fn(inp, out)
            out_name = f"{Path(name).stem}_{tool}{out_ext}"
            doc = FSInputFile(path=str(out), filename=out_name)
            await bot.send_document(
                chat_id=cb.message.chat.id,
                document=doc,
                caption=f"✅ {tool} done ({timer.elapsed_ms}ms)",
            )
            await usage.log(uid, ftype, tool, data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"✅ {tool} done! ({timer.elapsed_ms}ms)")
    except Exception as e:
        logger.error(f"Process error ({tool}): {e}", exc_info=True)
        await usage.log(uid, ftype, tool, data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        if out:
            fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_compress(cb, bot, config, fm, usage, img_svc, level):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳ Compressing...")
    await cb.message.edit_text(f"⏳ Compressing ({level})...")
    inp = None
    out = None
    try:
        async with _semaphore:
            timer = Timer()
            name = data["file_name"]
            in_ext = Path(name).suffix if name else ".jpg"
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            out = fm.temp_path(".jpg")
            with timer:
                _, orig, new, saved = await img_svc.compress(inp, out, level)
            out_name = f"{Path(name).stem}_compressed.jpg"
            doc = FSInputFile(path=str(out), filename=out_name)
            await bot.send_document(
                chat_id=cb.message.chat.id,
                document=doc,
                caption=(
                    f"✅ Compressed ({level})\n"
                    f"📦 {format_size(orig)} → {format_size(new)}\n"
                    f"💾 Saved: {saved}%\n"
                    f"⏱ {timer.elapsed_ms}ms"
                ),
            )
            await usage.log(uid, "image", f"compress_{level}", data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"✅ Compressed! Saved {saved}% ({timer.elapsed_ms}ms)")
    except Exception as e:
        logger.error(f"Compress error: {e}", exc_info=True)
        await usage.log(uid, "image", f"compress_{level}", data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        if out:
            fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_info(cb, bot, fm, usage, img_svc):
    uid = cb.from_user.id
    data = _pending.get(uid)
    if not data:
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("🔍 Analyzing...")
    inp = None
    try:
        async with _semaphore:
            name = data["file_name"]
            in_ext = Path(name).suffix if name else ".jpg"
            inp = fm.temp_path(in_ext)
            tg_file = await bot.get_file(data["file_id"])
            await bot.download_file(tg_file.file_path, destination=str(inp))
            info = await img_svc.get_info(inp)

            gps_warning = "⚠️ YES — GPS location found!" if info["has_gps"] else "✅ No"

            text = (
                f"📏 Image Info\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📄 Name: {name}\n"
                f"🖼 Format: {info['format']}\n"
                f"📐 Size: {info['width']} x {info['height']}\n"
                f"📊 Megapixels: {info['megapixels']}\n"
                f"📦 File size: {format_size(info['size_bytes'])}\n"
                f"🎨 Color mode: {info['mode']}\n"
                f"📏 DPI: {info['dpi']}\n"
                f"📷 Camera: {info['camera']}\n"
                f"🏷 EXIF fields: {info['exif_fields']}\n"
                f"📍 GPS data: {gps_warning}"
            )

            await cb.message.edit_text(text)
            await usage.log(uid, "image", "info", data["file_size"], "success")
    except Exception as e:
        logger.error(f"Info error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        _pending.pop(uid, None)


async def _do_custom_resize_pct(message, bot, config, fm, usage, data, pct):
    uid = message.from_user.id
    inp = None
    out = None
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
            with timer:
                await img_svc.resize(inp, out, pct)
            out_name = f"{Path(name).stem}_resize_{pct}pct{in_ext}"
            doc = FSInputFile(path=str(out), filename=out_name)
            await bot.send_document(
                chat_id=message.chat.id,
                document=doc,
                caption=f"✅ Resized to {pct}% ({timer.elapsed_ms}ms)",
            )
            await usage.log(uid, "image", f"resize_{pct}", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"Custom resize error: {e}", exc_info=True)
        await message.reply(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        if out:
            fm.cleanup(out)
        _pending.pop(uid, None)


async def _do_custom_resize_exact(message, bot, config, fm, usage, data, width, height):
    uid = message.from_user.id
    inp = None
    out = None
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
            with timer:
                await img_svc.resize_exact(inp, out, width, height)
            out_name = f"{Path(name).stem}_{width}x{height}{in_ext}"
            doc = FSInputFile(path=str(out), filename=out_name)
            await bot.send_document(
                chat_id=message.chat.id,
                document=doc,
                caption=f"✅ Resized to {width}x{height} ({timer.elapsed_ms}ms)",
            )
            await usage.log(uid, "image", f"resize_{width}x{height}", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"Exact resize error: {e}", exc_info=True)
        await message.reply(f"❌ Error: {str(e)[:200]}")
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
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳ Extracting...")
    await cb.message.edit_text("⏳ Extracting text...")
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
                    text=f"📝 Extracted Text:\n\n{text[:3900]}",
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
                    caption=f"📝 {len(text)} characters extracted",
                )
            await usage.log(uid, ftype, tool, data["file_size"], "success", "", timer.elapsed_ms)
            await cb.message.edit_text(f"✅ Text extracted ({timer.elapsed_ms}ms)")
    except Exception as e:
        logger.error(f"Text extract error: {e}", exc_info=True)
        await usage.log(uid, ftype, tool, data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
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
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳ Extracting images...")
    await cb.message.edit_text("⏳ Extracting images...")
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
                await cb.message.edit_text("ℹ️ No images found in PDF.")
            else:
                sent = 0
                for ip in img_paths[:10]:
                    try:
                        f = FSInputFile(path=str(ip), filename=ip.name)
                        await bot.send_document(chat_id=cb.message.chat.id, document=f)
                        sent += 1
                    except Exception as e:
                        logger.warning(f"Send image failed: {e}")
                await cb.message.edit_text(f"✅ {sent} image(s) extracted ({timer.elapsed_ms}ms)")
            await usage.log(uid, "pdf", "extract_images", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"Image extract error: {e}", exc_info=True)
        await usage.log(uid, "pdf", "extract_images", data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
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
        await cb.answer("❌ No file pending.", show_alert=True)
        return
    await cb.answer("⏳ Splitting...")
    await cb.message.edit_text("⏳ Splitting pages...")
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
            await cb.message.edit_text(f"✅ Split into {sent} page(s) ({timer.elapsed_ms}ms)")
            await usage.log(uid, "pdf", "split_pages", data["file_size"], "success", "", timer.elapsed_ms)
    except Exception as e:
        logger.error(f"Split error: {e}", exc_info=True)
        await usage.log(uid, "pdf", "split_pages", data.get("file_size", 0), "failure", str(e)[:200])
        await cb.message.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        if inp:
            fm.cleanup(inp)
        if out_dir:
            fm.cleanup(out_dir)
        _pending.pop(uid, None)
