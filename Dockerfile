# ==================== Backend Dockerfile ====================
# Two stages: the compiler toolchain and pip's build artefacts stay in the builder, so the
# runtime image carries only the virtualenv and the system libraries the app loads.

# -------- Stage 1: build the virtualenv --------
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copied before the source so code edits reuse the cached dependency layer.
COPY requirements.txt .
# B3: camelot's opencv-python-headless and img2table's opencv-contrib-python-headless both write
# cv2/; reinstalling contrib last makes its complete cv2.ximgproc win (see requirements.in).
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps --force-reinstall opencv-contrib-python-headless==4.12.0.88 \
    && python -c "import cv2; assert hasattr(cv2.ximgproc, 'niBlackThreshold'), 'B3: non-contrib cv2 won'"

# -------- Stage 2: runtime --------
FROM python:3.11-slim

# tesseract + poppler are runtime dependencies of the OCR and PDF-to-image paths.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TESSERACT_PATH=/usr/bin/tesseract

# Unprivileged user: a compromised parser can't modify the code or the rest of the container.
RUN useradd --create-home --uid 1000 app

WORKDIR /app
COPY backend/app/ ./backend/app/

# Only the runtime-state directories are writable by the app. They must exist and be owned by
# `app` in the image: an empty named volume copies this ownership the first time it is mounted.
# They sit beside the package, not inside it, because the app resolves them against its CWD.
RUN mkdir -p backend/data backend/uploads backend/logs \
    && chown -R app:app backend/data backend/uploads backend/logs

USER app
# The CWD is what puts `app` on sys.path for uvicorn, and where data/, uploads/, logs/ resolve.
WORKDIR /app/backend

EXPOSE 8000

# Slim images have no curl. urlopen raises on connection errors and non-2xx responses.
# start-period covers the ~10 s of library imports before uvicorn listens (no network calls at
# startup since Day 9).
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=4)" "http://127.0.0.1:${PORT:-8000}/health" || exit 1

# sh -c expands Render's $PORT; exec replaces the shell so uvicorn is PID 1 and receives
# SIGTERM directly (graceful shutdown instead of a 10 s kill on `docker stop`).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
