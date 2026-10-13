"""
Document data loader using LlamaIndex.
Loads PDFs and text files, chunks text, and splits by sentences.
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader


class DocumentLoader:
    """
    Loads PDF and text files, chunks them into sentences.
    Uses LlamaIndex for both loading and parsing.
    Supports: .pdf, .txt, .md
    """
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        sentence_splitter: bool = True
    ):
        """
        Initialize the PDF data loader.
        
        Args:
            chunk_size: Target size for each chunk (in characters)
            chunk_overlap: Overlap between chunks (in characters)
            sentence_splitter: If True, split at sentence boundaries
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Initialize the sentence splitter
        self.splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            # Ensure we split at sentence boundaries
            separator="\n"
        )
        
        # Initialize PDF reader
        self.pdf_reader = PDFReader()
    
    def load_text_file(self, file_path: str) -> List[Document]:
        """
        Load a text file (.txt, .md, etc.).
        
        Args:
            file_path: Path to the text file
            
        Returns:
            List of LlamaIndex Documents
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Text file not found: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Create a single document with metadata
        doc = Document(
            text=text,
            metadata={
                "source_file": path.name,
                "file_type": path.suffix,
            }
        )
        return [doc]
    
    def load_pdf(self, file_path: str) -> List[Document]:
        """
        Load a single PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            List of LlamaIndex Documents
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        
        documents = self.pdf_reader.load_data(file=path)
        return documents
    
    def load_file(self, file_path: str) -> List[Document]:
        """
        Load any supported file type (auto-detects based on extension).
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of LlamaIndex Documents
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        if suffix == '.pdf':
            return self.load_pdf(file_path)
        elif suffix in ['.txt', '.md', '.markdown', '.text']:
            return self.load_text_file(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}. Supported: .pdf, .txt, .md")
    
    def load_pdfs(self, directory: str, glob_pattern: str = "*.pdf") -> List[Document]:
        """
        Load all PDF files from a directory.
        
        Args:
            directory: Directory containing PDF files
            glob_pattern: Pattern to match PDF files
            
        Returns:
            List of LlamaIndex Documents
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        pdf_files = list(dir_path.glob(glob_pattern))
        
        all_documents = []
        for pdf_file in pdf_files:
            documents = self.load_pdf(str(pdf_file))
            # Add source metadata to each document
            for doc in documents:
                doc.metadata["source_file"] = pdf_file.name
            all_documents.extend(documents)
        
        return all_documents
    
    def load_directory(self, directory: str, glob_pattern: str = "*.*") -> List[Document]:
        """
        Load all supported files from a directory.
        
        Args:
            directory: Directory containing files
            glob_pattern: Pattern to match files (default: *.*)
            
        Returns:
            List of LlamaIndex Documents
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        files = list(dir_path.glob(glob_pattern))
        
        all_documents = []
        for file_path in files:
            # Skip directories and unsupported files
            if file_path.is_dir():
                continue
            
            try:
                documents = self.load_file(str(file_path))
                # Add source metadata to each document
                for doc in documents:
                    if "source_file" not in doc.metadata:
                        doc.metadata["source_file"] = file_path.name
                all_documents.extend(documents)
            except ValueError as e:
                # Skip unsupported file types
                print(f"Skipping {file_path.name}: {e}")
                continue
        
        return all_documents
    
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split documents into chunks using sentence splitting.
        
        Args:
            documents: List of LlamaIndex Documents
            
        Returns:
            List of chunked Documents
        """
        # The SentenceSplitter handles sentence-aware splitting
        nodes = self.get_nodes(documents)
        
        # Convert nodes back to documents
        chunks = []
        for node in nodes:
            doc = Document(
                text=node.text,
                metadata={**node.metadata}
            )
            chunks.append(doc)
        
        return chunks
    
    def get_nodes(self, documents: List[Document]):
        """
        Parse documents into nodes using the sentence splitter.
        
        Args:
            documents: List of LlamaIndex Documents
            
        Returns:
            List of nodes (chunks)
        """
        return self.splitter.get_nodes_from_documents(documents)
    
    def load_and_chunk(
        self, 
        file_path: Optional[str] = None, 
        directory: Optional[str] = None,
        glob_pattern: str = "*.*"
    ) -> List[Document]:
        """
        Convenience method to load and chunk in one step.
        
        Args:
            file_path: Path to a single file (PDF or text)
            directory: Path to directory with files
            glob_pattern: Pattern for files (default: *.* for all)
            
        Returns:
            List of chunked Documents
        """
        if file_path:
            documents = self.load_file(file_path)
        elif directory:
            documents = self.load_directory(directory, glob_pattern)
        else:
            raise ValueError("Either file_path or directory must be provided")
        
        return self.chunk_documents(documents)
    
    def load_and_chunk_with_metadata(
        self,
        file_path: Optional[str] = None,
        directory: Optional[str] = None,
        glob_pattern: str = "*.*",
        file_metadata: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Load files and return chunks as dicts with metadata.
        
        Args:
            file_path: Path to a single file (PDF or text)
            directory: Path to directory with files
            glob_pattern: Pattern for files (default: *.*)
            file_metadata: Additional metadata to add to all chunks
            
        Returns:
            List of dicts with 'text' and 'metadata' keys
        """
        chunks = self.load_and_chunk(file_path=file_path, directory=directory, glob_pattern=glob_pattern)
        
        results = []
        for i, chunk in enumerate(chunks):
            metadata = dict(chunk.metadata) if chunk.metadata else {}
            if file_metadata:
                metadata.update(file_metadata)
            metadata["chunk_index"] = i
            
            results.append({
                "text": chunk.text,
                "metadata": metadata
            })
        
        return results


# Keep old class name for backward compatibility
PDFDataLoader = DocumentLoader


# Convenience function for quick usage
def load_documents(
    source: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    is_directory: bool = False,
    glob_pattern: str = "*.*"
) -> List[Dict[str, Any]]:
    """
    Quick load function for documents (PDFs, text files, etc.).
    
    Usage:
        # Load single file
        chunks = load_documents("document.pdf")
        chunks = load_documents("notes.txt")
        
        # Load all files from directory
        chunks = load_documents("./docs", is_directory=True)
        
        # Load only PDFs from directory
        chunks = load_documents("./docs", is_directory=True, glob_pattern="*.pdf")
    
    Args:
        source: File path or directory path
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks
        is_directory: If True, treat source as directory
        glob_pattern: File pattern to match (when is_directory=True)
        
    Returns:
        List of dicts with 'text' and 'metadata'
    """
    loader = DocumentLoader(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    
    if is_directory:
        chunks = loader.load_and_chunk_with_metadata(directory=source, glob_pattern=glob_pattern)
    else:
        chunks = loader.load_and_chunk_with_metadata(file_path=source)
    
    return chunks


# Keep old function name for backward compatibility
load_pdfs = load_documents


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        source = sys.argv[1]
        is_dir = len(sys.argv) > 2 and sys.argv[2] == "--dir"
        
        chunks = load_pdfs(source, is_directory=is_dir)
        print(f"Loaded {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks[:3]):
            print(f"\n--- Chunk {i} ---")
            print(chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"])
    else:
        print("Usage: python data_loader.py <file_or_directory> [--dir]")