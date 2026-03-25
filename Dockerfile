# Use Python 3.12 slim image as base (pinned digest for stable build cache)
FROM python:3.12-slim@sha256:9e01bf1ae5db7649a236da7be1e94ffbbbdd7a93f867dd0d8d5720d9e1f89fab

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# PyTorch variant: "cpu" (default, ~500MB) or "cu124"/"cu126" for CUDA (~5GB)
# Override with: docker compose build --build-arg TORCH_VARIANT=cu124
ARG TORCH_VARIANT=cpu

# Install PyTorch separately so this layer is cached when requirements.txt changes
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/${TORCH_VARIANT}

# Copy requirements file and install the rest of the dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the SentenceTransformer model into /app/.cache so it's accessible
# to the non-root appuser (who owns /app but not /root)
ENV HF_HOME=/app/.cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY domain/ ./domain/
COPY application/ ./application/
COPY infrastructure/ ./infrastructure/
COPY presentation/ ./presentation/
COPY config/ ./config/

# Create data directory (not in source control)
RUN mkdir -p data

EXPOSE 5678

# Application version (set at build time by CI)
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=presentation.web.app

# Run as non-root user
RUN useradd --create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

# Run the application with Gunicorn from project root
WORKDIR /app
CMD ["gunicorn", "--bind", "0.0.0.0:5678", "--workers", "4", "--timeout", "120", "presentation.web.app:app"]
