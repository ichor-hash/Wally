from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct


class QdrantStorage:
    def __init__(self, url: str = "http://localhost:6333", collection: str = "docs", dimension: int = 384): 
        self.client = QdrantClient(url=url, timeout=30)
        self.collection = collection
        self.dimension = dimension
        
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE)
            )
    
    def upsert(self, ids, vectors, payloads):
        """Insert or update vectors in the collection."""
        points = [
            PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i]) 
            for i in range(len(ids))
        ]
        self.client.upsert(collection_name=self.collection, points=points)
    
    def search(self, query_vector, top_k: int = 5, filter_query: dict = None):
        """Search for similar vectors."""
        return self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=top_k,
            query_filter=filter_query
        )
    
    def delete(self, ids):
        """Delete points by IDs."""
        self.client.delete(
            collection_name=self.collection,
            points_selector=ids
        )
    
    def delete_collection(self):
        """Delete the entire collection."""
        self.client.delete_collection(collection_name=self.collection)


# Import the embedding provider factory
from embeddings import get_embedding_provider


class RAGVectorDB(QdrantStorage):
    """
    Extended Qdrant storage with built-in embedding support.
    Uses Groq by default for embeddings.
    Simplifies the RAG pipeline by handling embeddings internally.
    """
    
    def __init__(
        self, 
        url: str = "http://localhost:6333", 
        collection: str = "docs",
        embed_provider: str = "huggingface",
        embed_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        **embed_kwargs
    ):
        # Get embedding provider to determine dimension
        self.embedder = get_embedding_provider(embed_provider, model_name=embed_model, **embed_kwargs)
        dimension = self.embedder.dimension
        
        super().__init__(url=url, collection=collection, dimension=dimension)
        
        self.embed_provider = embed_provider
        self.embed_model = embed_model
    
    def add_texts(self, texts: list, ids: list = None, metadata: list = None):
        """
        Convenience method to add texts directly with automatic embedding.
        
        Args:
            texts: List of text strings to embed and store
            ids: Optional list of IDs (auto-generated if None)
            metadata: Optional list of metadata dicts
        """
        # Generate sequential integer IDs if not provided
        if ids is None:
            import time
            base_id = int(time.time() * 1000000)  # Use microsecond timestamp as base
            ids = [base_id + i for i in range(len(texts))]
        
        # Generate embeddings
        vectors = self.embedder.embed(texts)
        
        # Prepare payloads
        if metadata is None:
            metadata = [{"text": text} for text in texts]
        else:
            for i, m in enumerate(metadata):
                m["text"] = texts[i]
        
        self.upsert(ids, vectors, metadata)
        return ids
    
    def similarity_search(self, query: str, top_k: int = 5, filter_query: dict = None):
        """
        Search by text query (automatically embeds the query).
        
        Args:
            query: Text query to search for
            top_k: Number of results to return
            filter_query: Optional Qdrant filter
        
        Returns:
            List of search results with payload and score
        """
        query_vector = self.embedder.embed([query])[0]
        response = self.search(query_vector, top_k=top_k, filter_query=filter_query)
        
        # Handle Qdrant QueryResponse - it has a .points attribute
        points = response.points if hasattr(response, 'points') else response
        
        parsed_results = []
        for point in points:
            parsed_results.append({
                "id": point.id,
                "score": point.score,
                "payload": point.payload
            })
        
        return parsed_results