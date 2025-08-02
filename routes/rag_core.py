import os
import fitz
import re
import faiss
import numpy as np
import google.generativeai as genai
from langchain.text_splitter import CharacterTextSplitter
from langchain.schema import Document
import threading
import hashlib
import pickle
from functools import lru_cache

# Membuat objek lokal untuk setiap thread
thread_local = threading.local()

DOWNLOAD_FOLDER = 'D:/ProjectGemastik/AgroLLM/jurnal_ilmiah'
CACHE_FOLDER = 'cache'

# Create cache folder if it doesn't exist
if not os.path.exists(CACHE_FOLDER):
    os.makedirs(CACHE_FOLDER)

def get_cache_path(filename):
    """Generate cache file path for embeddings"""
    return os.path.join(CACHE_FOLDER, f"{filename}.pkl")

@lru_cache(maxsize=100)
def extract_text_from_pdf(file_path):
    """Extract text from PDF with caching"""
    original_filename = os.path.basename(file_path)
    paper_title = original_filename
    
    # Check cache first
    cache_path = get_cache_path(original_filename)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        except:
            pass
    
    try:
        with fitz.open(file_path) as pdf:
            first_page = pdf[0]
            blocks = first_page.get_text("dict")["blocks"]
            font_sizes = {}
            for b in blocks:
                if 'lines' in b:
                    for l in b['lines']:
                        for s in l['spans']:
                            size = round(s['size'])
                            text = s['text'].strip()
                            if size not in font_sizes: font_sizes[size] = []
                            if len(text) > 2 and not text.isdigit():
                                font_sizes[size].append(text)
            if font_sizes:
                max_size = max(font_sizes.keys())
                potential_title = " ".join(font_sizes[max_size])
                potential_title = re.sub(r'\s+', ' ', potential_title).strip()
                if len(potential_title.split()) > 2:
                    paper_title = potential_title

            doc_pages = []
            for page_num, page in enumerate(pdf.pages()):
                page_text = page.get_text("text")
                if page_text:
                    doc_pages.append(Document(
                        page_content=page_text,
                        metadata={"title": paper_title, "filename": original_filename, "page": page_num + 1}
                    ))
            
            # Cache the result
            try:
                with open(cache_path, 'wb') as f:
                    pickle.dump(doc_pages, f)
            except:
                pass
                
            return doc_pages
    except Exception as e:
        print(f"⚠️ Gagal membaca file {original_filename}: {e}")
        return []

@lru_cache(maxsize=1000)
def get_doc_embeddings(texts):
    """Get document embeddings with caching"""
    try:
        result = genai.embed_content(model="models/embedding-001", content=texts, task_type="retrieval_document")
        return [np.array(emb) for emb in result['embedding']]
    except Exception:
        return [None] * len(texts)

@lru_cache(maxsize=1000)
def get_query_embedding(text):
    """Get query embedding with caching"""
    try:
        result = genai.embed_content(model="models/embedding-001", content=text, task_type="retrieval_query")
        return np.array(result['embedding'])
    except Exception:
        return None

def initialize_rag_system():
    """Initialize RAG system with better error handling and caching"""
    # Menyimpan data pada thread lokal
    if not hasattr(thread_local, 'faiss_index'):
        print(f"Menginisialisasi sistem RAG dari folder: {DOWNLOAD_FOLDER}...")

        # Check if we have cached FAISS index
        faiss_cache_path = os.path.join(CACHE_FOLDER, 'faiss_index.pkl')
        chunks_cache_path = os.path.join(CACHE_FOLDER, 'doc_chunks.pkl')
        
        if os.path.exists(faiss_cache_path) and os.path.exists(chunks_cache_path):
            try:
                print("Loading cached FAISS index...")
                with open(faiss_cache_path, 'rb') as f:
                    thread_local.faiss_index = pickle.load(f)
                with open(chunks_cache_path, 'rb') as f:
                    thread_local.doc_chunks = pickle.load(f)
                thread_local.model_gen = genai.GenerativeModel("gemini-2.5-flash")
                print("✅ Sistem RAG loaded from cache.")
                return
            except Exception as e:
                print(f"Failed to load cache: {e}")

        pdf_files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) if f.lower().endswith('.pdf')]
        if not pdf_files:
            print("❌ Tidak ada PDF ditemukan.")
            return

        all_documents = []
        for pdf_file in pdf_files:
            docs = extract_text_from_pdf(pdf_file)
            if docs:
                all_documents.extend(docs)
                print(f"  -> Berhasil memproses: {docs[0].metadata['title']}")

        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        doc_chunks = text_splitter.split_documents(all_documents)

        # Process embeddings in batches for better performance
        batch_size = 10
        embeddings_list = []
        for i in range(0, len(doc_chunks), batch_size):
            batch = doc_chunks[i:i+batch_size]
            batch_embeddings = get_doc_embeddings(tuple([chunk.page_content for chunk in batch]))
            embeddings_list.extend(batch_embeddings)

        valid_embeddings = [emb for emb in embeddings_list if emb is not None]

        if not valid_embeddings:
            print("❌ Gagal membuat embedding.")
            return

        dimension = valid_embeddings[0].shape[0]
        faiss_index = faiss.IndexFlatL2(dimension)
        faiss_index.add(np.array(valid_embeddings).astype('float32'))

        model_gen = genai.GenerativeModel("gemini-2.5-flash")

        # Cache the results
        try:
            with open(faiss_cache_path, 'wb') as f:
                pickle.dump(faiss_index, f)
            with open(chunks_cache_path, 'wb') as f:
                pickle.dump(doc_chunks, f)
        except Exception as e:
            print(f"Failed to cache: {e}")

        # Menyimpan pada thread lokal
        thread_local.faiss_index = faiss_index
        thread_local.doc_chunks = doc_chunks
        thread_local.model_gen = model_gen

        print("✅ Sistem RAG siap digunakan.")
    else:
        # Ambil data dari thread lokal jika sudah ada
        faiss_index = thread_local.faiss_index
        doc_chunks = thread_local.doc_chunks
        model_gen = thread_local.model_gen

