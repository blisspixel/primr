# Production Dockerfile for Primr Job Runner
#
# Multi-stage build:
# - Stage 1 (builder): Build wheel from source
# - Stage 2 (runtime): Install wheel in minimal runtime image
#
# Security:
# - Non-root user (primr, uid 1000)
# - Minimal runtime image (python:3.11-slim)
#
# Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9

# =============================================================================
# Stage 1: Builder - Build wheel from source
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir build wheel setuptools

# Copy project files needed for building
COPY pyproject.toml .
COPY MANIFEST.in .
COPY README.md .
COPY src/ src/

# Build the wheel
RUN python -m build --wheel --outdir /build/dist

# =============================================================================
# Stage 2: Runtime - Install wheel in minimal image
# =============================================================================
FROM python:3.11-slim

# Create non-root user (primr, uid 1000)
# Requirements: 1.4 (non-root execution)
RUN useradd -m -s /bin/bash -u 1000 primr

WORKDIR /app

# Install system dependencies for primr
# - tesseract-ocr: for OCR functionality
# - libmagic1: for file type detection
# - curl: for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheel from builder stage
COPY --from=builder /build/dist/*.whl /app/

# Install the wheel and its dependencies
RUN pip install --no-cache-dir /app/*.whl && rm /app/*.whl

# Install runner wrapper and manifest module
COPY deploy/runner.py /app/runner.py
COPY deploy/manifest.py /app/manifest.py
COPY deploy/storage.py /app/storage.py
COPY deploy/__init__.py /app/deploy/__init__.py

# Create deploy package structure for imports
RUN mkdir -p /app/deploy && \
    cp /app/runner.py /app/deploy/runner.py && \
    cp /app/manifest.py /app/deploy/manifest.py && \
    cp /app/storage.py /app/deploy/storage.py && \
    cp /app/deploy/__init__.py /app/deploy/__init__.py

# Create directories for job artifacts and logs
RUN mkdir -p /job /app/_logs && \
    chown -R primr:primr /app /job

# Switch to non-root user
# Requirements: 1.4 (non-root execution)
USER primr

# Environment variables
# - PYTHONUNBUFFERED: Ensure logs are written immediately
# - PYTHONDONTWRITEBYTECODE: Don't create .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check (optional, for container orchestration)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import primr; print('healthy')" || exit 1

# Runner reads JOB_SPEC from env or file, executes primr, writes to ARTIFACT_STORE
# Requirements: 1.1 (job spec via JSON/env), 1.8 (exit codes), 1.12 (non-interactive)
ENTRYPOINT ["python", "/app/runner.py"]
