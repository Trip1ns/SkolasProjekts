from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    vards = db.Column(db.String(50), nullable=False)
    uzvards = db.Column(db.String(50), nullable=False)
    loma = db.Column(db.String(20), nullable=False) # admin, skolotajs, skolens
    prieksmets = db.Column(db.String(50), nullable=True)

class Konsultacija(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    skolotajs_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    datums_laiks = db.Column(db.DateTime, nullable=False)
    kabinets = db.Column(db.String(20), nullable=False)
    # Attiecība, lai vieglāk piekļūtu skolotāja datiem
    skolotajs = db.relationship('User', backref='konsultacijas')

class Pieteikums(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    konsultacija_id = db.Column(db.Integer, db.ForeignKey('konsultacija.id'), nullable=False)
    skolens_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    iemesls = db.Column(db.Text, nullable=False)
    statuss = db.Column(db.String(20), default='Gaidīšanā') # Gaidīšanā, Pieņemts, Noraidīts
    atteikuma_iemesls = db.Column(db.Text, nullable=True)
    
    skolens = db.relationship('User', backref='pieteikumi')
    konsultacija = db.relationship('Konsultacija', backref='pieteikumi')