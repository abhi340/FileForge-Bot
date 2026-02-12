# 🚀 FileForge-Bot

> **Transform Your Files Instantly** — A powerful Telegram bot for PDF manipulation, image editing, and document conversion

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python)](https://python.org)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.13+-green?style=flat-square&logo=telegram)](https://aiogram.dev)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)](https://github.com/abhi340/FileForge-Bot)

---

## ✨ Features

### 📄 PDF Operations
- ✂️ **Merge PDFs** — Combine multiple PDF files seamlessly
- 📑 **Split PDFs** — Extract specific pages or ranges
- 🔒 **Compress PDFs** — Reduce file size while maintaining quality
- 🎨 **Convert to Images** — Transform PDF pages to PNG/JPG
- 📝 **Extract Text** — Pull text content from PDF files
- 🔐 **Add Watermarks** — Protect your PDFs with custom watermarks

### 🖼️ Image Tools
- 🔄 **Resize & Scale** — Adjust dimensions easily
- 🔁 **Rotate & Flip** — Correct image orientation
- 🎯 **Crop Images** — Precise image trimming
- 💾 **Format Conversion** — Convert between PNG, JPG, WebP, etc.
- ✏️ **Add Text/Watermarks** — Customize images with overlays
- 📐 **Collage Creator** — Combine multiple images

### 📋 Document Processing
- 📄 **DOCX Editing** — Modify Word documents
- 🔄 **Format Conversion** — Convert between different document formats
- 📊 **Extract Content** — Pull text and metadata

### 🛡️ Admin Features
- 👑 **Admin Panel** — Full control and monitoring
- 📊 **User Statistics** — Track usage patterns
- 🔔 **Broadcast Messages** — Reach all users instantly
- ⚙️ **System Management** — Configure bot settings

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Framework** | Aiogram 3.13 (Telegram Bot API) |
| **Language** | Python 3.11+ |
| **PDF Processing** | PyMuPDF, pikepdf, pdfplumber |
| **Image Processing** | Pillow |
| **Document Handling** | python-docx |
| **Database** | LibSQL (Experimental) |
| **Async** | Aiohttp |
| **Configuration** | python-dotenv |

---

## 📦 Installation

### Prerequisites
- Python 3.11 or higher
- Git
- 2GB RAM (recommended)

### Quick Setup

```bash
# 1. Clone the repository
git clone https://github.com/abhi340/FileForge-Bot.git
cd FileForge-Bot

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
nano .env  # Add your BOT_TOKEN and other secrets

# 5. Run the bot
python -m app.main
```

### 🐳 Docker Setup (Optional)

```bash
docker build -t fileforge-bot .
docker run -d --env-file .env fileforge-bot
```

---

## ⚙️ Configuration

Create a `.env` file with the following variables:

```env
# Telegram Bot Token (from @BotFather)
BOT_TOKEN=your_telegram_bot_token_here

# Admin User ID
ADMIN_ID=your_user_id

# Database URL
DATABASE_URL=your_database_url

# API Keys (if needed)
API_KEY=optional_api_key
```

Get your `BOT_TOKEN` from [@BotFather](https://t.me/botfather) on Telegram.

---

## 📁 Project Structure

```
FileForge-Bot/
├── app/
│   ├── main.py              # Entry point
│   ├── bot.py               # Bot initialization
│   ├── config.py            # Configuration management
│   ├── database.py          # Database operations
│   ├── middleware.py        # Request middleware
│   ├── admin.py             # Admin commands
│   ├── file_router.py       # Main file handling routes
│   ├── file_manager.py      # File utilities
│   ├── pdf_service.py       # PDF operations
│   ├── image_service.py     # Image operations
│   └── docx_service.py      # Document operations
├── deploy.sh                # Oracle Cloud deployment script
├── requirements.txt         # Python dependencies
├── Procfile                 # Heroku deployment config
├── .env.example             # Environment template
└── README.md                # This file
```

---

## 🚀 Deployment

### Deploy to Oracle Cloud

```bash
# Run the deployment script
sudo bash deploy.sh
```

The script will:
- ✅ Update system packages
- 🔒 Configure UFW firewall
- 🛡️ Enable fail2ban
- 💾 Create 2GB swap space
- 🐍 Install Python 3.11
- 👤 Create dedicated bot user
- ⚙️ Set up systemd service

### Deploy to Heroku

```bash
heroku create your-app-name
git push heroku main
heroku config:set BOT_TOKEN=your_token
heroku ps:scale worker=1
```

---

## 🎮 Usage

### For Users

Simply send files to the bot:
1. **Send a PDF** → Get options to merge, split, compress, or convert
2. **Send an Image** → Resize, rotate, convert formats, add watermarks
3. **Send a Document** → Edit, convert, or extract content

### For Admins

```
/admin              # Access admin panel
/stats              # View user statistics
/broadcast <msg>    # Send message to all users
/ban <user_id>      # Ban a user
/unban <user_id>    # Unban a user
```

---

## 📊 Performance

- ⚡ **Async Processing** — Handle multiple requests simultaneously
- 💪 **Efficient Resource Usage** — Memory-optimized operations
- 🔄 **Queue Management** — Graceful request handling
- 📈 **Scalable Architecture** — Designed for growth

---

## 🐛 Troubleshooting

### Bot not responding?
```bash
# Check bot status
systemctl status filebot

# View logs
journalctl -u filebot -f
```

### Memory issues?
- Increase swap space: `sudo fallocate -l 4G /swapfile`
- Monitor with: `watch -n 1 free -h`

### PDF conversion failing?
- Ensure `libmupdf` is installed: `sudo apt install libmupdf-dev`

---

## 📝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙋 Support & Contact

- 💬 **Issues** — Report bugs on [GitHub Issues](https://github.com/abhi340/FileForge-Bot/issues)
- 📧 **Email** — Contact via GitHub profile
- 🌐 **Telegram** — Reach out directly on Telegram

---

## 🎉 Acknowledgments

- [Aiogram](https://aiogram.dev) — Telegram Bot API framework
- [PyMuPDF](https://pymupdf.io) — PDF manipulation
- [Pillow](https://python-pillow.org) — Image processing
- The open-source community

---

## 📈 Roadmap

- [ ] WebUI Dashboard
- [ ] Batch file processing
- [ ] Cloud storage integration (Google Drive, Dropbox)
- [ ] Advanced image editing (filters, effects)
- [ ] Multi-language support
- [ ] Premium tier features

---

**Made with ❤️ by [abhi340](https://github.com/abhi340)**

*Last Updated: 2026-02-12 15:54:33*