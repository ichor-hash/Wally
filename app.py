"""
Production RAG System - Streamlit Frontend
Clean, minimal interface with Figtree typography.
"""
import streamlit as st
import requests
from pathlib import Path

# ============================================================
# CONFIG & STYLING
# ============================================================
API_URL = "http://localhost:8001"

st.set_page_config(
    page_title="Wally - RAG Chat",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Apply Figtree font globally
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap');

* {
    font-family: 'Figtree', sans-serif !important;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# HELPER FUNCTIONS
# ============================================================

@st.cache_data(ttl=5)
def get_stored_documents():
    """Fetch list of documents currently in storage"""
    try:
        response = requests.get(f"{API_URL}/documents", timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return {"documents": []}

@st.cache_data(ttl=10)
def get_health_info():
    """Fetch system health info"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def delete_document(doc_id):
    """Delete a document and its chunks"""
    try:
        response = requests.delete(f"{API_URL}/documents/{doc_id}", timeout=10)
        if response.status_code == 200:
            st.cache_data.clear()
            return True, response.json().get("message", "Deleted successfully")
        else:
            return False, f"Error: {response.status_code}"
    except Exception as e:
        return False, f"Error: {str(e)}"

# ============================================================
# HEADER
# ============================================================
st.title("Wally")
st.caption("Your documents, smarter. Ask anything.")

# ============================================================
# TABS
# ============================================================
tab1, tab2 = st.tabs(["Ask Questions", "Ingest Documents"])

# ============================================================
# TAB 1: CHAT & STORAGE VIEW
# ============================================================
with tab1:
    st.divider()
    
    # Show current storage
    st.subheader("Knowledge Base")
    
    try:
        docs_data = get_stored_documents()
        documents = docs_data.get("documents", [])
        
        if documents:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Documents", len(set(d.get("source_file") for d in documents)))
            with col2:
                st.metric("Chunks", len(documents))
            with col3:
                st.metric("Storage Size", f"~{len(documents) * 1.5:.1f} KB")
            
            # List documents with delete option
            st.markdown("**Uploaded Files:**")
            
            unique_files = {}
            for doc in documents:
                fname = doc.get("source_file", "Unknown")
                if fname not in unique_files:
                    unique_files[fname] = {"count": 0, "id": doc.get("id", 0)}
                unique_files[fname]["count"] += 1
            
            for idx, (fname, info) in enumerate(unique_files.items()):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.caption(f"{fname}")
                with col2:
                    st.caption(f"{info['count']} chunks")
                with col3:
                    if st.button("Delete", key=f"del_{idx}", help="Delete this document"):
                        success, msg = delete_document(fname)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
        else:
            st.info("No documents uploaded yet. Start by uploading files in the Ingest Documents tab.")
    
    except Exception as e:
        st.error(f"Could not load storage info: {str(e)}")
    
    st.divider()
    
    # Chat interface
    st.subheader("Ask a Question")
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        query = st.text_input(
            "Your question:",
            placeholder="What is this document about?",
            label_visibility="collapsed",
            key="query_input"
        )
    
    with col2:
        top_k = st.selectbox(
            "Results:",
            options=[3, 5, 7, 10],
            index=1,
            label_visibility="collapsed"
        )
    
    # Search button
    search_button = st.button("Search", type="primary", use_container_width=False)
    
    if search_button:
        if query:
            with st.spinner("Searching your documents..."):
                try:
                    response = requests.post(
                        f"{API_URL}/search",
                        json={"query": query, "top_k": top_k},
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Display answer
                        st.divider()
                        st.subheader("Answer")
                        st.write(result.get('answer', 'No answer found.'))
                        
                        # Display sources
                        if result.get("sources"):
                            st.subheader("Sources")
                            for i, src in enumerate(result["sources"], 1):
                                score = src.get("score", 0)
                                text = src.get("text", "")[:250]
                                relevance = "High" if score > 0.8 else "Medium" if score > 0.6 else "Low"
                                
                                with st.expander(f"Source {i} - {relevance} relevance (similarity: {score:.2%})", expanded=(i==1)):
                                    st.write(text + "...")
                    else:
                        st.error(f"API Error: {response.status_code}")
                        if response.text:
                            st.code(response.text)
                
                except requests.exceptions.ConnectionError:
                    st.error("Cannot connect to API. Ensure FastAPI server is running on port 8001.")
                except requests.exceptions.Timeout:
                    st.error("Request timed out. Try with fewer results or a shorter question.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        else:
            st.warning("Please enter a question.")

# ============================================================
# TAB 2: INGEST DOCUMENTS
# ============================================================
with tab2:
    st.divider()
    st.subheader("Ingest Documents")
    st.caption("Supported formats: PDF, TXT, Markdown")
    
    st.divider()
    
    # File uploader
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["pdf", "txt", "md"],
        accept_multiple_files=False,
        label_visibility="collapsed"
    )
    
    if uploaded_file:
        st.info(f"File: `{uploaded_file.name}` ({uploaded_file.size / 1024:.1f} KB)")
        
        if st.button("Upload", type="primary", use_container_width=True):
            with st.spinner("Processing and storing..."):
                try:
                    # Determine content type
                    content_type = "application/pdf" if uploaded_file.name.endswith('.pdf') else "text/plain"
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), content_type)}
                    
                    response = requests.post(
                        f"{API_URL}/ingest/pdf",
                        files=files,
                        timeout=120
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        chunks = result.get('chunks', 0)
                        st.success(f"Successfully ingested {chunks} chunks from `{uploaded_file.name}`")
                        st.cache_data.clear()
                        st.balloons()
                        
                        # Show chunk preview
                        with st.expander("Storage Details"):
                            st.json({
                                "file": result.get("file"),
                                "chunks_created": chunks,
                                "chunk_ids_sample": result.get("ids", [])[:3]
                            })
                    else:
                        st.error(f"Upload failed: {response.status_code}")
                        if response.text:
                            st.code(response.text, language="json")
                
                except requests.exceptions.ConnectionError:
                    st.error("Cannot connect to API. Ensure FastAPI server is running on port 8001.")
                except requests.exceptions.Timeout:
                    st.error("Upload timed out. File may be too large.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    else:
        st.info("Select a file to upload. Drag and drop or click to browse.")
    
    # System Architecture section
    st.divider()
    st.subheader("System Architecture")
    
    health = get_health_info()
    
    if health:
        try:
            # Processing pipeline
            st.markdown("**Processing Pipeline:**")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                embedding_model = health.get("embedding_model", "Unknown").split("/")[-1]
                st.metric("Embeddings", embedding_model)
            with col2:
                st.metric("Vector DB", "Qdrant")
            with col3:
                llm_model = health.get("llm_model", "Unknown").split("/")[-1]
                st.metric("LLM", llm_model)
            with col4:
                st.metric("Dimension", f"{health.get('dimension', '?')}D")
            
            st.divider()
            
            # Tech stack
            st.markdown("**Technology Stack:**")
            tech_info = {
                "PDF Processing": "LlamaIndex",
                "Text Embedding": health.get("embedding_provider", "Unknown"),
                "Vector Storage": "Qdrant (HNSW indexing)",
                "Vector Search": "Cosine Similarity",
                "LLM Provider": "Groq API",
                "Backend": "FastAPI + Uvicorn",
                "Frontend": "Streamlit",
                "Event Scheduling": "Inngest",
                "Chunking": "LlamaIndex SentenceSplitter"
            }
            
            col1, col2 = st.columns(2)
            
            items = list(tech_info.items())
            for i, (key, value) in enumerate(items):
                if i % 2 == 0:
                    with col1:
                        st.caption(f"**{key}:** {value}")
                else:
                    with col2:
                        st.caption(f"**{key}:** {value}")
        
        except Exception as e:
            st.error(f"Error displaying system info: {str(e)}")
    
    else:
        with st.expander("System Architecture (Click to expand)", expanded=False):
            st.warning("Cannot fetch live system info, but here's the architecture:")
            
            st.markdown("**Processing Pipeline:**")
            st.caption("Embeddings: HuggingFace")
            st.caption("Vector DB: Qdrant")
            st.caption("LLM: Groq API")
            st.caption("Dimension: 384D")
            
            st.divider()
            
            st.markdown("**Technology Stack:**")
            tech_info = {
                "PDF Processing": "LlamaIndex",
                "Text Embedding": "HuggingFace Transformers",
                "Vector Storage": "Qdrant (HNSW indexing)",
                "Vector Search": "Cosine Similarity",
                "LLM Provider": "Groq API",
                "Backend": "FastAPI + Uvicorn",
                "Frontend": "Streamlit",
                "Event Scheduling": "Inngest",
                "Chunking": "LlamaIndex SentenceSplitter"
            }
            
            col1, col2 = st.columns(2)
            
            items = list(tech_info.items())
            for i, (key, value) in enumerate(items):
                if i % 2 == 0:
                    with col1:
                        st.caption(f"**{key}:** {value}")
                else:
                    with col2:
                        st.caption(f"**{key}:** {value}")
