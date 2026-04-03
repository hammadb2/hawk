# HAWK API — OS libs for WeasyPrint (PIPEDA PDF, monthly reports) + Python deps from requirements.txt
FROM python:3.13-slim-bookworm

# System WeasyPrint + Cairo/Pango stack (Railway). Python package also in requirements.txt.
RUN apt-get update && apt-get install -y --no-install-recommends \
    weasyprint \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fail the image build if the app cannot import (catches missing files/deps before deploy healthchecks).
RUN python -c "import main; print('main import ok')"

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Railway sets PORT; default 8000 for local.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
