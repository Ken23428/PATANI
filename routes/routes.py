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
    def admin_dashboard():
        if not session.get('is_admin'):
            return redirect(url_for('login'))

        # Jika yang login adalah superadmin, alihkan ke dashboard superadmin
        if session.get('user_role') == 'superadmin':
            return redirect(url_for('superadmin_dashboard'))

        # Ambil data wilayah admin Pemda yang login
        admin_region = session.get('admin_region')
        
        # Query pengaduan berdasarkan wilayah admin, urutkan berdasarkan waktu pembuatan
        pengaduan = Pengaduan.query.filter_by(region=admin_region).order_by(Pengaduan.created_at.desc()).all()

        # Tambahkan nomor urut berdasarkan urutan pengaduan
        for index, complaint in enumerate(pengaduan, start=1):
            complaint.nomor_urut = index  # Menambahkan nomor urut

        return render_template('admin_dashboard.html', complaints=pengaduan)

    

    @app.route('/superadmin/monitoring')
    def superadmin_monitoring():
        if session.get('user_role') != 'superadmin':
            return redirect(url_for('login'))

        # Memastikan data terbaru dengan expire_all
        db.session.expire_all()  # Ini memastikan semua objek yang di-cache dibuang dan query baru dieksekusi

        # Data dari database
        start_date_str = request.args.get('start')
        end_date_str = request.args.get('end')

        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else None
        except ValueError:
            return "❌ Format tanggal salah. Gunakan YYYY-MM-DD.", 400

        query = db.session.query(
            Pengaduan.region,
            db.func.count(Pengaduan.id).label('total'),
            db.func.sum(db.case((Pengaduan.status == 'done', 1), else_=0)).label('ditindaklanjuti'),
            db.func.sum(db.case((Pengaduan.status == 'pending', 1), else_=0)).label('belum_diproses'),
            db.func.sum(db.case((Pengaduan.status == 'in_progress', 1), else_=0)).label('sedang_diproses'),
            db.func.avg(db.func.coalesce(
                db.func.extract('epoch', Pengaduan.updated_at - Pengaduan.created_at), 
                db.func.extract('epoch', datetime.utcnow() - Pengaduan.created_at)
            ) / 86400).label('rata2_respon')  # Jika updated_at kosong, gunakan waktu sekarang
        )

        if start_date:
            query = query.filter(Pengaduan.created_at >= start_date)
        if end_date:
            query = query.filter(Pengaduan.created_at <= end_date)

        data = query.group_by(Pengaduan.region).all()

        # Menonaktifkan cache
        response = make_response(render_template('superadmin_monitoring.html', data=data, start=start_date_str, end=end_date_str))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response




    @app.route('/superadmin/dashboard', methods=['GET', 'POST'])
    def superadmin_dashboard():
        if session.get('user_role') != 'superadmin':
            return redirect(url_for('login'))
        selected_region = request.form.get('region') if request.method == 'POST' else None
        all_regions = [r[0] for r in db.session.query(Pengaduan.region).distinct().all()]
        pengaduan = Pengaduan.query.order_by(Pengaduan.created_at.desc()).all() if not selected_region else Pengaduan.query.filter_by(region=selected_region).order_by(Pengaduan.created_at.desc()).all()
        return render_template('superadmin_dashboard.html', complaints=pengaduan, regions=all_regions, selected_region=selected_region)


    @app.route('/admin/complaint/<int:complaint_id>/update', methods=['POST'])
    def update_complaint_status(complaint_id):
        if not session.get('is_admin'):
            return redirect(url_for('login'))
        complaint = Pengaduan.query.get(complaint_id)
        if complaint:
            complaint.status = request.form.get('status')
            complaint.updated_at = datetime.utcnow()  # Pastikan updated_at diperbarui
            db.session.commit()
        return redirect(url_for('admin_dashboard'))



    @app.route('/pengaduan', methods=['GET', 'POST'])
    def form_pengaduan():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if request.method == 'POST':
            file_data = request.files['file'].read() if 'file' in request.files else None
            
            # Ambil kategori yang dipilih
            category = request.form['category']

            # Jika kategori adalah "Lainnya", ambil kategori lain yang dimasukkan oleh pengguna
            if category == 'Lainnya':
                other_category = request.form['other_category']
                if other_category:
                    category = other_category  # Gunakan kategori yang dimasukkan pengguna
                else:
                    flash('Mohon masukkan kategori lainnya.', 'error')
                    return redirect(url_for('form_pengaduan'))  # Kembali ke form jika tidak ada input kategori lain

            # Menyimpan data pengaduan ke database
            pengaduan = Pengaduan(
                user_id=user.id,
                name=user.name,
                email=user.email,
                phone=user.phone,
                address=request.form['address'],
                region=request.form['region'],
                category=category,  # Menyimpan kategori, termasuk "Lainnya"
                problem_description=request.form['problem_description'],
                severity=request.form['severity'],
                file_upload=file_data,
                incident_date=datetime.strptime(request.form['incident_date'], '%Y-%m-%d'),
                actions_taken=request.form['actions_taken'],
                follow_up_request=request.form['follow_up_request'],
                data_consent=bool(request.form.get('data_consent')),
                data_accuracy=bool(request.form.get('data_accuracy')),
            )
            db.session.add(pengaduan)
            db.session.commit()

            return render_template('pengaduan.html', success=True)
        
        return render_template('pengaduan.html')


    @app.route('/riwayat_pengaduan')
    def riwayat_pengaduan():
        if 'user_id' not in session:
            return redirect(url_for('login'))
            
        user = User.query.get(session['user_id'])
        complaints = Pengaduan.query.filter_by(user_id=user.id).order_by(Pengaduan.created_at.desc()).all()

            # Tambahkan nomor urut pada setiap pengaduan
        for index, complaint in enumerate(complaints, start=1):
            complaint.nomor_urut = index  # Menambahkan nomor urut

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
            return jsonify({'reply': response.text, 'sources': [{"title": k, "filename": v} for k, v in unique_sources.items()]})
        except Exception:
            print(traceback.format_exc())
            return jsonify({'reply': "Terjadi error di server. Silakan coba lagi."}), 500
        







    @app.route('/file/<int:complaint_id>')
    def display_file(complaint_id):
        complaint = Pengaduan.query.get(complaint_id)
        if complaint and complaint.file_upload:
            return app.response_class(complaint.file_upload, mimetype='image/jpeg')
        return "File tidak ditemukan", 404
    

    @app.route('/pengaduan/<int:complaint_id>/delete', methods=['POST'])
    def delete_complaint(complaint_id):
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])
        complaint = Pengaduan.query.get(complaint_id)

        # Pastikan pengguna hanya bisa menghapus pengaduan mereka sendiri
        if complaint and complaint.user_id == user.id:
            db.session.delete(complaint)
            db.session.commit()
            flash('Pengaduan berhasil dihapus.', 'success')
        else:
            flash('Anda tidak memiliki izin untuk menghapus pengaduan ini.', 'error')

        return redirect(url_for('riwayat_pengaduan'))  # Redirect ke halaman riwayat pengaduan
    
    
    @app.route('/profil', methods=['GET', 'POST'])
    def profil():
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])  # Ambil data pengguna yang sedang login

        if request.method == 'POST':
            if 'profile_pic' not in request.files:
                flash('Tidak ada file yang dipilih!', 'error')
                return redirect(request.url)

            file = request.files['profile_pic']
            
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)  # Menyimpan file di folder uploads
                file.save(filepath)
                
                # Simpan nama file gambar profil ke database
                user.profile_pic = f'{filename}'  # Menyimpan path relatif
                db.session.commit()
                flash('Foto profil berhasil diunggah!', 'success')
                return redirect(url_for('profil'))

        return render_template('profil.html', user=user)
   

    # --- Route untuk menyajikan gambar dari folder uploads ---
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(UPLOAD_FOLDER, filename)
    
    
    @app.route('/profil/delete_photo', methods=['POST'])
    def delete_photo():
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])  # Ambil data pengguna yang sedang login
        if user and user.profile_pic:
            # Menghapus file dari folder uploads
            file_path = os.path.join(UPLOAD_FOLDER, user.profile_pic)
            if os.path.exists(file_path):
                os.remove(file_path)

            # Menghapus path foto profil di database
            user.profile_pic = None
            db.session.commit()
            flash('Foto profil berhasil dihapus.', 'success')
        else:
            flash('Tidak ada foto profil yang dihapus.', 'error')

        return redirect(url_for('profil'))




    




    @app.route('/init-db')
    def init_db():
        db.create_all()
        return "✅ Database initialized!"

    @app.route('/drop-db')
    def drop_db():
        db.drop_all()
        return "✅ Semua tabel dihapus."
