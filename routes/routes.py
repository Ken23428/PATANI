from flask import request, render_template, redirect, url_for, jsonify, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from .models import db, User, Pengaduan
from .rag_core import initialize_rag_system
from datetime import datetime
import os
from flask import request, render_template, redirect, url_for, jsonify, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from .rag_core import *
import traceback
from datetime import datetime
from flask import make_response
from werkzeug.utils import secure_filename
from flask_caching import Cache
import hashlib

# --- Konfigurasi Folder Upload ---
UPLOAD_FOLDER = 'D:/ProjectGemastik/AgroLLM/uploads'  # folder uploads di root, bukan di static/
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# --- Fungsi untuk memeriksa apakah file yang diupload diperbolehkan ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Membuat folder 'uploads' jika belum ada ---
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def register_routes(app):
    # Initialize cache
    cache = Cache(app)

    @app.route('/')
    def home():
        return redirect(url_for('index')) if 'user_id' in session else redirect(url_for('login'))

    @app.route('/index')
    def index():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return render_template('index.html', user=session.get('user_name'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if 'user_id' in session:
            return redirect(url_for('index'))
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password, password):
                session['user_id'] = user.id
                session['user_name'] = user.name
                session['is_admin'] = user.role in ['admin', 'superadmin']
                session['user_role'] = user.role
                session['admin_region'] = user.region
                if user.role == 'superadmin':
                    return redirect(url_for('superadmin_dashboard'))
                elif user.role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('index'))
            else:
                return render_template('login.html', error="Email atau password salah.")
        return render_template('login.html')

    @app.route('/daftar', methods=['GET', 'POST'])
    def daftar_petani():
        if 'user_id' in session:
            return redirect(url_for('index'))
        if request.method == 'POST':
            data = request.form
            if User.query.filter_by(email=data['email']).first():
                return render_template('daftar.html', error="Email sudah terdaftar.")
            user = User(
                name=data['name'],
                dob=datetime.strptime(data['dob'], '%Y-%m-%d'),
                gender=data['gender'],
                email=data['email'],
                phone=data['phone'],
                password=generate_password_hash(data['password']),
                role='petani'
            )
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login'))
        return render_template('daftar.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/admin/dashboard')
    @cache.cached(timeout=60)  # Cache for 1 minute
    def admin_dashboard():
        if not session.get('is_admin'):
            return redirect(url_for('login'))

        # Jika yang login adalah superadmin, alihkan ke dashboard superadmin
        if session.get('user_role') == 'superadmin':
            return redirect(url_for('superadmin_dashboard'))

        # Ambil data wilayah admin Pemda yang login
        admin_region = session.get('admin_region')
        
        # Optimize database queries with eager loading
        complaints = Pengaduan.query.filter_by(region=admin_region).order_by(Pengaduan.created_at.desc()).limit(10).all()
        
        # Get counts efficiently
        total_complaints = Pengaduan.query.filter_by(region=admin_region).count()
        pending_complaints = Pengaduan.query.filter_by(region=admin_region, status='pending').count()
        processed_complaints = Pengaduan.query.filter_by(region=admin_region, status='processed').count()
        
        return render_template('admin_dashboard.html', 
                             complaints=complaints,
                             total_complaints=total_complaints,
                             pending_complaints=pending_complaints,
                             processed_complaints=processed_complaints)

    @app.route('/superadmin/monitoring')
    @cache.cached(timeout=60)  # Cache for 1 minute
    def superadmin_monitoring():
        if not session.get('is_admin') or session.get('user_role') != 'superadmin':
            return redirect(url_for('login'))

        # Optimize database queries
        complaints = Pengaduan.query.order_by(Pengaduan.created_at.desc()).limit(20).all()
        
        # Get statistics efficiently
        total_complaints = Pengaduan.query.count()
        pending_complaints = Pengaduan.query.filter_by(status='pending').count()
        processed_complaints = Pengaduan.query.filter_by(status='processed').count()
        
        # Get user statistics
        total_users = User.query.count()
        total_petani = User.query.filter_by(role='petani').count()
        total_admin = User.query.filter_by(role='admin').count()
        
        return render_template('superadmin_monitoring.html',
                             complaints=complaints,
                             total_complaints=total_complaints,
                             pending_complaints=pending_complaints,
                             processed_complaints=processed_complaints,
                             total_users=total_users,
                             total_petani=total_petani,
                             total_admin=total_admin)

    @app.route('/superadmin/dashboard', methods=['GET', 'POST'])
    def superadmin_dashboard():
        if not session.get('is_admin') or session.get('user_role') != 'superadmin':
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            # Handle admin creation
            data = request.form
            if User.query.filter_by(email=data['email']).first():
                flash('Email sudah terdaftar.', 'error')
            else:
                user = User(
                    name=data['name'],
                    email=data['email'],
                    phone=data['phone'],
                    password=generate_password_hash(data['password']),
                    role='admin',
                    region=data['region']
                )
                db.session.add(user)
                db.session.commit()
                flash('Admin berhasil ditambahkan.', 'success')
        
        # Get admin list efficiently
        admins = User.query.filter_by(role='admin').all()
        return render_template('superadmin_dashboard.html', admins=admins)

    @app.route('/admin/complaint/<int:complaint_id>/update', methods=['POST'])
    def update_complaint_status(complaint_id):
        if not session.get('is_admin'):
            return redirect(url_for('login'))
        
        complaint = Pengaduan.query.get_or_404(complaint_id)
        complaint.status = request.form['status']
        complaint.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Clear cache for dashboard
        cache.delete_memoized(admin_dashboard)
        cache.delete_memoized(superadmin_monitoring)
        
        flash('Status pengaduan berhasil diperbarui.', 'success')
        return redirect(url_for('admin_dashboard'))

    @app.route('/pengaduan', methods=['GET', 'POST'])
    def form_pengaduan():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            user = User.query.get(session['user_id'])
            data = request.form
            
            # Handle file upload more efficiently
            file_upload = None
            if 'file_upload' in request.files:
                file = request.files['file_upload']
                if file and allowed_file(file.filename):
                    # Store file path instead of binary data for better performance
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(file_path)
                    file_upload = filename  # Store filename instead of binary data
            
            complaint = Pengaduan(
                user_id=user.id,
                name=data['name'],
                email=data['email'],
                phone=data['phone'],
                address=data['address'],
                region=data['region'],
                category=data['category'],
                problem_description=data['problem_description'],
                severity=data['severity'],
                file_upload=file_upload,  # Store filename
                incident_date=datetime.strptime(data['incident_date'], '%Y-%m-%d'),
                actions_taken=data['actions_taken'],
                follow_up_request=data['follow_up_request'],
                data_consent=data.get('data_consent') == 'on',
                data_accuracy=data.get('data_accuracy') == 'on'
            )
            
            db.session.add(complaint)
            db.session.commit()
            
            flash('Pengaduan berhasil dikirim.', 'success')
            return redirect(url_for('riwayat_pengaduan'))
        
        return render_template('pengaduan.html')

    @app.route('/riwayat_pengaduan')
    def riwayat_pengaduan():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        # Optimize query with pagination
        page = request.args.get('page', 1, type=int)
        per_page = 10
        
        complaints = Pengaduan.query.filter_by(user_id=session['user_id'])\
                                   .order_by(Pengaduan.created_at.desc())\
                                   .paginate(page=page, per_page=per_page, error_out=False)
        
        return render_template('riwayat_pengaduan.html', complaints=complaints)

    @app.route('/chat', methods=['POST'])
    def chat():
        if not hasattr(thread_local, 'faiss_index'):
            initialize_rag_system()
            if not hasattr(thread_local, 'faiss_index'):
                return jsonify({'reply': "Sistem belum siap digunakan. Silakan coba lagi nanti."})

        try:
            data = request.get_json()
            user_question = data['message']
            history = data.get('history', [])
            
            # Create cache key for this query
            cache_key = hashlib.md5(f"{user_question}_{str(history)}".encode()).hexdigest()
            
            # Check cache first
            cached_response = cache.get(cache_key)
            if cached_response:
                return jsonify(cached_response)
            
            query_embedding = get_query_embedding(user_question)

            if query_embedding is None:
                return jsonify({'reply': "Sistem belum siap digunakan. Silakan coba lagi nanti."})

            faiss_index = thread_local.faiss_index
            doc_chunks = thread_local.doc_chunks
            model_gen = thread_local.model_gen

            distances, indices = faiss_index.search(np.array([query_embedding]).astype('float32'), 5)
            context_chunks, unique_sources = [], {}

            for i in indices[0]:
                if i != -1:
                    chunk = doc_chunks[i]
                    context_chunks.append(chunk.page_content)
                    title = chunk.metadata['title']
                    filename = chunk.metadata['filename']
                    unique_sources[title] = filename

            context = "\n\n---\n\n".join(context_chunks)
            chat_history = "".join([f"Petani: {turn['user']}\nAsisten: {turn['bot']}\n\n" for turn in history])

            prompt = f"""
            ## PERAN DAN TUJUAN
            Anda adalah "Penyuluh Pertanian Digital," seorang asisten AI ahli. Jawab pertanyaan petani berdasarkan konteks yang diberikan dengan bahasa yang jelas dan praktis.

            ## ATURAN
            - Jawaban HARUS 100% berdasarkan pada "KONTEKS".
            - Jangan menyebutkan "berdasarkan konteks". Langsung saja berikan jawabannya.
            - Jika informasi tidak ada, katakan "Maaf, informasi tersebut tidak ditemukan dalam dokumen saya."

            ---
            ## RIWAYAT PERCAKAPAN
            {chat_history}
            ---
            ## KONTEKS DARI DOKUMEN PENELITIAN
            {context}
            ---
            ## PERTANYAAN TERBARU DARI PETANI
            {user_question}
            ---
            ## JAWABAN PRAKTIS
            """

            response = model_gen.generate_content(prompt)
            result = {'reply': response.text, 'sources': [{"title": k, "filename": v} for k, v in unique_sources.items()]}
            
            # Cache the response for 5 minutes
            cache.set(cache_key, result, timeout=300)
            
            return jsonify(result)
        except Exception:
            print(traceback.format_exc())
            return jsonify({'reply': "Terjadi error di server. Silakan coba lagi."}), 500

    @app.route('/file/<int:complaint_id>')
    def display_file(complaint_id):
        complaint = Pengaduan.query.get(complaint_id)
        if complaint and complaint.file_upload:
            # Serve file from filesystem instead of database
            return send_from_directory(UPLOAD_FOLDER, complaint.file_upload)
        return "File tidak ditemukan", 404

    @app.route('/pengaduan/<int:complaint_id>/delete', methods=['POST'])
    def delete_complaint(complaint_id):
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])
        complaint = Pengaduan.query.get(complaint_id)

        # Pastikan pengguna hanya bisa menghapus pengaduan mereka sendiri
        if complaint and complaint.user_id == user.id:
            # Delete file if exists
            if complaint.file_upload:
                try:
                    file_path = os.path.join(UPLOAD_FOLDER, complaint.file_upload)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
            
            db.session.delete(complaint)
            db.session.commit()
            flash('Pengaduan berhasil dihapus.', 'success')
        else:
            flash('Anda tidak memiliki izin untuk menghapus pengaduan ini.', 'error')

        return redirect(url_for('riwayat_pengaduan'))

    @app.route('/profil', methods=['GET', 'POST'])
    def profil():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        
        if request.method == 'POST':
            # Handle profile photo upload
            if 'profile_pic' in request.files:
                file = request.files['profile_pic']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(file_path)
                    user.profile_pic = filename
            
            # Update other fields
            user.name = request.form['name']
            user.phone = request.form['phone']
            
            db.session.commit()
            session['user_name'] = user.name
            flash('Profil berhasil diperbarui.', 'success')
            return redirect(url_for('profil'))
        
        return render_template('profil.html', user=user)

    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(UPLOAD_FOLDER, filename)

    @app.route('/profil/delete_photo', methods=['POST'])
    def delete_photo():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if user.profile_pic:
            try:
                file_path = os.path.join(UPLOAD_FOLDER, user.profile_pic)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            user.profile_pic = None
            db.session.commit()
            flash('Foto profil berhasil dihapus.', 'success')
        
        return redirect(url_for('profil'))

    @app.route('/init-db')
    def init_db():
        db.create_all()
        return "Database initialized!"

    @app.route('/drop-db')
    def drop_db():
        db.drop_all()
        return "Database dropped!"
