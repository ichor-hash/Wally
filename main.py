import logging
import os
from typing import List
from pathlib import Path

import inngest
from inngest.fast_api import serve
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Production-Ready RAG")

# Import RAG components
from vector_db import RAGVectorDB
from llm import get_llm_provider
from data_loader import DocumentLoader
from custom_types import SearchRequest, SearchResponse

# Initialize RAG components (uses Groq by default)
# You can override the collection name here
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "docs")

rag_db = RAGVectorDB(collection=COLLECTION_NAME)
llm = get_llm_provider("groq")


@app.get("/")
async def root():
    return {"status": "ok", "service": "Production-Ready RAG"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "embedding_provider": rag_db.embed_provider,
        "embedding_model": rag_db.embed_model,
        "llm_model": llm.model,
        "collection": rag_db.collection,
        "dimension": rag_db.dimension
    }


@app.post("/ingest/texts")
async def ingest_texts(texts: List[str], metadata: List[dict] = None):
    """
    Ingest text strings into the vector database.
    
    Body:
        texts: List of text strings to embed and store
        metadata: Optional list of metadata dicts
    """
    try:
        if not texts:
            raise HTTPException(status_code=400, detail="texts cannot be empty")
        
        if len(texts) > 1000:
            raise HTTPException(status_code=413, detail="Too many texts. Max 1000 at a time.")
        
        ids = rag_db.add_texts(texts, metadata=metadata)
        return {"status": "ok", "ingested": len(ids), "ids": ids}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ingesting texts: {str(e)}")


@app.post("/ingest/pdf")
async def ingest_pdf(file: UploadFile = File(...), metadata: dict = None):
    """
    Upload and ingest a PDF or text file.
    
    The file will be loaded, chunked by sentences, and stored in the vector DB.
    Supports: .pdf, .txt, .md
    """
    import tempfile
    import os
    
    temp_path = None
    
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="Invalid file")
        
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ['.pdf', '.txt', '.md']:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}. Supported: .pdf, .txt, .md")
        
        # Check file size (max 50MB)
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large. Max 50MB.")
        
        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        # Load and chunk
        loader = DocumentLoader(chunk_size=512, chunk_overlap=50)
        chunks = loader.load_and_chunk_with_metadata(
            file_path=temp_path,
            file_metadata=metadata or {}
        )
        
        if not chunks:
            raise HTTPException(status_code=400, detail="No text content found in file")
        
        # Extract and store
        texts = [chunk["text"] for chunk in chunks]
        chunk_metadata = [chunk["metadata"] for chunk in chunks]
        
        ids = rag_db.add_texts(texts, metadata=chunk_metadata)
        
        return {
            "status": "ok",
            "file": file.filename,
            "chunks": len(ids),
            "ids": ids[:10]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error ingesting file: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    
    finally:
        # Cleanup
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass


@app.post("/ingest/directory")
async def ingest_directory(directory: str, glob_pattern: str = "*.*"):
    """
    Ingest all supported files from a directory.
    
    Query params:
        directory: Path to directory containing files
        glob_pattern: Glob pattern to match files (default: *.* for all)
                     Use *.pdf for PDFs only, *.txt for text only, etc.
    
    Supported file types: .pdf, .txt, .md
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")
    
    loader = DocumentLoader(chunk_size=512, chunk_overlap=50)
    chunks = loader.load_and_chunk_with_metadata(
        directory=str(dir_path),
        glob_pattern=glob_pattern
    )
    
    texts = [chunk["text"] for chunk in chunks]
    chunk_metadata = [chunk["metadata"] for chunk in chunks]
    
    ids = rag_db.add_texts(texts, metadata=chunk_metadata)
    
    return {
        "status": "ok",
        "directory": str(dir_path),
        "files_matched": len(list(dir_path.glob(glob_pattern))),
        "chunks": len(ids),
        "ids": ids
    }


@app.get("/documents")
async def list_documents():
    """
    Get list of all stored documents and chunks.
    
    Returns:
        List of documents with metadata
    """
    try:
        # Scroll through all points in Qdrant
        result = rag_db.client.scroll(
            collection_name=COLLECTION_NAME,
            limit=100,
            with_payload=True,
            with_vectors=False
        )
        
        points = result[0]
        documents = []
        
        for point in points:
            documents.append({
                "id": point.id,
                "text": point.payload.get("text", "")[:200],
                "source_file": point.payload.get("source_file", "Unknown"),
                "chunk_index": point.payload.get("chunk_index", 0),
                "file_type": point.payload.get("file_type", "unknown")
            })
        
        return {"documents": documents, "total": len(documents)}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching documents: {str(e)}")


@app.delete("/documents/{doc_name}")
async def delete_document(doc_name: str):
    """
    Delete all chunks for a specific document.
    
    Args:
        doc_name: Name of the document/file to delete
    
    Returns:
        Success message with count of deleted chunks
    """
    try:
        # Get all points and find those matching the document name
        result = rag_db.client.scroll(
            collection_name=COLLECTION_NAME,
            limit=1000,
            with_payload=True,
            with_vectors=False
        )
        
        points = result[0]
        delete_ids = []
        
        for point in points:
            if point.payload.get("source_file") == doc_name:
                delete_ids.append(point.id)
        
        if delete_ids:
            rag_db.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=delete_ids
            )
            return {
                "message": f"Deleted {len(delete_ids)} chunks from {doc_name}",
                "deleted_count": len(delete_ids)
            }
        else:
            return {
                "message": f"No chunks found for {doc_name}",
                "deleted_count": 0
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")


@app.post("/search")
async def search(request: SearchRequest) -> SearchResponse:
    """
    Search for similar documents and generate answer with LLM.
    
    Body:
        query: The search query
        top_k: Number of results to retrieve (default: 5)
    
    Returns:
        answer: LLM-generated answer
        sources: List of source documents with scores
    """
    try:
        query = request.get("query")
        top_k = request.get("top_k", 5)
        
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        
        if len(query) > 2000:
            raise HTTPException(status_code=400, detail="Query too long. Max 2000 characters.")
        
        if top_k < 1 or top_k > 20:
            raise HTTPException(status_code=400, detail="top_k must be between 1 and 20")
        
        # Search vector DB
        results = rag_db.similarity_search(query, top_k=top_k)
        
        if not results:
            return SearchResponse(
                answer="No relevant documents found in knowledge base. Try uploading more documents or ask a different question.",
                sources=[]
            )
        
        # Extract context
        context = "\n\n".join([r["payload"].get("text", "") for r in results])
        
        if not context.strip():
            return SearchResponse(
                answer="Retrieved documents but found no text content.",
                sources=[]
            )
        
        # Generate answer
        messages = [
            {
                "role": "system", 
                "content": "You are a helpful assistant. Use the provided context to answer the user's question. If the context doesn't contain relevant information, say so. Be concise and clear."
            },
            {
                "role": "user", 
                "content": f"Context:\n{context}\n\nQuestion: {query}"
            }
        ]
        
        answer = llm.chat(messages)
        
        return SearchResponse(
            answer=answer,
            sources=[{"id": r["id"], "score": r["score"], "text": r["payload"].get("text", "")[:300]} for r in results]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Search error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error during search: {str(e)}")
    """
    Search for similar documents and generate answer with LLM.
    
    Body:
        query: The search query
        top_k: Number of results to retrieve (default: 5)
    
    Returns:
        answer: LLM-generated answer
        sources: List of source documents with scores
    """
    query = request.get("query")
    top_k = request.get("top_k", 5)
    
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    
    # 1. Search vector DB
    results = rag_db.similarity_search(query, top_k=top_k)
    
    if not results:
        return SearchResponse(
            answer="No relevant documents found.",
            sources=[]
        )
    
    # 2. Extract context from results
    context = "\n\n".join([r["payload"].get("text", "") for r in results])
    
    # 3. Generate answer with LLM
    messages = [
        {
            "role": "system", 
            "content": "You are a helpful assistant. Use the provided context to answer the user's question. If the context doesn't contain relevant information, say so."
        },
        {
            "role": "user", 
            "content": f"Context:\n{context}\n\nQuestion: {query}"
        }
    ]
    answer = llm.chat(messages)
    
    return SearchResponse(
        answer=answer,
        sources=[{"id": r["id"], "score": r["score"], "text": r["payload"].get("text", "")[:200]} for r in results]
    )


# ============================================================
# INNGEST FUNCTIONS
# ============================================================
# Inngest handles event-driven workflows. Functions are triggered
# by events sent to the Inngest platform.
#
# EVENTS YOU CAN TRIGGER:
# ------------------------
# 1. rag/ingest_pdf   - Trigger PDF ingestion from a file path
#    Payload: {"file_path": "/path/to/file.pdf"}
#
# 2. rag/ingest_texts - Trigger text ingestion
#    Payload: {"texts": ["text1", "text2"], "metadata": [{}]}
#
# 3. rag/search       - Trigger RAG search
#    Payload: {"query": "your question", "top_k": 5}
#
# HOW TO SEND EVENTS (from your frontend or external system):
# -----------------------------------------------------------
# Using curl:
#   curl -X POST https://your-inngest-url/-/events \
#     -H "Content-Type: application/json" \
#     -d '{"name": "rag/ingest_pdf", "data": {"file_path": "/path/to.pdf"}}'
#
# Using Python:
#   import inngest
#   client = inngest.Inngest(app_id="rag_app")
#   client.send_event("rag/ingest_pdf", {"file_path": "/path/to.pdf"})
#
# DEVELOPMENT VS PRODUCTION:
# --------------------------
# - is_production=False in Inngest client = dev mode (local/webhook testing)
# - Set is_production=True when deploying to production
#
# ============================================================

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,  # Set to True in production
    serializer=inngest.PydanticSerializer(),
)


@inngest_client.create_function(
    fn_id="RAG: Ingest File",
    trigger=inngest.TriggerEvent(event="rag/ingest_file"),
)
async def rag_ingest_file(ctx: inngest.Context):
    """
    Ingest a file (PDF or text) from a file path.
    
    Event: rag/ingest_file
    Payload: {"file_path": "/path/to/document.pdf", "metadata": {}}
    Supports: .pdf, .txt, .md
    """
    event_data = ctx.event.data
    
    file_path = event_data.get("file_path")
    metadata = event_data.get("metadata", {})
    
    if not file_path:
        return {"error": "file_path is required"}
    
    # Load and chunk the file
    loader = DocumentLoader(chunk_size=512, chunk_overlap=50)
    chunks = loader.load_and_chunk_with_metadata(
        file_path=file_path,
        file_metadata=metadata
    )
    
    # Extract texts and metadata
    texts = [chunk["text"] for chunk in chunks]
    chunk_metadata = [chunk["metadata"] for chunk in chunks]
    
    # Add to vector database
    ids = rag_db.add_texts(texts, metadata=chunk_metadata)
    
    return {
        "status": "ok",
        "file": file_path,
        "chunks": len(ids),
        "ids": ids
    }


@inngest_client.create_function(
    fn_id="RAG: Ingest Texts",
    trigger=inngest.TriggerEvent(event="rag/ingest_texts"),
)
async def rag_ingest_texts(ctx: inngest.Context):
    """
    Ingest text strings into the vector database.
    
    Event: rag/ingest_texts
    Payload: {"texts": ["text1", "text2"], "metadata": [{}]}
    """
    event_data = ctx.event.data
    
    texts = event_data.get("texts", [])
    metadata = event_data.get("metadata")
    
    if not texts:
        return {"error": "texts array is required"}
    
    ids = rag_db.add_texts(texts, metadata=metadata)
    
    return {
        "status": "ok",
        "ingested": len(ids),
        "ids": ids
    }


@inngest_client.create_function(
    fn_id="RAG: Search",
    trigger=inngest.TriggerEvent(event="rag/search"),
)
async def rag_search(ctx: inngest.Context):
    """
    Perform RAG search and return answer.
    
    Event: rag/search
    Payload: {"query": "your question", "top_k": 5}
    """
    event_data = ctx.event.data
    
    query = event_data.get("query")
    top_k = event_data.get("top_k", 5)
    
    if not query:
        return {"error": "query is required"}
    
    # Search vector DB
    results = rag_db.similarity_search(query, top_k=top_k)
    
    if not results:
        return {"answer": "No relevant documents found.", "sources": []}
    
    # Extract context
    context = "\n\n".join([r["payload"].get("text", "") for r in results])
    
    # Generate answer with LLM
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Use the provided context to answer the user's question."
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {query}"
        }
    ]
    
    answer = llm.chat(messages)
    
    return {
        "answer": answer,
        "sources": [{"id": r["id"], "score": r["score"]} for r in results]
    }


# Serve the FastAPI app with Inngest
inngest.fast_api.serve(app, inngest_client, [
    rag_ingest_file,
    rag_ingest_texts,
    rag_search
])