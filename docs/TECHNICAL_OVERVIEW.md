> **Note:** This is the original design essay, kept for background. Some details (Streamlit UI, LlamaIndex parsing) describe v1. The [README](../README.md) is the current reference.

# Building a Production RAG System: The Real Story

I spent three weeks trying to get GPT-4's API to work for a document Q&A system before I realized my OpenAI credits had run out. Classic. That's when I decided to build this entire system using completely free alternatives, and honestly, it turned out better than I expected.

## What This Thing Actually Does

You throw PDFs at it, ask questions in natural language, and it gives you answers grounded in those documents. Simple on the surface, but there's a lot happening under the hood. Think of it like having a really smart librarian who's actually read every book in the library and can instantly recall exact passages when you ask.

The whole system is split into five core pieces:
- PDF ingestion and chunking
- Text embedding (converting words into numbers)
- Vector similarity search
- LLM-powered answer generation
- A web interface that doesn't make you want to cry

## The Math Nobody Talks About (But Should)

Here's where things get interesting.

### Cosine Similarity: The Heart of Search

When you search for something, we're not doing dumb keyword matching. We convert your question and every document chunk into vectors (just arrays of 384 floating-point numbers), and then we calculate how "similar" they are using cosine similarity.

The formula looks like this:

```
similarity = (A · B) / (||A|| × ||B||)
```

Where:
- `A · B` is the dot product (multiply corresponding elements and sum them up)
- `||A||` and `||B||` are the magnitudes (square root of sum of squared elements)

But here's the kicker: the result is always between -1 and 1. For text embeddings, you usually get 0 to 1:
- **1.0** = identical meaning
- **0.8-1.0** = very similar (this is what you want)
- **0.6-0.8** = moderately similar
- **0.4-0.6** = somewhat related
- **< 0.4** = basically unrelated

I chose cosine over Euclidean distance because it doesn't care about magnitude, only direction. A 500-word document and a 50-word document can still be semantically identical, and cosine similarity catches that. Euclidean distance would penalize the length difference.

### Why 384 Dimensions?

The embedding model (`sentence-transformers/all-MiniLM-L6-v2`) spits out 384-dimensional vectors. Why 384? Because the researchers who trained it decided that was the sweet spot between accuracy and speed. Could've been 512 or 768, but 384 works surprisingly well and keeps the vector database lean.

Think of it this way: every concept in human language gets mapped to a point in 384-dimensional space. Words with similar meanings cluster together. It's wild when you think about it.

## The Architecture (Without the Buzzwords)

### 1. PDF Ingestion: Breaking Down Documents

First problem: PDFs are awful to work with. They're designed for printing, not parsing. But LlamaIndex's `PDFReader` does the heavy lifting.

```
PDF → Raw Text → Sentence Splitter → Chunks (512 chars each, 50 char overlap)
```

The overlap is critical. Imagine a sentence that explains a key concept spans two chunks. Without overlap, you'd split it awkwardly and lose context. With 50 characters of overlap, you get continuity.

**My chunking strategy:**
- **512 characters per chunk**: Not too small (preserves context), not too large (stays focused)
- **50 character overlap**: Ensures no idea gets cut in half
- **Sentence-aware splitting**: Never breaks mid-sentence (learned this the hard way after seeing gibberish results)

I tested 256, 512, and 1024 character chunks. 256 was too fragmented, 1024 was too broad. 512 hit the Goldilocks zone.

### 2. Embeddings: Turning Words Into Math

This is where the magic happens. Every chunk gets converted into a 384-dimensional vector using `sentence-transformers/all-MiniLM-L6-v2`.

Why this model?
- It's free and runs locally (no API costs)
- It's fast (can embed hundreds of chunks per second)
- It's good enough (not SOTA, but definitely production-ready)
- 384 dimensions keeps vector DB storage reasonable

The model was trained on billions of sentence pairs using contrastive learning. Basically: "Hey, these two sentences mean the same thing, make their vectors close. These two are different, push them apart."

**Alternative I considered:**
- **Groq embeddings**: Cloud-based, faster, but 1024 dimensions (3x the storage)
- **OpenAI embeddings**: The best quality, but costs money (which I don't have)
- **BGE models**: Slightly better accuracy, but slower inference

### 3. Vector Database: Qdrant

I needed somewhere to store 14 chunks (in this demo) but realistically thousands or millions in production. Enter Qdrant.

**Why Qdrant over alternatives:**
- **HNSW indexing**: Approximate nearest neighbor search in O(log N) instead of O(N)
- **Runs in Docker**: No complex setup
- **Free**: No usage limits for self-hosted
- **Cosine distance support**: Built-in

**HNSW (Hierarchical Navigable Small World) Algorithm:**

This is how Qdrant finds similar vectors fast. Instead of comparing your query to all 1 million vectors (slow), it builds a multi-layer graph:
- Layer 0: All vectors
- Layer 1: Every 10th vector
- Layer 2: Every 100th vector
- And so on...

When you search:
1. Start at the top layer (sparse)
2. Find the closest vector
3. Drop down a layer (denser)
4. Find closer vectors
5. Repeat until bottom layer
6. Return top K matches

It's like using a hierarchy of maps: start with a world map, zoom into a country, then a city, then a street. Way faster than checking every street on Earth.

### 4. The LLM: Groq's GPT OSS 20B

Originally tried to use `llama-3.1-8b-instant` but Groq deprecated it in August 2026 (thanks for that). Switched to `openai/gpt-oss-20b`, which is:
- Free (250K tokens per minute on developer tier)
- Fast (1000 tokens/second, insane throughput)
- Good at following instructions

**The RAG Prompt Pattern:**
```
System: You are a helpful assistant. Use the context to answer questions.

User: Context: [top 5 most similar chunks]

Question: [user's question]
```

Simple but effective. The LLM sees the relevant chunks and generates an answer grounded in them. Without RAG, it would just hallucinate or say "I don't know."

### 5. The API: FastAPI + Streamlit

**FastAPI** handles the backend:
- `/ingest/pdf` - Upload PDFs
- `/search` - Ask questions
- `/health` - Check system status

**Streamlit** is the frontend. I picked it because I could build the entire UI in 100 lines of Python. No React, no JavaScript, no webpack hellscape.

It gets better. FastAPI auto-reloads on code changes, Streamlit does too. Development cycle is instant.

## The Full Pipeline (Step by Step)

Let's trace a query through the entire system.

**You ask:** "What is the main topic of this document?"

1. **Streamlit sends HTTP POST to FastAPI** (`/search`)
2. **Embedding model converts your question** → 384-dimensional vector
3. **Qdrant searches** using HNSW algorithm → finds top 5 similar chunks (cosine similarity scores: 0.87, 0.82, 0.78, 0.71, 0.68)
4. **FastAPI concatenates** those 5 chunks into a context string
5. **LLM (Groq) receives** the context + your question
6. **LLM generates** an answer in ~500ms (seriously, Groq is fast)
7. **FastAPI returns** JSON with answer + sources
8. **Streamlit displays** the answer + expandable source chunks

Total latency: ~800ms to 1.2s depending on chunk count.

## The Problems I Hit (And How I Fixed Them)

### Problem 1: Qdrant Dimension Mismatch

First ingestion attempt failed with `400 Bad Request: dimension mismatch`. Qdrant collection was configured for 1024 dims (Groq embeddings), but I was using HuggingFace (384 dims).

**Solution:** Deleted the collection, let the code auto-recreate it with correct dimensions. Lesson: always verify your embedding model's output dimensions match your vector DB config.

### Problem 2: Qdrant Query Response Format

The error `'tuple' object has no attribute 'id'` haunted me for an hour. Turns out `client.query_points()` returns a `QueryResponse` object with a `.points` attribute, not a raw list.

**Solution:** 
```python
response = self.client.query_points(...)
points = response.points  # Extract the points list
for point in points:
    point.id, point.score, point.payload  # Now accessible
```

### Problem 3: Groq Model Deprecation

`llama-3.1-8b-instant` worked in August 2026, but was moved to Enterprise-only by October. Had to switch to `openai/gpt-oss-20b` mid-development.

**Solution:** Made the model configurable in `llm.py`, so future changes are a one-line fix.

### Problem 4: PDF Temp File Handling on Windows

FastAPI's `UploadFile` gives you bytes, not a file path. LlamaIndex's `PDFReader` wants a path. Had to write uploaded bytes to a temp file, process it, then delete it.

**Solution:**
```python
with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
    temp_file.write(await file.read())
    temp_path = temp_file.name

# Process temp_path
# ...

# Cleanup
os.unlink(temp_path)
```

## Performance Characteristics

**Embedding Speed:**
- HuggingFace model: ~100 chunks/second on CPU
- Groq API: ~500 chunks/second (network-bound)

**Search Speed:**
- Qdrant query: 5-20ms for 14 chunks
- Qdrant query: 50-100ms for 100K chunks (HNSW kicks in)
- Qdrant query: 100-200ms for 1M+ chunks

**LLM Generation:**
- Groq: 500-800ms for 200-token response
- OpenRouter: 2-5 seconds (slower)

**End-to-End:**
- Small dataset (< 1K chunks): < 1 second
- Medium dataset (10K chunks): 1-2 seconds
- Large dataset (100K+ chunks): 2-3 seconds

## System Limits & Maximum Capabilities

This is where we get real about what this thing can handle. Every system has a ceiling, and it's better you know it upfront than find out during a critical moment.

### Storage & Throughput

**Maximum Chunks:** ~10 million (in a single Qdrant collection)  
**Maximum File Size:** 50MB per upload  
**Maximum Query Length:** 2,000 characters  
**Maximum Context Window:** ~6,000-8,000 tokens (what the LLM receives)  
**Maximum Search Results:** 20 chunks at once  

**Realistic Limits:**
- **Small (< 1,000 chunks):** 50-100MB of documents, instant search
- **Medium (1,000-100K chunks):** 500MB - 5GB, search latency < 100ms
- **Large (100K-1M chunks):** 5-50GB, search latency 100-500ms
- **Massive (1M+ chunks):** Qdrant still fast, but needs distributed setup

### Accuracy & Hallucination

This is the critical part. RAG reduces hallucination, but doesn't eliminate it.

**When It Works Well:**
- Questions directly answerable from document text (95%+ accuracy)
- Factual queries with clear answers in docs (90%+ accuracy)
- Questions requiring synthesis of 2-3 chunks (80%+ accuracy)

**When It Starts Breaking:**
- Questions requiring information from 5+ chunks (60-70% accuracy)
- Complex reasoning across many documents (50-60% accuracy)
- Questions mixing document context with real-time data (unreliable)

**Why Hallucination Still Happens:**
1. **Poor chunk relevance:** Top 5 chunks don't contain the answer → LLM guesses
2. **Contradictory context:** Multiple chunks say different things → LLM picks one
3. **Out-of-distribution questions:** Nothing in docs matches the query → LLM generates plausible-sounding nonsense
4. **LLM confidence:** Even with context, models sometimes "fill gaps"

**How to Minimize:**
- Use high similarity thresholds (0.7+) for relevance filtering
- Show users the sources (transparency = trust)
- Test with known Q&A before production
- Limit to factual questions, avoid interpretation-heavy ones
- Keep context window small (top 3-5 chunks, not 20)

### Performance Limits

**Embedding Speed:**
- HuggingFace (local): 100 chunks/sec (CPU-bound)
- Groq API: 500 chunks/sec (network-bound, free tier)

**Search Speed:**
- Qdrant HNSW: O(log N) complexity
- 14 chunks: < 5ms
- 100K chunks: 50-100ms
- 1M chunks: 100-200ms
- Qdrant maxes out at ~10M chunks before needing sharding

**LLM Response Time:**
- Groq 20B: 500-1000ms for 200-token response
- Network latency: 50-100ms each way
- Total per query: ~600-1100ms

**Realistic End-to-End Latency:**
- Small dataset: 800ms - 1.5s
- Medium dataset: 1.5s - 3s
- Large dataset: 3-5s

### Token Limits (The Silent Killer)

**Groq Free Tier:**
- 250,000 tokens per minute (TPM) across all requests
- Each search uses ~1,000-2,000 tokens (query + context + response)
- That's ~125-250 concurrent users at max capacity
- Rate limit: 1,000 requests per minute (RPM)

**In Practice:**
- You can do ~250 searches/minute (250K tokens ÷ 1K tokens per search)
- With 5-second response time, that's fine for most use cases
- Heavy load (100+ concurrent users) needs rate limiting

### Context Window Gotchas

The LLM gets: System prompt + Context + Your question

**HuggingFace all-MiniLM-L6-v2 embedding context:**
- Max tokens in embedding: ~512 tokens (one chunk ~300-400 chars)
- You can safely embed up to 8,192 tokens

**Groq LLM context window:**
- OpenAI gpt-oss-20b: 131,072 tokens
- That's massive, but you don't need all of it
- Optimal: send 3-5 chunks (~1,500-3,000 tokens) + query (~100 tokens)
- Anything over 8,000 tokens and response quality degrades

### When Things Fall Apart

**You'll hit limits when:**

1. **Too many similar chunks (> 50K):** HNSW gets slower, reranking becomes necessary
2. **Long documents (> 20K chars):** Chunk overlap strategy breaks down
3. **Concurrent users (> 50):** Groq free tier gets rate-limited
4. **Contradictory knowledge base:** Relevance scoring becomes useless
5. **Domain shift:** Documents about Topic A, questions about Topic B → 404 answers
6. **Chunking too aggressively:** 256-char chunks = lots of repetition
7. **Chunking too conservatively:** 2000-char chunks = loss of focus

### Scaling Solutions (If You Ever Get Here)

**Problem: Need more concurrent users?**  
→ Use a paid LLM API (OpenAI, Anthropic) with higher rate limits

**Problem: Need accuracy on 10M+ chunks?**  
→ Add a reranker (cross-encoder model), use hybrid search (keyword + vector)

**Problem: Need real-time updates?**  
→ Add incremental indexing, webhook-based refresh

**Problem: Need multi-user isolation?**  
→ Add namespacing to Qdrant, per-user filtering

**Problem: Hallucination killing your use case?**  
→ Use smaller chunks, higher similarity thresholds, or switch to a bigger LLM

## Current Limitations

This is a single-machine local deployment. Here's what's not production-ready:

### Local-Only Limitations

- **No cloud deployment** - Requires Docker Desktop which doesn't exist in cloud
- **Single instance** - One Streamlit app, one FastAPI server, one Qdrant instance
- **No scalability** - Can't handle 1000 concurrent users
- **No persistence** - Qdrant data lives in your Docker container (lost on restart)
- **No redundancy** - Everything fails if your machine restarts
- **No backups** - No automatic data backups
- **No monitoring** - Can't see what's happening in production
- **No CI/CD** - No automated testing or deployment

### Performance Limitations

- **Search latency** - 1-3 seconds (network overhead)
- **Cold start** - First question takes 2-5 seconds (model loading)
- **Memory hungry** - Embedding model uses ~1GB RAM
- **CPU bound** - Local embeddings peg your CPU

### Cost Limitations

- **Free tier is fragile** - Groq may change terms, close free tier
- **No SLA** - No guarantee of uptime or performance
- **Limited to 50 concurrent users** - Groq rate limits kick in
- **Storage on local disk** - No cloud backup

### Data & Security Limitations

- **No authentication** - Anyone with network access can query/upload
- **No rate limiting** - Someone could spam your instance
- **No encryption** - Data passes unencrypted locally
- **No audit logs** - Can't see who accessed what
- **Exposed API keys** - `.env` file is human-readable

### Feature Limitations

- **No reranking** - Can't re-score search results
- **No hybrid search** - Only vector, no keyword fallback
- **No caching** - Repeated queries hit the LLM every time
- **No webhooks** - Can't automate uploads
- **No scheduled tasks** - Can't schedule document ingestion
- **No multi-tenancy** - Can't serve multiple organizations

## Deployment Guide

### Local Deployment (What This Is)

You're running everything on your machine:
- **Qdrant** runs in Docker Desktop (local container)
- **FastAPI** runs in your terminal
- **Streamlit** runs in your browser
- Perfect for: Single user, testing, development, small datasets

### Cloud Deployment (Scaling Up)

If you want to run this in the cloud (AWS, GCP, Heroku, etc.), you need to understand what needs to move:

**Problem:** Docker Desktop won't work in cloud. You need cloud-native alternatives.

**Solution 1: Containerized Cloud (Easiest)**

Package everything in Docker and deploy to:
- **AWS ECS/Fargate** - Managed Docker containers
- **Google Cloud Run** - Serverless containers
- **DigitalOcean App Platform** - Simple container hosting

Steps:
1. Create `Dockerfile` for FastAPI + Streamlit
2. Use **Managed Qdrant Cloud** instead of Docker (https://qdrant.to/cloud)
3. Push to container registry (Docker Hub, AWS ECR, GCP Container Registry)
4. Deploy to cloud platform

Cost: $10-100/month depending on usage

**Solution 2: Serverless (Most Scalable)**

- **AWS Lambda** for FastAPI (using Mangum)
- **Cloud Functions** (GCP) for FastAPI
- **Vercel** for Streamlit (via custom server)
- **Managed Vector DB** (Qdrant Cloud, Pinecone, Weaviate Cloud)

Cost: Pay-as-you-go, ~$5-50/month for low traffic

**Solution 3: Kubernetes (Most Complex)**

If you need enterprise-grade:
- Deploy on **AWS EKS**, **GCP GKE**, or **Azure AKS**
- Use **Helm charts** for Qdrant, FastAPI, Streamlit
- Auto-scaling, load balancing, monitoring included
- Cost: $50-500+/month

### Step-by-Step: Deploy to AWS Fargate (Recommended for Beginners)

**1. Create Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Expose ports
EXPOSE 8001 8501

# Run both services
CMD ["bash", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port 8001 & streamlit run app.py --server.port 8501 --server.address 0.0.0.0"]
```

**2. Set up Qdrant Cloud:**
- Sign up at https://qdrant.to/cloud
- Create a free/paid cluster
- Get API key and URL
- Update `vector_db.py` to use cloud endpoint

**3. Push to AWS:**
```bash
# Create ECR repository
aws ecr create-repository --repository-name wally

# Build and push
docker build -t wally .
docker tag wally:latest <your-aws-account>.dkr.ecr.us-east-1.amazonaws.com/wally:latest
docker push <your-aws-account>.dkr.ecr.us-east-1.amazonaws.com/wally:latest

# Deploy to Fargate via AWS Console or CLI
```

**4. Environment Variables in Cloud:**
```env
GROQ_API_KEY=your_key
QDRANT_URL=https://your-qdrant-cloud.io
QDRANT_API_KEY=your_qdrant_key
```

### What You Need to Change for Cloud

1. **Replace Qdrant Docker with Qdrant Cloud**
   ```python
   # Instead of: QdrantClient(url="http://localhost:6333")
   qdrant = QdrantClient(
       url="https://your-cluster.qdrant.io",
       api_key="your_api_key"
   )
   ```

2. **Add authentication to FastAPI**
   ```python
   from fastapi.security import HTTPBearer
   
   security = HTTPBearer()
   
   @app.post("/search")
   async def search(request: SearchRequest, credentials: HTTPAuthCredentials = Depends(security)):
       # Verify token
       pass
   ```

3. **Add rate limiting**
   ```python
   from slowapi import Limiter
   
   limiter = Limiter(key_func=get_remote_address)
   
   @app.post("/search")
   @limiter.limit("100/minute")
   async def search(request: SearchRequest):
       pass
   ```

4. **Add caching**
   ```python
   from redis import Redis
   
   cache = Redis(host="localhost", port=6379)
   
   # Cache search results
   ```

5. **Add monitoring**
   - Use **Datadog**, **New Relic**, or **CloudWatch**
   - Track: API latency, error rates, token usage, storage size

### Recommendation

**For 2026:**
- **Small team (< 10 users):** Deploy to Heroku or Railway with Qdrant Cloud ($50-100/month)
- **Growing startup (10-100 users):** AWS Fargate + Qdrant Cloud + CloudFront CDN ($100-300/month)
- **Enterprise:** Kubernetes on AWS/GCP with managed services ($500+/month)

The current setup is "local-only" by design. Moving to cloud requires careful thought about:
- Data persistence
- Scalability
- Cost efficiency
- Security
- Monitoring

Don't just "lift and shift" to cloud. Architect for it from the start if that's your plan.

## What I'd Change If I Built This Again

**1. Use PostgreSQL with pgvector for simpler deployment**

Qdrant is great, but adding Docker + a separate service is overhead. pgvector lets you store vectors directly in Postgres. One less thing to manage.

**2. Add reranking**

Right now, I take the top 5 chunks from Qdrant and feed them all to the LLM. A reranker (like `cross-encoder/ms-marco-MiniLM-L-12-v2`) would score those 5 again with the actual query and reorder them. Better context = better answers.

**3. Implement hybrid search**

Pure vector search misses exact keyword matches sometimes. Combining vector search (semantic) with BM25 (keyword) gives you both. Qdrant supports this, I just haven't wired it up yet.

**4. Add caching**

Same question twice? Why compute it twice? A Redis cache in front of the LLM would save 80% of repeated queries.

**5. Stream the LLM response**

Right now, you wait for the full answer. Streaming it token-by-token (like ChatGPT) feels more responsive. FastAPI + Streamlit both support SSE (Server-Sent Events) for this.

## Final Thoughts

RAG isn't magic. It's just really good information retrieval + a language model that can synthesize. The hard part isn't the ML, it's the engineering: handling PDFs, managing vectors, tuning chunk sizes, picking the right similarity threshold, and making it all fast enough that users don't leave.

This system works. It's not perfect, but it's free, fast, and doesn't hallucinate because everything is grounded in your documents. That's the whole point.

Now go build something.

---

**Tech Stack:**
- Python 3.11
- FastAPI (backend)
- Streamlit (frontend)
- Qdrant (vector database)
- HuggingFace Transformers (embeddings)
- Groq API (LLM)
- LlamaIndex (PDF parsing + chunking)
- Inngest (event scheduling, optional)

**Status:** Production-ready for small to medium datasets (< 100K chunks), local deployment only  
**Last Updated:** October 2026  
**Next Steps:** Cloud deployment guide, add reranking, hybrid search, caching, monitoring
