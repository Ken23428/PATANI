# app.py

import os
import fitz  # PyMuPDF
from langchain.text_splitter import CharacterTextSplitter
from langchain.schema import Document
import faiss
import numpy as np
import google.generativeai as genai
import traceback
import re
from flask import Flask, render_template, request, jsonify, send_from_directory

# --- Inisialisasi Aplikasi Flask ---
app = Flask(__name__)

# --- Konfigurasi dan Variabel Global ---
# Pastikan GOOGLE_API_KEY sudah diatur di environment Anda
# genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

DOWNLOAD_FOLDER = 'data_nilam'
faiss_index = None
doc_chunks = None
model_gen = None

# --- Fungsi Helper RAG ---
def extract_text_from_pdf(file_path):
    # Dapatkan nama file asli untuk tautan unduhan
    original_filename = os.path.basename(file_path)
    paper_title = original_filename # Default
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
                    # Simpan judul DAN nama file asli di metadata
                    doc_pages.append(Document(
                        page_content=page_text, 
                        metadata={
                            "title": paper_title, 
                            "filename": original_filename,
                            "page": page_num + 1
                        }
                    ))
            return doc_pages
    except Exception as e:
        print(f"⚠️ Gagal membaca file {original_filename}: {e}")
        return []

def get_doc_embeddings(texts):
    try:
        result = genai.embed_content(model="models/embedding-001", content=texts, task_type="retrieval_document")
        return [np.array(emb) for emb in result['embedding']]
    except Exception as e:
        return [None] * len(texts)

def get_query_embedding(text):
    try:
        result = genai.embed_content(model="models/embedding-001", content=text, task_type="retrieval_query")
        return np.array(result['embedding'])
    except Exception as e:
        return None

# --- Fungsi Inisialisasi RAG ---
def initialize_rag_system():
    global faiss_index, doc_chunks, model_gen
    print(f"Menginisialisasi sistem RAG dari folder: {DOWNLOAD_FOLDER}...")
    pdf_files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) if f.lower().endswith('.pdf')]
    if not pdf_files: raise FileNotFoundError(f"Tidak ada file PDF di folder '{DOWNLOAD_FOLDER}'.")
    
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
    if not valid_embeddings: raise ValueError("Gagal membuat embedding.")
    
    dimension = valid_embeddings[0].shape[0]
    faiss_index = faiss.IndexFlatL2(dimension)
    faiss_index.add(np.array(valid_embeddings).astype('float32'))
    model_gen = genai.GenerativeModel("gemini-2.5-flash")
    print("✅ Sistem RAG siap digunakan.")


# --- Rute Flask ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_question = data['message']
        conversation_history = data.get('history', [])

        query_embedding = get_query_embedding(user_question)
        if query_embedding is None:
            return jsonify({'reply': "Maaf, terjadi masalah saat memproses pertanyaan Anda."})

        k = 5
        distances, indices = faiss_index.search(np.array([query_embedding]).astype('float32'), k)
        
        # Kumpulkan konteks dan sumber unik
        konteks_list = []
        unique_sources = {} # Gunakan dictionary untuk menghindari duplikat
        for i in indices[0]:
            if i != -1:
                chunk = doc_chunks[i]
                konteks_list.append(chunk.page_content)
                title = chunk.metadata['title']
                filename = chunk.metadata['filename']
                if title not in unique_sources:
                    unique_sources[title] = filename

        konteks = "\n\n---\n\n".join(konteks_list)
        formatted_history = "".join([f"Petani: {turn['user']}\nAsisten: {turn['bot']}\n\n" for turn in conversation_history])

        # Prompt yang lebih sederhana
        prompt_rag = f"""
        ## PERAN DAN TUJUAN
        Anda adalah "Penyuluh Pertanian Digital," seorang asisten AI ahli. Jawab pertanyaan petani berdasarkan konteks yang diberikan dengan bahasa yang jelas dan praktis.

        ## ATURAN
        - Jawaban HARUS 100% berdasarkan pada "KONTEKS".
        - Jangan menyebutkan "berdasarkan konteks". Langsung saja berikan jawabannya.
        - Jika informasi tidak ada, katakan "Maaf, informasi tersebut tidak ditemukan dalam dokumen saya."
        
        ---
        ## RIWAYAT PERCAKAPAN
        {formatted_history}
        ---
        ## KONTEKS DARI DOKUMEN PENELITIAN
        {konteks}
        ---
        ## PERTANYAAN TERBARU DARI PETANI
        {user_question}
        ---
        ## JAWABAN PRAKTIS
        """
        
        response = model_gen.generate_content(prompt_rag)
        
        # Kirim jawaban DAN daftar sumber ke frontend
        sources_for_frontend = [{"title": title, "filename": filename} for title, filename in unique_sources.items()]
        
        return jsonify({'reply': response.text, 'sources': sources_for_frontend})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'reply': "Terjadi error di server. Silakan coba lagi."}), 500

# Rute baru untuk mengunduh file
@app.route('/download/<path:filename>')
def download_file(filename):
    """Menyajikan file dari folder data_nilam untuk diunduh."""
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)


# --- Jalankan Aplikasi ---
if __name__ == '__main__':
    initialize_rag_system()
    app.run(debug=True, port=5000)