# ─── Builder stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ─── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/

# Non-root user setup and persistent data directory creation with correct ownership
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser && \
    mkdir -p /data/faiss_index /data/logs && \
    chown -R appuser:appgroup /data

USER appuser

# Persistent volume mounts
VOLUME ["/data/faiss_index", "/data/logs"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]