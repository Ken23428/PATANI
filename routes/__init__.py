from flask import request, render_template, redirect, url_for, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from .rag_core import *  # Mengimpor fungsi dari rag_core untuk inisialisasi sistem RAG
import traceback
from datetime import datetime

User = None
Complaint = None

def register_routes(app, database):
    global User, Complaint

    # Definisikan model User
    class User(database.Model):
        id = database.Column(database.Integer, primary_key=True)
        name = database.Column(database.String(100), nullable=False)
        email = database.Column(database.String(100), nullable=False, unique=True)
        phone = database.Column(database.String(20), nullable=False)
        province = database.Column(database.String(100), nullable=False)
        district = database.Column(database.String(100), nullable=False)
        address = database.Column(database.Text, nullable=True)
        password = database.Column(database.String(256), nullable=False)
        role = database.Column(database.String(20), default='petani')
        created_at = database.Column(database.DateTime, default=datetime.utcnow)

    # Definisikan model Complaint
    class Complaint(database.Model):
        id = database.Column(database.Integer, primary_key=True)
        user_id = database.Column(database.Integer, database.ForeignKey('user.id'), nullable=False)
        message = database.Column(database.Text, nullable=False)
        status = database.Column(database.String(20), default='pending')
        created_at = database.Column(database.DateTime, default=datetime.utcnow)
        village = database.Column(database.String(100), nullable=False)
        subdistrict = database.Column(database.String(100), nullable=False)
        regency = database.Column(database.String(100), nullable=False)
        user = database.relationship('User', backref=database.backref('complaints', lazy=True))

    # Route untuk halaman utama atau login
    @app.route('/')
    def home():
        if 'user_id' in session:
            return redirect(url_for('index'))  # Jika sudah login, langsung ke halaman utama
        return redirect(url_for('login'))  # Jika belum login, arahkan ke halaman login

    # Route untuk halaman login
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if 'user_id' in session:
            return redirect(url_for('index'))  # Jika sudah login, langsung ke halaman utama

        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password, password):
                session['user_id'] = user.id
                session['user_name'] = user.name
                session['is_admin'] = (user.role == 'admin')
                return redirect(url_for('index') if user.role != 'admin' else url_for('admin_dashboard'))
            else:
                return render_template('login.html', error="Email atau password salah.")
        
        return render_template('login.html')

    # Route untuk halaman pendaftaran
    @app.route('/daftar', methods=['GET', 'POST'])
    def daftar_petani():
        if 'user_id' in session:
            return redirect(url_for('index'))  # Jika sudah login, kembali ke halaman utama

        if request.method == 'POST':
            data = request.form
            existing_user = User.query.filter_by(email=data['email']).first()
            if existing_user:
                return render_template('daftar.html', error="Email sudah terdaftar.")
            user = User(
                name=data['name'], email=data['email'], phone=data['phone'],
                province=data['province'], district=data['district'],
                address=data['address'], password=generate_password_hash(data['password']),
                role='petani')
            database.session.add(user)
            database.session.commit()
            return redirect(url_for('login'))  # Setelah mendaftar, kembali ke halaman login
        return render_template('daftar.html')

    # Route untuk halaman utama setelah login
    @app.route('/index')
    def index():
        if 'user_id' not in session:
            return redirect(url_for('login'))  # Jika belum login, kembali ke halaman login
        
        return render_template('index.html', user=session.get('user_name'))

    # Route untuk halaman logout
    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    # Route untuk dashboard admin
    @app.route('/admin/dashboard')
    def admin_dashboard():
        if not session.get('is_admin'):
            return redirect(url_for('login'))
        complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
        return render_template('admin_dashboard.html', complaints=complaints)

    # Route untuk update status pengaduan
    @app.route('/admin/complaint/<int:complaint_id>/update', methods=['POST'])
    def update_complaint_status(complaint_id):
        if not session.get('is_admin'):
            return redirect(url_for('login'))

        new_status = request.form.get('status')
        complaint = Complaint.query.get(complaint_id)
        if complaint:
            complaint.status = new_status
            database.session.commit()
        return redirect(url_for('admin_dashboard'))
    
    
    

    @app.route('/chat', methods=['POST'])
    def chat():
        global faiss_index, doc_chunks, model_gen

        # Pastikan faiss_index, doc_chunks, dan model_gen terinisialisasi
        if not hasattr(thread_local, 'faiss_index') or not hasattr(thread_local, 'doc_chunks') or not hasattr(thread_local, 'model_gen'):
            # Inisialisasi sistem jika belum
            initialize_rag_system()  # Memanggil fungsi inisialisasi
            
            # Periksa lagi jika setelah inisialisasi masih None
            if not hasattr(thread_local, 'faiss_index') or not hasattr(thread_local, 'doc_chunks') or not hasattr(thread_local, 'model_gen'):
                return jsonify({'reply': "Sistem belum siap digunakan. Silakan coba lagi nanti."})
        
        faiss_index = thread_local.faiss_index
        doc_chunks = thread_local.doc_chunks
        model_gen = thread_local.model_gen

        try:
            data = request.get_json()
            user_question = data['message']
            conversation_history = data.get('history', [])
            query_embedding = get_query_embedding(user_question)

            if query_embedding is None or faiss_index is None:
                return jsonify({'reply': "Sistem belum siap digunakan. Silakan coba lagi nanti."})

            k = 5
            distances, indices = faiss_index.search(np.array([query_embedding]).astype('float32'), k)
            konteks_list, unique_sources = [], {}

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
            return jsonify({'reply': response.text, 'sources': [{"title": k, "filename": v} for k, v in unique_sources.items()]})
        
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'reply': "Terjadi error di server. Silakan coba lagi."}), 500


    # Route untuk inisialisasi database
    @app.route('/init-db')
    def init_db():
        database.create_all()
        return "✅ Database initialized!"

    # Route untuk menghapus semua tabel di database
    @app.route('/drop-db')
    def drop_db():
        database.drop_all()
        return "✅ Semua tabel dihapus."

    # Route untuk mengajukan pengaduan
    @app.route('/pengaduan', methods=['GET', 'POST'])
    def form_pengaduan():
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])

        if request.method == 'POST':
            message = request.form['message']
            village = request.form['village']
            subdistrict = request.form['subdistrict']
            regency = request.form['regency']

            new_complaint = Complaint(
                user_id=user.id,
                message=message,
                village=village,
                subdistrict=subdistrict,
                regency=regency,
            )
            database.session.add(new_complaint)
            database.session.commit()
            return render_template('pengaduan.html', success=True)

        return render_template('pengaduan.html')
    
    # Route untuk halaman riwayat pengaduan
    @app.route('/riwayat_pengaduan')
    def riwayat_pengaduan():
        if 'user_id' not in session:
            return redirect(url_for('login'))  # Jika belum login, kembali ke halaman login

        user = User.query.get(session['user_id'])
        complaints = Complaint.query.filter_by(user_id=user.id).order_by(Complaint.created_at.desc()).all()

        return render_template('riwayat_pengaduan.html', complaints=complaints)

