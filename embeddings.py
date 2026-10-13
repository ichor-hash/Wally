"""
Embedding providers for RAG system.
Supports multiple backends: HuggingFace (local), Groq, OpenRouter.
"""
import os
from abc import ABC, abstractmethod
from typing import List

# Try imports - will fail gracefully if not installed
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    import groq
except ImportError:
    groq = None


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""
    
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Convert texts to embedding vectors."""
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        pass


class HuggingFaceEmbeddings(EmbeddingProvider):
    """
    Local embeddings using HuggingFace sentence-transformers.
    Completely free, runs locally.
    
    Popular models:
    - sentence-transformers/all-MiniLM-L6-v2 (384 dims) - fast, good quality
    - BAAI/bge-small-en-v1.5 (384 dims) - better quality
    - intfloat/e5-small-v2 (384 dims) - good for semantic search
    """
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        if SentenceTransformer is None:
            raise ImportError("sentence-transformers not installed. Run: pip install sentence-transformers")
        
        self.model = SentenceTransformer(model_name)
    
    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, convert_to_numpy=True).tolist()


class GroqEmbeddings(EmbeddingProvider):
    """
    Cloud embeddings via Groq API.
    Free tier available at https://console.groq.com
    
    Requires: GROQ_API_KEY in environment
    """
    
    def __init__(self, model: str = "llama-embeddings-7b-v0"):
        if groq is None:
            raise ImportError("groq not installed. Run: pip install groq")
        
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        
        self.client = groq.Groq(api_key=api_key)
        self.model = model
        
        # Model dimensions
        self._dimension = 1024  # llama-embeddings-7b-v0 uses 1024
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        # Groq embeddings API
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]


class OpenRouterEmbeddings(EmbeddingProvider):
    """
    Cloud embeddings via OpenRouter API.
    Free credits available for new accounts.
    
    Requires: OPENROUTER_API_KEY in environment
    """
    
    def __init__(self, model: str = "microsoft/phi-3-mini-128k-instruct"):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")
        
        self.api_key = api_key
        self.model = model
        self._dimension = 4096  # varies by model
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        import requests
        
        response = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "input": texts
            }
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]


def get_embedding_provider(provider: str = "huggingface", **kwargs) -> EmbeddingProvider:
    """
    Factory function to get embedding provider.
    
    Usage:
        # Local (free)
        embedder = get_embedding_provider("huggingface")
        
        # Cloud (requires API key)
        embedder = get_embedding_provider("groq")
        embedder = get_embedding_provider("openrouter")
    
    Args:
        provider: One of "huggingface", "groq", "openrouter"
        **kwargs: Additional arguments passed to provider constructor
    
    Returns:
        EmbeddingProvider instance
    """
    providers = {
        "huggingface": HuggingFaceEmbeddings,
        "groq": GroqEmbeddings,
        "openrouter": OpenRouterEmbeddings,
    }
    
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(providers.keys())}")
    
    return providers[provider](**kwargs)