from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    phone = db.Column(db.String(20), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='petani')
    region = db.Column(db.String(100))
    profile_pic = db.Column(db.String(255))  # Kolom baru untuk foto profil
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Pengaduan(db.Model):
    __tablename__ = 'pengaduan'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    region = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    problem_description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(50), nullable=False)
    file_upload = db.Column(db.LargeBinary)
    incident_date = db.Column(db.Date, nullable=False)
    actions_taken = db.Column(db.Text, nullable=False)
    follow_up_request = db.Column(db.Text, nullable=False)
    data_consent = db.Column(db.Boolean, nullable=False)
    data_accuracy = db.Column(db.Boolean, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # ✅ Taruh di sini

    user = db.relationship('User', backref=db.backref('pengaduan_list', lazy=True))
