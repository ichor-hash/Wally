# Ethan API. CPU-only, models baked into the image so containers start offline.
#   docker build -t ethan-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    ETHAN_DATA_DIR=/data

WORKDIR /app

# CPU build of PyTorch first: the default wheel bundles CUDA and is ~10x larger
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

# Download the embedding model and reranker at build time, not on first request
ARG EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
ARG RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('${EMBED_MODEL}'); CrossEncoder('${RERANK_MODEL}')"
ENV HF_HUB_OFFLINE=1

COPY *.py ./
COPY prompts/ prompts/
COPY evals/ evals/

RUN useradd --create-home --uid 10001 ethan && mkdir -p /data && chown ethan /data
USER ethan
VOLUME ["/data"]
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=4)"

# One worker: models are loaded per process, and telemetry and the cache are in-process.
# Scale with more containers behind a load balancer, not more workers (docs/HOSTING.md).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--forwarded-allow-ips=*"]
