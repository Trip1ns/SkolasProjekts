from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Konsultacija, Pieteikums
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import re

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///konsultacijas.db'
app.config['SECRET_KEY'] = 'projekts2024'
db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login' # type: ignore
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- MARŠRUTI ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            if user.loma == 'admin': return redirect(url_for('admin_dashboard'))
            if user.loma == 'skolotajs': return redirect(url_for('skolotajs_dashboard'))
            return redirect(url_for('skolens_dashboard'))
        flash('Nepareizi dati!')
    return render_template('login.html')



def is_password_strong(password):
    # Definējam regex modeli
    regex = r"^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
    return bool(re.match(regex, password))

    
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.loma != 'admin': return "Nav pieejas", 403
    
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        
        if form_type == 'add_user':
            u = User(username=request.form['username'], vards=request.form['vards'],  # type: ignore
                     uzvards=request.form['uzvards'], loma=request.form['loma'], # type: ignore
                     prieksmets=request.form.get('prieksmets'), # type: ignore
                     password=generate_password_hash(request.form['password'])) # type: ignore
            db.session.add(u)
        
        elif form_type == 'delete_user':
            User.query.filter_by(id=request.form['user_id']).delete()

        elif form_type == 'edit_konsultacija':
            k_id = request.form.get('k_id')
            dt = datetime.strptime(request.form['datums_laiks'], '%Y-%m-%dT%H:%M')
            if k_id: # Rediģēt esošu
                k = Konsultacija.query.get(k_id)
                k.datums_laiks = dt # type: ignore
                k.kabinets = request.form['kabinets'] # type: ignore
            else: # Pievienot jaunu
                k = Konsultacija(skolotajs_id=request.form['skolotajs_id'], datums_laiks=dt, kabinets=request.form['kabinets']) # type: ignore
                db.session.add(k)
        
        elif form_type == 'delete_konsultacija':
            Konsultacija.query.filter_by(id=request.form['k_id']).delete()

        db.session.commit()
        return redirect(url_for('admin_dashboard'))

    users = User.query.all()
    skolotaji = User.query.filter_by(loma='skolotajs').all()
    konsultacijas = Konsultacija.query.all()
    return render_template('admin.html', users=users, skolotaji=skolotaji, konsultacijas=konsultacijas)

@app.route('/mainit-paroli', methods=['GET', 'POST'])
@login_required
def mainit_paroli():
    if request.method == 'POST':
        veca = request.form.get('veca_parole')
        jauna = request.form.get('jauna_parole')
        
        if not check_password_hash(current_user.password, veca): # type: ignore
            flash("Pašreizējā parole nav pareiza!")
        elif is_password_strong(jauna) is not True:
            # is_password_strong jau satur flash ziņojumu
            pass
        else:
            current_user.password = generate_password_hash(jauna) # type: ignore
            db.session.commit()
            flash("Parole veiksmīgi nomainīta!")
            return redirect(url_for('index'))
            
    return render_template('mainit_paroli.html')

@app.route('/skolotajs', methods=['GET', 'POST'])
@login_required
def skolotajs_dashboard():
    if current_user.loma != 'skolotajs': return "Nav pieejas", 403
    
    if request.method == 'POST':
        p_id = request.form.get('p_id')
        pieteikums = Pieteikums.query.get(p_id)
        if 'accept' in request.form:
            pieteikums.statuss = 'Pieņemts' # type: ignore
        elif 'reject' in request.form:
            pieteikums.statuss = 'Noraidīts' # type: ignore
            pieteikums.atteikuma_iemesls = request.form.get('iemesls') # type: ignore
        db.session.commit() 

    # Redz pieteikumus tikai uz savām konsultācijām
    pieteikumi = Pieteikums.query.join(Konsultacija).filter(Konsultacija.skolotajs_id == current_user.id).all()
    return render_template('skolotajs.html', pieteikumi=pieteikumi)

@app.route('/skolens')
@login_required
def skolens_dashboard():
    pieteikumi = Pieteikums.query.filter_by(skolens_id=current_user.id).all()
    return render_template('skolens.html', pieteikumi=pieteikumi)

@app.route('/kalendars', methods=['GET', 'POST'])
@login_required
def kalendars():
    if current_user.loma == 'skolotajs':
        flash("Skolotāji nevar pieteikties konsultācijām!")
        return redirect(url_for('skolotajs_dashboard'))

    tagad = datetime.now()
    query = Konsultacija.query.filter(Konsultacija.datums_laiks > tagad)
    
    search = request.args.get('search')
    subject = request.args.get('subject')
    
    if search:
        query = query.join(User).filter(User.uzvards.contains(search))
    if subject:
        query = query.join(User).filter(User.prieksmets.contains(subject))
    
    konsultacijas = query.all()

    if request.method == 'POST':
        p = Pieteikums(konsultacija_id=request.form['k_id'], skolens_id=current_user.id, iemesls=request.form['iemesls']) # type: ignore
        db.session.add(p)
        db.session.commit()
        return redirect(url_for('skolens_dashboard'))

    return render_template('kalendars.html', konsultacijas=konsultacijas)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('admin123'), vards='Admin', uzvards='Lietotājs', loma='admin') # type: ignore
        skolotajs = User(username='skolotajs', password=generate_password_hash('parole123'), vards='Jānis', uzvards='Bērziņš', loma='skolotajs', prieksmets='Matemātika') # type: ignore
        skolens = User(username='skolens', password=generate_password_hash('parole123'), vards='Anna', uzvards='Ozola', loma='skolens') # type: ignore
        db.session.add_all([admin, skolotajs, skolens])
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)