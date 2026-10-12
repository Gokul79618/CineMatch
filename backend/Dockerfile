# CineMatch AI — FastAPI Backend
# Multi-stage build with CPU-only PyTorch and pre-built local RAG index.

FROM python:3.10-slim AS builder

WORKDIR /build

# Install build-time system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only PyTorch first to avoid multi-GB CUDA wheels in production
RUN pip install --no-cache-dir --prefix=/install \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.10-slim

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Configure deterministic local model cache path and pinned embedding revision
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    RAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 \
    RAG_EMBEDDING_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
    PORT=10000

# Copy application code, seed data, and SQL scripts
COPY app/ ./app/
COPY data/movies.json ./data/movies.json
COPY data/rag_documents.json ./data/rag_documents.json
COPY data/rag_golden_set.json ./data/rag_golden_set.json
COPY sql/ ./sql/

# Pre-download the pinned embedding model and build data/rag_index.json
# so runtime retrieval (local_files_only=True) succeeds without network calls.
RUN python -m app.rag.ingest

# Create non-root runtime user and grant access to data and model cache
RUN groupadd -r cinematch && \
    useradd -r -g cinematch -d /app cinematch && \
    chown -R cinematch:cinematch /app

USER cinematch

EXPOSE ${PORT}

# Start Uvicorn. Single worker keeps memory footprint bounded for sentence-transformers.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 5 --limit-concurrency 50"]
