# Hosting Ethan

Ethan has three parts:

- **Web app**: Next.js, static after build.
- **API**: FastAPI, with two small local models in memory.
- **Vector store**: Qdrant.

They can run on one laptop, one server, or three managed services. Pick the row that matches your situation, then follow its section.

| Option | Good for | Docker? | Data leaves your machines? | Running cost |
|---|---|---|---|---|
| [1. Laptop, embedded Qdrant](#option-1-laptop-no-docker) | Development, demos | No | Only the question and 5 chunks, to the LLM | $0 + LLM |
| [2. One server, Docker Compose](#option-2-one-server-with-docker-compose) | A team, internal tool | Yes | Same as above | One small VM + LLM |
| [3. Managed services](#option-3-managed-services) | No servers to look after | No | Documents stored with Qdrant Cloud | Free tiers to low tens of dollars + LLM |
| [4. Kubernetes / cloud containers](#option-4-kubernetes-or-cloud-containers) | Many users, uptime targets | Yes | Your cloud account | Per cluster |
| [5. Fully private, local model](#option-5-fully-private-local-model) | Confidential documents | Optional | **Nothing** | Hardware only |

## What the API needs

Measured on the demo index:

| | |
|---|---|
| Memory | About 1.5 GB committed, 220 MB resident when idle. **Allocate 2 GB.** |
| CPU | Any modern x86 or ARM. No GPU. Reranking 15 candidates takes about 0.25 s on a laptop CPU. |
| Disk | About 175 MB for the two models. The index is about 1 MB per 230 chunks. |
| Python | 3.11 or 3.12 |

Install PyTorch's CPU build before the requirements. The default Linux wheel bundles CUDA and is roughly ten times larger:

```bash
pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

## Option 1: laptop, no Docker

Qdrant can run **inside the API process**, storing its index in a folder. Nothing else to install or start.

```env
# .env
QDRANT_PATH=./ethan_data/qdrant
```

```bash
python -m uvicorn main:app --port 8001
cd ethan-frontend && npm run dev
```

Embedded Qdrant allows one process at a time, so run a single API worker. That suits a laptop and a small team; move to a Qdrant server (options 2 to 4) when you need several API processes. The API reports which mode it is in under **Settings → System → Vector database**.

## Option 2: one server with Docker Compose

`docker-compose.yml` runs Qdrant, the API and the web app on one machine. Qdrant is reachable only from the API.

```bash
cp .env.example .env               # add GROQ_API_KEY and COMPANY_NAME
docker compose up -d --build
```

Open `http://<server>:3000`. The API image is CPU-only, has both models baked in (it starts offline, with no download on first request), runs as a non-root user and has a health check.

When the web app and API are on a public address, set both variables before building:

```env
PUBLIC_API_URL=https://api.example.com      # baked into the web app at build time
CORS_ORIGINS=https://ethan.example.com      # the only origin allowed to call the API
```

Then put a reverse proxy in front for HTTPS (Caddy is two lines per site; nginx or Traefik also work). Use a VM with at least 4 GB of memory, so the API, Qdrant, the web app and the OS each have room. For the Compose files to work as written, Docker Desktop must be running on Windows and macOS.

## Option 3: managed services

| Part | Service | Notes |
|---|---|---|
| Web app | Vercel, Netlify, Cloudflare Pages | Root directory `ethan-frontend`. Set `NEXT_PUBLIC_API_BASE` to the API URL. |
| API | Railway, Render, Fly.io, Google Cloud Run, AWS App Runner | Deploy the root `Dockerfile`. Give it 2 GB of memory and keep **at least one instance warm**: loading the models takes several seconds, which a scale-to-zero cold start would add to the first question. |
| Vector store | Qdrant Cloud | Set `QDRANT_URL` and `QDRANT_API_KEY`. A free cluster holds the demo many times over. |
| Data volume | The host's persistent disk | Mount it at `/data` for knowledge gaps, feedback, cost totals and the query log. Without it they reset on each deploy. |

The API is a long-running process holding models in memory, so it fits a container host better than per-request serverless functions. If you do run it serverless, expect the model load on every cold start.

## Option 4: Kubernetes or cloud containers

Use the same two images. To scale the API horizontally:

- **Vector store:** a Qdrant server or Qdrant Cloud. Embedded mode is single-process.
- **State:** the API keeps telemetry, the answer cache and rate-limit windows in process, and persists gaps and totals to a local folder. With several replicas, each has its own. That is fine for the cache and rate limits (each replica limits its own share). For shared knowledge-gap and cost dashboards, move `telemetry.py`'s storage to Postgres or Redis; it is one class.
- **Probes:** use `GET /health` for readiness. It returns `degraded` when Qdrant is unreachable.
- **Workers:** scale with replicas, not uvicorn workers. Each worker loads its own copy of both models.

## Option 5: fully private, local model

Point Ethan at any server that speaks the OpenAI chat-completions API. With [Ollama](https://ollama.com):

```bash
ollama pull qwen3:8b                 # or another instruction model that fits your hardware
```

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:8b
LLM_PRICE_INPUT_PER_M=0
LLM_PRICE_OUTPUT_PER_M=0
```

LM Studio (`http://localhost:1234/v1`), vLLM and llama.cpp's server work the same way. With embeddings and reranking already local, **no text leaves your network**.

Before switching, run `python evals/run_evals.py --answers` with the local model. Small models follow citation and refusal instructions less reliably, and the answer evaluation will show you where.

## Before you expose it to a network

The API has **no authentication of its own**. Anyone who can reach it can read, upload and delete documents. Before it leaves a laptop:

1. **Put it behind your identity provider.** Use a proxy that enforces SSO, such as oauth2-proxy, Cloudflare Access or Tailscale, or your platform's built-in protection. Or keep it on a private network.
2. **Set `CORS_ORIGINS`** to the web app's exact origin.
3. **Leave `ALLOW_DIRECTORY_INGEST` off.** It defaults to off. When enabled, it lets a caller read any folder on the server's disk.
4. **Keep `INNGEST_ENABLED` off** unless you use it. With `INNGEST_PRODUCTION=true`, also set Inngest's signing key.
5. **Rate limiting** keys on the client IP. Behind a proxy the API trusts the first `X-Forwarded-For` address, so make sure your proxy sets that header and strips any value sent by the client.
6. **Back up** the Qdrant volume and `ethan_data/`. Re-uploading the documents rebuilds the index; feedback and gaps exist only in `ethan_data/`.

## Upgrading from v2

v3 stores a BM25 vector next to each dense vector, in a new collection named `ethan_docs`. Your v2 collection (`docs`) is left untouched. Either re-upload your documents, which also gives you structure-aware chunks, or copy the existing chunks across:

```bash
python scripts/migrate_collection.py --source docs --target ethan_docs
```

If you point v3 at an old collection without migrating, it keeps working dense-only and says so in Settings.
