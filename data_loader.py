"""
Document data loader using PyPDF (no llama-index required).
Loads PDFs and text files, chunks text by character count.
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import re

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        PdfReader = None


class DocumentLoader:
    """
    Loads PDF and text files, chunks them into manageable pieces.
    Supports: .pdf, .txt, .md
    """
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        sentence_splitter: bool = True
    ):
        """
        Initialize the document loader.
        
        Args:
            chunk_size: Target size for each chunk (in characters)
            chunk_overlap: Overlap between chunks (in characters)
            sentence_splitter: If True, try to split at sentence boundaries
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.sentence_splitter = sentence_splitter
        
        if PdfReader is None:
            raise ImportError("pypdf not installed. Run: pip install pypdf")
    
    def load_text_file(self, file_path: str) -> str:
        """
        Load a text file (.txt, .md, etc.).
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Text content as string
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Text file not found: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        return text
    
    def load_pdf(self, file_path: str) -> str:
        """
        Load a single PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Text content as string
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        
        reader = PdfReader(str(path))
        text_parts = []
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    def load_file(self, file_path: str) -> str:
        """
        Load any supported file type (auto-detects based on extension).
        
        Args:
            file_path: Path to the file
            
        Returns:
            Text content as string
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        if suffix == '.pdf':
            return self.load_pdf(file_path)
        elif suffix in ['.txt', '.md', '.markdown', '.text']:
            return self.load_text_file(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}. Supported: .pdf, .txt, .md")
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks with overlap.
        
        Args:
            text: Input text to chunk
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
        
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + self.chunk_size
            
            # If sentence splitting is enabled, try to end at sentence boundary
            if self.sentence_splitter and end < text_len:
                # Look for sentence endings near the chunk boundary
                search_start = max(start, end - 100)
                search_end = min(text_len, end + 100)
                chunk_portion = text[search_start:search_end]
                
                # Find the last sentence ending
                sentence_ends = [m.end() for m in re.finditer(r'[.!?]\s+', chunk_portion)]
                if sentence_ends:
                    # Adjust end to the last sentence boundary
                    last_sentence = sentence_ends[-1]
                    end = search_start + last_sentence
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            if end >= text_len:
                break
            
            # Move start position with overlap, always making forward progress
            next_start = end - self.chunk_overlap
            start = next_start if next_start > start else end
        
        return chunks
    
    def load_and_chunk(
        self, 
        file_path: Optional[str] = None, 
        directory: Optional[str] = None,
        glob_pattern: str = "*.*"
    ) -> List[Dict[str, Any]]:
        """
        Load and chunk files, return with metadata.
        
        Args:
            file_path: Path to a single file (PDF or text)
            directory: Path to directory with files
            glob_pattern: Pattern for files (default: *.* for all)
            
        Returns:
            List of dicts with 'text' and 'metadata' keys
        """
        if file_path:
            path = Path(file_path)
            text = self.load_file(file_path)
            chunks = self.chunk_text(text)
            
            results = []
            for i, chunk in enumerate(chunks):
                results.append({
                    "text": chunk,
                    "metadata": {
                        "source_file": path.name,
                        "file_type": path.suffix,
                        "chunk_index": i
                    }
                })
            return results
            
        elif directory:
            dir_path = Path(directory)
            if not dir_path.exists():
                raise FileNotFoundError(f"Directory not found: {directory}")
            
            files = list(dir_path.glob(glob_pattern))
            all_results = []
            
            for file_path in files:
                if file_path.is_dir():
                    continue
                
                try:
                    text = self.load_file(str(file_path))
                    chunks = self.chunk_text(text)
                    
                    for i, chunk in enumerate(chunks):
                        all_results.append({
                            "text": chunk,
                            "metadata": {
                                "source_file": file_path.name,
                                "file_type": file_path.suffix,
                                "chunk_index": i
                            }
                        })
                except (ValueError, Exception) as e:
                    print(f"Skipping {file_path.name}: {e}")
                    continue
            
            return all_results
        else:
            raise ValueError("Either file_path or directory must be provided")
    
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
        results = self.load_and_chunk(
            file_path=file_path, 
            directory=directory, 
            glob_pattern=glob_pattern
        )
        
        # Add additional metadata if provided
        if file_metadata:
            for result in results:
                result["metadata"].update(file_metadata)
        
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