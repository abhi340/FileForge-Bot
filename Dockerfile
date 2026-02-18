FROM python:3.11-slim

# 1. Install LibreOffice, Fonts, and Tesseract OCR
RUN apt-get update && \
    echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections && \
    apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-calc \
    fonts-liberation \
    ttf-mscorefonts-installer \
    fontconfig \
    tesseract-ocr \
    && fc-cache -f -v \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data tmp

CMD ["python", "-m", "app.main"]
