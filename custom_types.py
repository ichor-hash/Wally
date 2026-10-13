"""
Custom type definitions for the RAG system.
"""
from typing import List, Optional, Any
from typing_extensions import TypedDict
from dataclasses import dataclass


class DocumentChunk(TypedDict):
    """A chunk of text with metadata."""
    text: str
    metadata: dict


class SearchResult(TypedDict):
    """A search result from the vector database."""
    id: str
    score: float
    payload: dict


class IngestRequest(TypedDict):
    """Request body for ingesting documents."""
    texts: List[str]
    metadata: Optional[List[dict]]


class SearchRequest(TypedDict):
    """Request body for search endpoint."""
    query: str
    top_k: Optional[int]


class SearchResponse(TypedDict):
    """Response from search endpoint."""
    answer: str
    sources: List[dict]


@dataclass
class PDFDocument:
    """Represents a loaded PDF document."""
    file_path: str
    text: str
    page_count: int
    metadata: dict


@dataclass
class ChunkedDocument:
    """A document that has been split into chunks."""
    original_doc: PDFDocument
    chunks: List[DocumentChunk]
    chunk_count: int


class EmbeddingModel(str):
    """Available embedding models."""
    GROQ_LLAMA = "llama-embeddings-7b-v0"
    HF_MINILM = "sentence-transformers/all-MiniLM-L6-v2"
    HF_BGE_SMALL = "BAAI/bge-small-en-v1.5"


class LLMModel(str):
    """Available LLM models."""
    GROQ_LLAMA_8B = "llama-3.1-8b-instant"
    GROQ_LLAMA_70B = "llama-3.1-70b-versatile"
    GROQ_MIXTRAL = "mixtral-8x7b-32768"
    OPENROUTER_GEMMA = "google/gemma-2-9b-it"
    OPENROUTER_LLAMA = "meta-llama/llama-3.1-8b-instruct"


# Collection names
class Collections:
    """Collection name constants."""
    DOCS = "docs"
    PDFs = "pdfs"
    ARTICLES = "articles"