"""
Direct query interface for the RAG system.
Use this for direct Python usage without the API.
"""
from typing import List, Dict, Any, Optional

from vector_db import RAGVectorDB
from llm import get_llm_provider
from data_loader import PDFDataLoader


class RAGQuery:
    """
    Main interface for RAG operations.
    Provides both search and ingest capabilities.
    """
    
    def __init__(
        self,
        collection: str = "docs",
        embed_provider: str = "groq",
        embed_model: str = "llama-embeddings-7b-v0",
        llm_provider: str = "groq",
        llm_model: str = "llama-3.1-8b-instant"
    ):
        """
        Initialize RAG query interface.
        
        Args:
            collection: Qdrant collection name
            embed_provider: Embedding provider ("groq", "huggingface", "openrouter")
            embed_model: Embedding model name
            llm_provider: LLM provider ("groq", "openrouter")
            llm_model: LLM model name
        """
        # Initialize vector DB with embeddings
        self.db = RAGVectorDB(
            collection=collection,
            embed_provider=embed_provider,
            embed_model=embed_model
        )
        
        # Initialize LLM
        self.llm = get_llm_provider(llm_provider, model=llm_model)
        
        # Data loader for PDFs
        self.loader = PDFDataLoader()
    
    def ingest_texts(self, texts: List[str], metadata: List[Dict] = None) -> List[str]:
        """
        Ingest text strings into the vector database.
        
        Args:
            texts: List of text strings
            metadata: Optional list of metadata dicts
            
        Returns:
            List of generated IDs
        """
        return self.db.add_texts(texts, metadata=metadata)
    
    def ingest_pdf(self, file_path: str, metadata: Dict = None) -> List[str]:
        """
        Load and ingest a PDF file.
        
        Args:
            file_path: Path to PDF file
            metadata: Optional metadata dict
            
        Returns:
            List of generated IDs
        """
        chunks = self.loader.load_and_chunk_with_metadata(
            file_path=file_path,
            file_metadata=metadata or {}
        )
        
        texts = [chunk["text"] for chunk in chunks]
        chunk_metadata = [chunk["metadata"] for chunk in chunks]
        
        return self.db.add_texts(texts, metadata=chunk_metadata)
    
    def ingest_directory(self, directory: str, glob_pattern: str = "*.pdf") -> List[str]:
        """
        Load and ingest all PDFs from a directory.
        
        Args:
            directory: Path to directory
            glob_pattern: Glob pattern for files
            
        Returns:
            List of generated IDs
        """
        chunks = self.loader.load_and_chunk_with_metadata(
            directory=directory,
            glob_pattern=glob_pattern
        )
        
        texts = [chunk["text"] for chunk in chunks]
        chunk_metadata = [chunk["metadata"] for chunk in chunks]
        
        return self.db.add_texts(texts, metadata=chunk_metadata)
    
    def search_only(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search vector database without LLM generation.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            List of search results with text and scores
        """
        results = self.db.similarity_search(query, top_k=top_k)
        return [
            {
                "id": r["id"],
                "score": r["score"],
                "text": r["payload"].get("text", ""),
                "metadata": {k: v for k, v in r["payload"].items() if k != "text"}
            }
            for r in results
        ]
    
    def query(self, query: str, top_k: int = 5, include_sources: bool = True) -> Dict:
        """
        Full RAG query: search + LLM answer.
        
        Args:
            query: User question
            top_k: Number of documents to retrieve
            include_sources: Include source documents in response
            
        Returns:
            Dict with 'answer' and optionally 'sources'
        """
        # Search
        results = self.db.similarity_search(query, top_k=top_k)
        
        if not results:
            return {"answer": "No relevant documents found.", "sources": []}
        
        # Build context
        context = "\n\n".join([r["payload"].get("text", "") for r in results])
        
        # Generate answer
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant. Use the provided context to answer. If the context doesn't have the answer, say so."
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {query}"
            }
        ]
        
        answer = self.llm.chat(messages)
        
        response = {"answer": answer}
        
        if include_sources:
            response["sources"] = [
                {
                    "id": r["id"],
                    "score": r["score"],
                    "text": r["payload"].get("text", "")[:300]
                }
                for r in results
            ]
        
        return response


# Convenience function for quick usage
def create_rag() -> RAGQuery:
    """Create a default RAGQuery instance."""
    return RAGQuery()


if __name__ == "__main__":
    # Example usage
    import sys
    
    rag = create_rag()
    
    # Example: Query
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"Query: {query}\n")
        result = rag.query(query)
        print(f"Answer: {result['answer']}\n")
        print("Sources:")
        for s in result.get("sources", []):
            print(f"  - [{s['score']:.3f}] {s['text'][:100]}...")
    else:
        print("Usage: python queries.py <your question>")