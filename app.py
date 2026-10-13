"""
Production RAG System - Streamlit Frontend
Warm linen aesthetic with figtree typography.
"""
import streamlit as st
import requests
import json
from pathlib import Path

# ============================================================
# CONFIG & STYLING
# ============================================================
API_URL = "http://localhost:8001"

st.set_page_config(
    page_title="Wally - RAG Chat",
    page_icon="�",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Warm linen theme with figtree font
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap');

* {
    font-family: 'Figtree', sans-serif !important;
}

:root {
    --warm-white: #f5ece0;
    --linen: #ede4d3;
    --warm-tan: #dcc8b6;
    --accent-brown: #8b7355;
    --accent-gold: #d4a574;
}

body, [data-testid="stAppViewContainer"] {
    background-color: #f5ece0 !important;
    color: #3a3a3a !important;
}

[data-testid="stMain"] {
    background-color: #f5ece0 !important;
}

h1, h2, h3, h4, h5, h6 {
    color: #5a4a3a !important;
    font-weight: 600 !important;
}

.stButton > button {
    background: linear-gradient(135deg, #d4a574 0%, #c19563 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.3s ease !important;
}

.stButton > button:hover {
    background: linear-gradient(135deg, #c19563 0%, #b08552 100%) !important;
    box-shadow: 0 4px 12px rgba(212, 165, 116, 0.3) !important;
}

.stTextInput > div > div > input {
    background-color: #fff !important;
    border: 2px solid #dcc8b6 !important;
    border-radius: 8px !important;
    color: #3a3a3a !important;
    font-family: 'Figtree', sans-serif !important;
}

.stTextInput > div > div > input:focus {
    border-color: #d4a574 !important;
    box-shadow: 0 0 0 2px rgba(212, 165, 116, 0.1) !important;
}

[data-testid="stTabs"] [role="tablist"] button {
    color: #5a4a3a !important;
    font-weight: 600 !important;
    background: transparent !important;
    border-bottom: 3px solid transparent !important;
    border-radius: 0 !important;
}

[data-testid="stTabs"] [role="tablist"] button[aria-selected="true"] {
    border-bottom: 3px solid #d4a574 !important;
    color: #d4a574 !important;
}

.stExpander {
    background-color: #fff !important;
    border: 1px solid #dcc8b6 !important;
    border-radius: 8px !important;
}

[data-testid="stExpanderDetails"] {
    background-color: #faf7f2 !important;
}

.stMetric {
    background-color: #fff !important;
    padding: 16px !important;
    border-radius: 8px !important;
    border: 1px solid #dcc8b6 !important;
}

.success {
    background-color: #e8f5e9 !important;
    border: 1px solid #81c784 !important;
    border-radius: 8px !important;
    padding: 12px !important;
    color: #2e7d32 !important;
}

.error {
    background-color: #ffebee !important;
    border: 1px solid #e57373 !important;
    border-radius: 8px !important;
    padding: 12px !important;
    color: #c62828 !important;
}

.info-box {
    background-color: #fff !important;
    border-left: 4px solid #d4a574 !important;
    padding: 16px !important;
    border-radius: 4px !important;
    margin: 16px 0 !important;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# HELPER FUNCTIONS
# ============================================================

@st.cache_resource
def get_storage_info():
    """Fetch storage info from API"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

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
st.markdown("<div style='text-align: center; padding: 20px 0;'><h1 style='color: #5a4a3a;'>📚 Wally</h1><p style='color: #8b7355; font-size: 16px; font-weight: 500;'>Your documents, smarter. Ask anything.</p></div>", unsafe_allow_html=True)

# ============================================================
# TABS
# ============================================================
tab1, tab2 = st.tabs(["💬 Ask Questions", "📤 Upload Documents"])

# ============================================================
# TAB 1: CHAT & STORAGE VIEW
# ============================================================
with tab1:
    st.markdown("---")
    
    # Show current storage
    st.subheader("📖 Your Knowledge Base")
    
    try:
        docs_data = get_stored_documents()
        documents = docs_data.get("documents", [])
        
        if documents:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("📄 Documents", len(set(d.get("source_file") for d in documents)))
            with col2:
                st.metric("📑 Chunks", len(documents))
            with col3:
                st.metric("💾 Storage Size", f"~{len(documents) * 1.5:.1f} KB")
            
            # List documents with delete option
            st.markdown("**Uploaded Files:**")
            
            col1, col2, col3 = st.columns([3, 1, 1])
            
            unique_files = {}
            for doc in documents:
                fname = doc.get("source_file", "Unknown")
                if fname not in unique_files:
                    unique_files[fname] = {"count": 0, "id": doc.get("id", 0)}
                unique_files[fname]["count"] += 1
            
            for idx, (fname, info) in enumerate(unique_files.items()):
                with col1:
                    st.caption(f"📄 {fname}")
                with col2:
                    st.caption(f"{info['count']} chunks")
                with col3:
                    if st.button("🗑️", key=f"del_{idx}", help="Delete this document"):
                        success, msg = delete_document(fname)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
        else:
            st.info("📭 No documents uploaded yet. Start by uploading files in the 'Upload Documents' tab.")
    
    except Exception as e:
        st.error(f"Could not load storage info: {str(e)}")
    
    st.markdown("---")
    
    # Chat interface
    st.subheader("💬 Ask a Question")
    
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
    
    # Search button with enter key support
    search_button = st.button("🔍 Search", type="primary", use_container_width=False)
    
    if search_button or query:
        if query and search_button:
            with st.spinner("🔍 Searching your documents..."):
                try:
                    response = requests.post(
                        f"{API_URL}/search",
                        json={"query": query, "top_k": top_k},
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Display answer
                        st.markdown("---")
                        st.markdown("### ✨ Answer")
                        st.markdown(f"<div style='background-color: #fff; padding: 16px; border-radius: 8px; border-left: 4px solid #d4a574;'>{result.get('answer', 'No answer found.')}</div>", unsafe_allow_html=True)
                        
                        # Display sources
                        if result.get("sources"):
                            st.markdown("### 📚 Sources")
                            for i, src in enumerate(result["sources"], 1):
                                score = src.get("score", 0)
                                text = src.get("text", "")[:250]
                                relevance = "🟢 High" if score > 0.8 else "🟡 Medium" if score > 0.6 else "🔴 Low"
                                
                                with st.expander(f"{relevance} · Source {i} (similarity: {score:.2%})", expanded=(i==1)):
                                    st.write(text + "...")
                    else:
                        st.error(f"❌ API Error: {response.status_code}")
                        if response.text:
                            st.code(response.text)
                
                except requests.exceptions.ConnectionError:
                    st.error("❌ Cannot connect to API. Ensure FastAPI server is running on port 8001.")
                except requests.exceptions.Timeout:
                    st.error("⏱️ Request timed out. Try with fewer results or a shorter question.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

# ============================================================
# TAB 2: UPLOAD DOCUMENTS
# ============================================================
with tab2:
    st.markdown("---")
    st.subheader("📤 Upload Documents")
    st.caption("Supported formats: PDF, TXT, Markdown")
    
    st.markdown("---")
    
    # File uploader
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["pdf", "txt", "md"],
        accept_multiple_files=False,
        label_visibility="collapsed"
    )
    
    if uploaded_file:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.info(f"📄 File: `{uploaded_file.name}` ({uploaded_file.size / 1024:.1f} KB)")
        
        with col2:
            if st.button("📤 Upload", type="primary", use_container_width=True):
                with st.spinner("🔄 Processing and storing..."):
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
                            st.success(f"✅ Successfully ingested **{chunks} chunks** from `{uploaded_file.name}`")
                            st.cache_data.clear()
                            st.balloons()
                            
                            # Show chunk preview
                            with st.expander("📊 Storage Details"):
                                st.json({
                                    "file": result.get("file"),
                                    "chunks_created": chunks,
                                    "chunk_ids_sample": result.get("ids", [])[:3]
                                })
                        else:
                            st.error(f"❌ Upload failed: {response.status_code}")
                            if response.text:
                                st.code(response.text, language="json")
                    
                    except requests.exceptions.ConnectionError:
                        st.error("❌ Cannot connect to API. Ensure FastAPI server is running on port 8001.")
                    except requests.exceptions.Timeout:
                        st.error("⏱️ Upload timed out. File may be too large.")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
    
    else:
        st.info("👆 Select a file to upload. Drag and drop or click to browse.")
    
    # System info
    st.markdown("---")
    st.markdown("### ℹ️ System Info")
    
    try:
        health = requests.get(f"{API_URL}/health", timeout=5).json()
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("🧠 Embeddings", health.get("embedding_model", "Unknown").split("/")[-1])
        with col2:
            st.metric("⚡ LLM", health.get("llm_model", "Unknown").split("/")[-1])
        with col3:
            st.metric("📊 Dimension", f"{health.get('dimension', '?')}D")
    
    except:
        st.warning("Could not fetch system info.")