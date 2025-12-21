# ==================== Backend Dockerfile ====================
# Use Python 3.9 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY src/ ./src/


# Create necessary directories
RUN mkdir -p src/data/uploads src/data/faiss_indexes src/logs

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TESSERACT_PATH=/usr/bin/tesseract

# Change to src directory and run uvicorn
WORKDIR /app/src
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
