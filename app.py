# === FILE: app.py ===
from flask import Flask, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash  # ✅ Tambahan untuk autentikasi
from routes import register_routes  # Rute dan logika utama aplikasi

# --- Inisialisasi Aplikasi ---
app = Flask(__name__)

# ✅ Secret Key untuk autentikasi session login
app.secret_key = '7f41b1f8f1a9e0f8c9b01d985e64d1d201edb5bbf7c36b876f8bbd4e789d7a20'  # Gantilah dengan secrets.token_hex(32) untuk produksi

# --- Konfigurasi Database ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Gemastikusk23@localhost:5432/agrolldb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Inisialisasi SQLAlchemy ---
db = SQLAlchemy(app)

# --- Registrasi Routes ---
register_routes(app, db)

# --- Jalankan Aplikasi ---
if __name__ == '__main__':
    from routes import initialize_rag_system
    initialize_rag_system()
    app.run(debug=True, port=5000)
