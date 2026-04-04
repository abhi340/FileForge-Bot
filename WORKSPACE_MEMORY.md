# Workspace Memory - FileForge-Bot

## Project Overview
A modular Telegram bot for file manipulation (PDF, Image, DOCX) built with `aiogram`.

## Key Architectural Changes (March 2026)
- **Database**: Switched from strict `libsql-experimental` to a "Smart" database handler in `app/database.py`. It uses `sqlite3` by default for local development (no Rust required) and connects to **Turso** if `TURSO_URL` and `TURSO_TOKEN` are provided in the environment.
- **PDF Service**: Migrated from `pikepdf` to `pypdf` in `app/pdf_service.py` to remove the dependency on Microsoft C++ Build Tools during installation.
- **Bot Initialization**: Fixed `NameError` in `app/bot.py` regarding router registration.

## Deployment Details (Koyeb)
- **Method**: Dockerfile (Buildpack alternative avoided for better control over system dependencies like LibreOffice and Tesseract).
- **Port**: Defaulted to **8000** (updated in `app/config.py` and `app/main.py`) to match Koyeb's default health check.
- **Base Image**: `python:3.11-slim`.

## Required Environment Variables
| Variable | Description |
| :--- | :--- |
| `BOT_TOKEN` | Telegram Bot Token from @BotFather |
| `ADMIN_ID` | Numeric Telegram ID of the admin |
| `PORT` | Set to `8000` for Koyeb |
| `TURSO_URL` | Turso database URL (e.g., `libsql://...`) |
| `TURSO_TOKEN` | Turso Auth Token |

## Local Execution
Use Python 3.13+ for best results:
```bash
py -3.13 -m app.main
```
