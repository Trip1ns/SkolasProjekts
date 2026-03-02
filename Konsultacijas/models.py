from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ==================== LIETOTĀJA MODELIS ====================
class User(db.Model, UserMixin):
    """Lietotāja modelis - skolēns, skolotājs vai administrators"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    username = db.Column(db.String(50), nullable=True, unique=True)
    password = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(20))  # "student", "teacher", "admin"
    subject = db.Column(db.String(200), nullable=True)  # Skolotāja mācību priedmetā
    ms_oid = db.Column(db.String(100), nullable=True, unique=True)
    email = db.Column(db.String(100), nullable=True)
    
    def set_password(self, password):
        """Parolei jāpieliek heš"""
        self.password = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Pārbauda vai parole ir pareiza"""
        if not self.password:
            return False
        return check_password_hash(self.password, password)


# ==================== KONSULTĀCIJAS LAIKA MODELIS ====================
class TeacherSlot(db.Model):
    """Skolotāja konsultācijas laiks - kad viņš pieņem skolēnus"""
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    day = db.Column(db.String(20))  # Pirmdiena, Otrdiena utt.
    time = db.Column(db.String(20))  # "15:00-16:00"
    room = db.Column(db.String(20))  # Auditorijas numurs
    max_students = db.Column(db.Integer, default=10)  # Maksimāls skolēnu skaits
    teacher = db.relationship("User")


# ==================== PIETEIKUMA MODELIS ====================
class Request(db.Model):
    """Skolēna pieteikums uz konsultāciju"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    slot_id = db.Column(db.Integer, db.ForeignKey("teacher_slot.id"))
    reason = db.Column(db.Text)  # Kāpēc skolēns piesakās
    status = db.Column(db.String(20), default="pending")  # pending, accepted, rejected
    reject_reason = db.Column(db.Text)  # Noraidīšanas iemesls (ja noraidīts)
    consultation_notes = db.Column(db.Text, nullable=True)  # Skolotāja piezīmes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

