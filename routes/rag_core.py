import os
import fitz
import re
import faiss
import numpy as np
import google.generativeai as genai
from langchain.text_splitter import CharacterTextSplitter
from langchain.schema import Document
import threading

# Membuat objek lokal untuk setiap thread
thread_local = threading.local()

DOWNLOAD_FOLDER = 'D:/ProjectGemastik/AgroLLM/jurnal_ilmiah'

def extract_text_from_pdf(file_path):
    original_filename = os.path.basename(file_path)
    paper_title = original_filename
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
            return doc_pages
    except Exception as e:
        print(f"⚠️ Gagal membaca file {original_filename}: {e}")
        return []

def get_doc_embeddings(texts):
    try:
        result = genai.embed_content(model="models/embedding-001", content=texts, task_type="retrieval_document")
        return [np.array(emb) for emb in result['embedding']]
    except Exception:
        return [None] * len(texts)

def get_query_embedding(text):
    try:
        result = genai.embed_content(model="models/embedding-001", content=text, task_type="retrieval_query")
        return np.array(result['embedding'])
    except Exception:
        return None

def initialize_rag_system():
    # Menyimpan data pada thread lokal
    if not hasattr(thread_local, 'faiss_index'):
        print(f"Menginisialisasi sistem RAG dari folder: {DOWNLOAD_FOLDER}...")

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

        embeddings_list = get_doc_embeddings([chunk.page_content for chunk in doc_chunks])
        valid_embeddings = [emb for emb in embeddings_list if emb is not None]

        if not valid_embeddings:
            print("❌ Gagal membuat embedding.")
            return

        dimension = valid_embeddings[0].shape[0]
        faiss_index = faiss.IndexFlatL2(dimension)
        faiss_index.add(np.array(valid_embeddings).astype('float32'))

        model_gen = genai.GenerativeModel("gemini-2.5-flash")

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

