import re
from datetime import datetime, timedelta, time as dt_time
from flask import Flask, render_template, request, redirect, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, TeacherSlot, Request
from consultation_utils import (
    atrod_visus_pieejamos_laikus,
    parbaud_registracija_atverta,
    atrod_laiku_lidz_terminam,
    formatets_datums_latvieski
)
import threading
import time as time_module


# ==================== KONFIGURĀCIJA ====================
PAROLES_SHEMA = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$'

app = Flask(__name__)
app.secret_key = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///kons.db"

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"  # type: ignore

@login_manager.user_loader
def load_user(user_id):
    """Ielādē lietotāju pēc ID"""
    return db.session.get(User, int(user_id))

# ==================== PIERAKSTĪŠANĀS ====================
@app.route("/", methods=["GET", "POST"])
def login():
    """Pierakstīšanās vai reģistrācija"""
    if request.method == "POST":
        vards = request.form["name"]
        parole = request.form["password"]
        role = request.form["role"]

        # Pārbauda paroļu kvalitāti
        if not re.match(PAROLES_SHEMA, parole):
            return render_template(
                "login.html",
                error="Parolei jābūt vismaz 8 simboliem, ar lielo burtu, ciparu un speciālo simbolu."
            )

        # Meklē lietotāju datu bāzē
        lietotajs = User.query.filter_by(name=vards, role=role).first()
        if not lietotajs:
            # Ja nav, mēģina ar lietotājvārdu (skolotājiem)
            lietotajs = User.query.filter_by(username=vards, role=role).first()

        if not lietotajs:
            # Ja lietotājs neeksistē, viņu izveido
            lietotajs = User(name=vards, role=role)  # type: ignore
            lietotajs.set_password(parole)
            db.session.add(lietotajs)
            db.session.commit()
        else:
            # Ja eksistē, pārbauda paroli
            if not lietotajs.check_password(parole):
                return render_template(
                    "login.html",
                    error="Nepareiza parole"
                )

        login_user(lietotajs)
        return redirect("/dashboard")

    return render_template("login.html")


# ==================== PANEĻI ====================
@app.route("/dashboard")
@login_required
def dashboard():
    """Pāradā pareizo paneļi pēc lietotāja lomas"""
    if current_user.role == "admin":
        return render_template("dashboard_admin.html")
    if current_user.role == "teacher":
        return render_template("dashboard_teacher.html")
    return render_template("dashboard_student.html")


@app.route("/calendar")
@login_required
def calendar():
    """Rāda interaktīvo konsultāciju kalendāru"""
    if current_user.role != "student":
        return redirect("/dashboard")
    return render_template("calendar.html")


@app.route("/logout")
def logout():
    """Izlogojas"""
    logout_user()
    return redirect("/")


@app.get("/api/slots")
@login_required
def slots():
    now = datetime.now()

    # LV → EN
    map_days = {
        "Pirmdiena": "Monday",
        "Otrdiena": "Tuesday",
        "Trešdiena": "Wednesday",
        "Ceturtdiena": "Thursday",
        "Piektdiena": "Friday"
    }

    # optional filter by teacher
    teacher_id = request.args.get("teacher_id", type=int)
    day_filter = request.args.get("day", type=str)
    
    query = TeacherSlot.query
    if teacher_id:
        query = query.filter_by(teacher_id=teacher_id)
    if day_filter:
        query = query.filter_by(day=day_filter)
    
    slots = query.all()

    # Get student's existing requests if they are a student
    student_requested_slot_ids = set()
    student_requested_slots = {}
    if current_user.role == "student":
        student_requests = Request.query.filter_by(
            student_id=current_user.id
        ).filter(
            Request.status != "rejected"
        ).all()
        student_requested_slot_ids = {req.slot_id for req in student_requests}
        student_requested_slots = {req.slot_id: req.status for req in student_requests}

    result = []

    for s in slots:
        # Handle both "–" (en dash) and "-" (hyphen) separators
        time_str = s.time.replace("–", "-").replace("—", "-")
        start_time = time_str.split("-")[0].strip()
        try:
            hour, minute = map(int, start_time.split(":"))
        except (ValueError, AttributeError):
            continue

        # Nosaka nedēļas dienu no slot.day
        slot_weekday = None
        for lv_day, en_day in map_days.items():
            if s.day == lv_day:
                slot_weekday = datetime.strptime(en_day, "%A").weekday()
                break
        
        if slot_weekday is None:
            continue

        # APRĒĶINS: Nākamais šī laika slot
        today_weekday = now.weekday()
        days_until_slot = (slot_weekday - today_weekday) % 7
        
        # Ja slots ir šodien, pārbaudē vai laiks jau pagājis
        if days_until_slot == 0:
            # Slots ir šodien
            if now.hour > hour or (now.hour == hour and now.minute > minute):
                # Laiks jau pagājis → rādīt nākamās nedēļas slot
                days_until_slot = 7
            # Citādi slot ir vēl šodien
        
        # Aprēķina slot sākuma datetime
        slot_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if days_until_slot > 0:
            slot_datetime += timedelta(days=days_until_slot)
        
        # SLĒGŠANAS LOGIKA:
        # - reģistrācija slēdzas 30 min pirms sākuma OR at the end of that calendar day (23:59:59)
        #   whichever comes earlier for the occurrence. This prevents signing up for past dates
        occurrence_date = slot_datetime.date()
        day_end = datetime.combine(occurrence_date, dt_time(23, 59, 59))
        closes_before_start = slot_datetime - timedelta(minutes=30)
        # choose the earlier close time so that registration closes 30min before start, but
        # after the day passes (23:59) it will be considered closed as well
        registration_closes_at = min(closes_before_start, day_end)
        is_closed = now >= registration_closes_at
        
        # Ja slots jau pilnīgi pagājis (laiks ir noslēdzies) → skip
        if now >= slot_datetime + timedelta(minutes=1):
            # If the calculated occurrence start is still in the past (safety), skip
            continue

        count = Request.query.filter_by(slot_id=s.id)\
            .filter(Request.status != "rejected").count()

        # Check if current student has requested this slot
        is_requested = s.id in student_requested_slot_ids
        request_status = student_requested_slots.get(s.id, None)

        result.append({
            "id": s.id,
            "day": s.day,
            "time": s.time,
            "room": s.room,
            "teacher": s.teacher.name,
            "teacher_id": s.teacher.id,
            "teacher_subject": s.teacher.subject if s.teacher else None,
            "max_students": s.max_students,
            "free": s.max_students - count,
            "is_requested": is_requested,
            "request_status": request_status,
            "is_closed": is_closed
        })

    return jsonify(result)


@app.get("/api/calendar/available")
@login_required
def calendar_available():
    """Get all available consultation slots with real-time registration status"""
    if current_user.role != "student":
        return jsonify([]), 403
    
    slots = TeacherSlot.query.all()
    available = atrod_visus_pieejamos_laikus(slots)
    
    # Get student's existing requests
    student_requests = Request.query.filter_by(
        student_id=current_user.id
    ).filter(
        Request.status != "rejected"
    ).all()
    student_requested_slot_ids = {req.slot_id for req in student_requests}
    
    # Create a map of slot_id to TeacherSlot for quick access
    slot_map = {s.id: s for s in slots}
    
    # Add request status and capacity info to each slot
    for slot in available:
        slot["is_requested"] = slot["id"] in student_requested_slot_ids
        
        # Add capacity information
        teacher_slot = slot_map.get(slot["id"])
        if teacher_slot:
            count = Request.query.filter_by(slot_id=slot["id"]).filter(
                Request.status != "rejected"
            ).count()
            slot["capacity"] = {
                "total": teacher_slot.max_students,
                "registered": count,
                "available": teacher_slot.max_students - count
            }
        else:
            # Fallback if slot not found
            slot["capacity"] = {
                "total": 10,
                "registered": 0,
                "available": 10
            }
    
    return jsonify(available)


@app.get("/api/calendar/slot-status/<int:slot_id>")
@login_required
def calendar_slot_status(slot_id):
    """Get real-time status of a specific slot"""
    slot = TeacherSlot.query.get(slot_id)
    if not slot:
        return jsonify({"error": "Slots nav atrasts"}), 404
    
    status = parbaud_registracija_atverta(slot.day, slot.time)
    time_info = atrod_laiku_lidz_terminam(slot.day, slot.time)
    
    # Get capacity info
    count = Request.query.filter_by(slot_id=slot_id).filter(
        Request.status != "rejected"
    ).count()
    
    # Check if student has already requested this
    is_requested = False
    if current_user.role == "student":
        is_requested = Request.query.filter_by(
            student_id=current_user.id,
            slot_id=slot_id
        ).filter(Request.status != "rejected").first() is not None
    
    return jsonify({
        "slot_id": slot_id,
        "day": slot.day,
        "time": slot.time,
        "room": slot.room,
        "teacher": slot.teacher.name,
        "registration_open": status["open"],
        "occurrence": status["occurrence"].isoformat() if status["occurrence"] else None,
        "occurrence_date_lv": formatets_datums_latvieski(status["occurrence"]) if status["occurrence"] else None,
        "deadline": status["deadline"].isoformat() if status["deadline"] else None,
        "deadline_lv": formatets_datums_latvieski(status["deadline"]) if status["deadline"] else None,
        "time_until_deadline": time_info,
        "capacity": {
            "total": slot.max_students,
            "registered": count,
            "available": slot.max_students - count
        },
        "is_requested": is_requested,
        "close_reason": status["reason"]
    })





# ==================== PALĪGFUNKCIJAS ====================
def parse_time(time_str):
    """Nobīrī laika stringu '15:10-16:00' uz (stundu, minūti) pārus"""
    time_str = time_str.replace("–", "-").replace("—", "-").strip()
    dalas = time_str.split("-")
    if len(dalas) != 2:
        return None, None
    
    try:
        start = dalas[0].strip().split(":")
        end = dalas[1].strip().split(":")
        start_time = (int(start[0]), int(start[1]))
        end_time = (int(end[0]), int(end[1]))
        return start_time, end_time
    except (ValueError, IndexError):
        return None, None


def times_overlap(time1, time2):
    """Pārbauda vai divi laika intervāli pārklājas"""
    start1, end1 = parse_time(time1)
    start2, end2 = parse_time(time2)
    
    if not all([start1, end1, start2, end2]):
        return False
    
    # Pārvērš uz minūtēm
    assert start1 is not None and end1 is not None and start2 is not None and end2 is not None
    start1_min = start1[0] * 60 + start1[1]
    end1_min = end1[0] * 60 + end1[1]
    start2_min = start2[0] * 60 + start2[1]
    end2_min = end2[0] * 60 + end2[1]
    
    # Atgriež True ja pārklājas
    return not (end1_min <= start2_min or end2_min <= start1_min)


# ==================== PIETEIKUMA IZVEIDE ====================
@app.post("/api/request")
@login_required
def make_request():
    """Skolēns piesakās uz konsultāciju"""
    if current_user.role != "student":
        return jsonify({"error": "Tikai skolēni var pieteikties konsultācijām"}), 403

    dati = request.json
    laiks = TeacherSlot.query.get(dati.get("slot_id"))
    if not laiks:
        return jsonify({"error": "Konsultācijas laiks nav atrasts"}), 404

    # Pārbauda vai skolotāja ID sakrīt
    if dati.get("teacher_id") != laiks.teacher_id:
        return jsonify({"error": "Nepareizs skolotāja ID"}), 400

    # Pārbauda vietas pieejamību
    pieteikumu_skaits = Request.query.filter_by(slot_id=laiks.id).filter(Request.status != "rejected").count()
    if pieteikumu_skaits >= laiks.max_students:
        return jsonify({"error": "Konsultācijas laiks ir pilns"}), 400

    # Pārbauda vai jau pieteicies
    jau_pieteicies = Request.query.filter_by(slot_id=laiks.id, student_id=current_user.id).first()
    if jau_pieteicies:
        return jsonify({"error": "Jūs jau esat pieteicies šai konsultācijai"}), 400

    # Pārbauda vai nav laika konflikta ar citām konsultācijām tajā pašā dienā
    mani_pieteikumi = Request.query.filter_by(
        student_id=current_user.id
    ).filter(
        Request.status != "rejected"
    ).all()
    
    for esoss_pieteikums in mani_pieteikumi:
        esoss_laiks = TeacherSlot.query.get(esoss_pieteikums.slot_id)
        if esoss_laiks and esoss_laiks.day == laiks.day:
            if times_overlap(esoss_laiks.time, laiks.time):
                return jsonify({
                    "error": f"Jūs jau esat pieteicies citai konsultācijai šajā laikā ({esoss_laiks.day}, {esoss_laiks.time})"
                }), 400

    # Izveido pieteikumu
    pieteikums = Request(  # type: ignore[keyword-arg]
        student_id=current_user.id,  # type: ignore[assignment]
        teacher_id=laiks.teacher_id,  # type: ignore[assignment]
        slot_id=laiks.id,  # type: ignore[assignment]
        reason=dati.get("reason", "")  # type: ignore[assignment]
    )
    db.session.add(pieteikums)
    db.session.commit()
    return jsonify({"ok": True, "message": "Pieteikums veiksmīgi nosūtīts"})


# ==================== SKOLĒNA PIETEIKUMI ====================
@app.get("/api/student/requests")
@login_required
def student_requests():
    """Ielādē visus skolēna pieteikumus"""
    if current_user.role != "student":
        return jsonify([]), 403

    pieteikumi = Request.query.filter_by(student_id=current_user.id).order_by(Request.created_at.desc()).all()
    rezultats = []

    for pieteikums in pieteikumi:
        laiks = TeacherSlot.query.get(pieteikums.slot_id)
        skolotajs = User.query.get(pieteikums.teacher_id)
        rezultats.append({
            "id": pieteikums.id,
            "slot_id": pieteikums.slot_id,
            "teacher": skolotajs.name if skolotajs else "Nezināms",
            "day": laiks.day if laiks else "Nezināms",
            "time": laiks.time if laiks else "Nezināms",
            "room": laiks.room if laiks else "Nezināms",
            "reason": pieteikums.reason,
            "status": pieteikums.status,
            "reject_reason": pieteikums.reject_reason,
            "consultation_notes": pieteikums.consultation_notes,
            "created_at": pieteikums.created_at.isoformat() if pieteikums.created_at else None
        })
    return jsonify(rezultats)


# ==================== SKOLOTĀJA PIETEIKUMI ====================
@app.get("/api/teacher/requests")
@login_required
def teacher_requests():
    """Ielādē visus skolotāja saņemtos pieteikumus"""
    if current_user.role != "teacher":
        return jsonify([]), 403

    pieteikumi = Request.query.filter_by(teacher_id=current_user.id).order_by(Request.created_at.desc()).all()
    rezultats = []

    for pieteikums in pieteikumi:
        skolens = User.query.get(pieteikums.student_id)
        laiks = TeacherSlot.query.get(pieteikums.slot_id)
        rezultats.append({
            "id": pieteikums.id,
            "student": skolens.name if skolens else "Nezināms",
            "student_id": pieteikums.student_id,
            "slot_id": pieteikums.slot_id,
            "day": laiks.day if laiks else "Nezināms",
            "time": laiks.time if laiks else "Nezināms",
            "room": laiks.room if laiks else "Nezināms",
            "reason": pieteikums.reason,
            "status": pieteikums.status,
            "reject_reason": pieteikums.reject_reason,
            "consultation_notes": pieteikums.consultation_notes,
            "created_at": pieteikums.created_at.isoformat() if pieteikums.created_at else None
        })
    return jsonify(rezultats)


# ==================== IZVEIDES FUNKCIJAS ====================
def seed_admin():
    """Izveido noklusējuma administratoru, skolotājus un skolēnus"""
    
    # Administrators
    if not User.query.filter_by(role="admin").first():
        admins = User(name="admin", role="admin")  # type: ignore
        admins.set_password("Admin123!")
        db.session.add(admins)

    # Paraugs skolotājs - matemātika
    if not User.query.filter_by(name="MathTeacher", role="teacher").first():
        matematikas_skolotajs = User(name="MathTeacher", role="teacher")  # type: ignore
        matematikas_skolotajs.set_password("Teach123!")
        db.session.add(matematikas_skolotajs)

    # Paraugs skolotājs - latvieši
    if not User.query.filter_by(name="LatvTeacher", role="teacher").first():
        latviesu_skolotajs = User(name="LatvTeacher", role="teacher")  # type: ignore
        latviesu_skolotajs.set_password("Teach123!")
        db.session.add(latviesu_skolotajs)

    # Paraugs skolēns
    if not User.query.filter_by(name="Student1", role="student").first():
        skolens = User(name="Student1", role="student")  # type: ignore
        skolens.set_password("Stud123!")
        db.session.add(skolens)

    db.session.commit()


def cleanup_expired_requests(now=None):
    """Dzēš pieteikumus, kuru konsultācija jau ir beigusies.
    Dzēš tikai PENDING pieteikumus, saglabā ACCEPTED un REJECTED vēsturei."""
    now = now or datetime.now()
    dzesami_pieteikumi = []

    nedelas_dienas = {
        "Pirmdiena": "Monday",
        "Otrdiena": "Tuesday",
        "Trešdiena": "Wednesday",
        "Ceturtdiena": "Thursday",
        "Piektdiena": "Friday"
    }

    # Apstrādā tikai gaidu statusa pieteikumus
    visi_pieteikumi = Request.query.filter_by(status="pending").all()
    for pieteikums in visi_pieteikumi:
        try:
            laiks = TeacherSlot.query.get(pieteikums.slot_id)
            if not laiks:
                dzesami_pieteikumi.append(pieteikums.id)
                continue

            # Nolasa sākuma laiku
            laika_string = laiks.time.replace("–", "-").replace("—", "-")
            sakums = laika_string.split("-")[0].strip()
            stundu, minusu = map(int, sakums.split(":"))

            # Atrast nedēļas dienu
            laika_nedelas_diena = None
            for lv_diena, en_diena in nedelas_dienas.items():
                if laiks.day == lv_diena:
                    laika_nedelas_diena = datetime.strptime(en_diena, "%A").weekday()
                    break
            if laika_nedelas_diena is None:
                continue

            # Atrod nākamo šī laika gadījumu
            izveide_laiks = pieteikums.created_at or datetime.now()
            dienas_lidz = (laika_nedelas_diena - izveide_laiks.weekday()) % 7
            gadijums = izveide_laiks.replace(hour=stundu, minute=minusu, second=0, microsecond=0) + timedelta(days=dienas_lidz)
            if gadijums < izveide_laiks:
                gadijums += timedelta(days=7)

            # Gala diena
            dienas_beigas = datetime.combine(gadijums.date(), dt_time(23, 59, 59))
            if now >= dienas_beigas:
                dzesami_pieteikumi.append(pieteikums.id)
        except Exception:
            dzesami_pieteikumi.append(pieteikums.id)

    # Dzēš pieteikumus
    dzestais_skaits = 0
    if dzesami_pieteikumi:
        dzestais_skaits = Request.query.filter(Request.id.in_(dzesami_pieteikumi)).delete(synchronize_session=False)
        db.session.commit()
    return dzestais_skaits


# ==================== ADMINISTRATORA FUNKCIJAS ====================
@app.post('/api/admin/cleanup')
@login_required
def admin_cleanup():
    """Administrators var manuāli izsaukt notīrīšanu"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403

    dzestais = cleanup_expired_requests()
    return jsonify({'ok': True, 'deleted_requests': dzestais})


def _cleanup_scheduler_loop():
    """Palīgfunkcija notīrīšanas plānošanai - katru dienu plkst. 00:05"""
    while True:
        try:
            cleanup_expired_requests()
        except Exception:
            pass
        # Pagaida līdz nākamajam rītam 00:05
        now = datetime.now()
        rits = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        sleep_seconds = (rits - now).total_seconds()
        if sleep_seconds <= 0:
            sleep_seconds = 60 * 60 * 24
        time_module.sleep(sleep_seconds)


def start_cleanup_scheduler():
    """Sāk notīrīšanas fonā"""
    pavads = threading.Thread(target=_cleanup_scheduler_loop, daemon=True)
    pavads.start()


# ==================== SKOLOTĀJA LĒMUMI ====================
@app.post("/api/teacher/decision")
@login_required
def decision():
    """Skolotājs pieņem vai noraidā pieteikumu"""
    if current_user.role != "teacher":
        return jsonify({"error": "forbidden"}), 403

    dati = request.json
    pieteikums = Request.query.get(dati["id"])
    if not pieteikums or pieteikums.teacher_id != current_user.id:
        return jsonify({"error": "not found"}), 404

    pieteikums.status = dati["status"]

    if dati["status"] == "rejected":
        pieteikums.reject_reason = dati.get("reason")
    elif dati["status"] == "accepted":
        # Saglabā skolotāja piezīmes
        pieteikums.consultation_notes = dati.get("consultation_notes", "")

    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/student/cancel-request")
@login_required
def cancel_request():
    """Skolēns atceļ savu pieteikumu"""
    if current_user.role != "student":
        return jsonify({"error": "forbidden"}), 403

    dati = request.json
    pieteikuma_id = dati.get("id")
    
    pieteikums = Request.query.get(pieteikuma_id)
    if not pieteikums or pieteikums.student_id != current_user.id:
        return jsonify({"error": "Pieteikums nav atrasts"}), 404

    # Tikai gaidošus pieteikumus drīkst atcelt
    if pieteikums.status != "pending":
        return jsonify({"error": "Var atcelt tikai gaidošos pieteikumus"}), 400

    db.session.delete(pieteikums)
    db.session.commit()
    return jsonify({"ok": True, "message": "Pieteikums atcelts"})


# ==================== ADMINISTRATORA LIETOTĀJU PĀRVALDĪBA ====================
@app.get("/api/admin/teachers")
@login_required
def admin_teachers():
    """Ielādē visus skolotājus"""
    if current_user.role != "admin":
        return jsonify([])

    skolotaji = User.query.filter_by(role="teacher").all()
    return jsonify([
        {
            "id": s.id,
            "name": s.name
        } for s in skolotaji
    ])


@app.get("/api/admin/users")
@login_required
def admin_users():
    """Ielādē visus lietotājus"""
    if current_user.role != "admin":
        return jsonify([]), 403

    lietotaji = User.query.all()
    return jsonify([
        {
            "id": l.id,
            "name": l.name,
            "username": l.username,
            "role": l.role,
            "email": l.email
        } for l in lietotaji
    ])


@app.post("/api/admin/add")
@login_required
def admin_add():
    """Administrators pievieno jaunus lietotājus"""
    if current_user.role != "admin":
        return jsonify({"error": "forbidden"}), 403

    dati = request.json
    jauns_lietotajs = User(  # type: ignore[keyword-arg]
        name=dati["name"],  # type: ignore[assignment]
        role=dati["role"]  # type: ignore[assignment]
    )
    jauns_lietotajs.set_password(dati["password"])
    db.session.add(jauns_lietotajs)
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/admin/delete")
@login_required
def admin_delete():
    """Administrators dzēš lietotājus"""
    if current_user.role != "admin":
        return jsonify({"error": "forbidden"}), 403

    lietotajs = User.query.get(request.json["id"])
    if lietotajs:
        db.session.delete(lietotajs)
        db.session.commit()

    return jsonify({"ok": True})


@app.get("/api/admin/stats")
@login_required
def admin_stats():
    """Administratora statistika"""
    if current_user.role != "admin":
        return jsonify({}), 403

    return jsonify({
        "skoleni": User.query.filter_by(role="student").count(),
        "skolotaji": User.query.filter_by(role="teacher").count(),
        "admini": User.query.filter_by(role="admin").count(),
        "laiki": TeacherSlot.query.count(),
        "pieteikumi": Request.query.count(),
        "gaidu": Request.query.filter_by(status="pending").count(),
        "pienemti": Request.query.filter_by(status="accepted").count(),
        "noraiditi": Request.query.filter_by(status="rejected").count()
    })


@app.get("/api/admin/slots")
@login_required
def admin_slots():
    """Ielādē visus konsultācijas laikus administratoram"""
    if current_user.role != "admin":
        return jsonify([]), 403

    laiki = TeacherSlot.query.all()
    return jsonify([
        {
            "id": l.id,
            "teacher_id": l.teacher_id,
            "teacher_name": l.teacher.name if l.teacher else "Nezināms",
            "day": l.day,
            "time": l.time,
            "room": l.room,
            "max_students": l.max_students,
            "current_requests": Request.query.filter_by(slot_id=l.id).filter(Request.status != "rejected").count()
        } for l in laiki
    ])

@app.post("/api/admin/add-slot")
@login_required
def admin_add_slot():
    """Administrators pievieno konsultācijas laikus"""
    if current_user.role != "admin":
        return jsonify({"error": "forbidden"}), 403

    dati = request.json

    jauns_laiks = TeacherSlot(  # type: ignore[keyword-arg]
        teacher_id=int(dati["teacher_id"]),  # type: ignore[assignment]
        day=dati["day"],  # type: ignore[assignment]
        time=dati["time"],  # type: ignore[assignment]
        room=dati["room"],  # type: ignore[assignment]
        max_students=int(dati.get("max_students", 10))  # type: ignore[assignment]
    )

    db.session.add(jauns_laiks)
    db.session.commit()
    return jsonify({"ok": True})


def seed_slots():
    """Inicializē konsultāciju laikus datu bāzē"""
    if not TeacherSlot.query.first():
        from seed_database import seed_database
        seed_database()


@app.get("/api/teachers")
@login_required
def teachers():
    """Ielādē visus skolotājus"""
    skolotaji = User.query.filter_by(role="teacher").all()
    return jsonify([{"id": s.id, "name": s.name, "subject": s.subject} for s in skolotaji])


# ==================== PROGRAMMAS SĀKUMS ====================
if __name__ == "__main__":
    with app.app_context():
        """Inicializē un palaiž Flask aplikāciju"""
        # Pārbauda datu bāzes shēmu
        shema_veca = False
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            
            # Check if user table exists
            tables = inspector.get_table_names()
            if 'user' in tables:
                columns = [col['name'] for col in inspector.get_columns('user')]
                if 'subject' not in columns:
                    shema_veca = True
                    print("⚠️  Database schema outdated (missing 'subject' column).")
            else:
                # Table doesn't exist, create it
                db.create_all()
        except Exception as e:
            # If inspection fails, try a direct query
            try:
                # Try to access subject attribute - if it fails, schema is outdated
                result = db.session.execute(text("PRAGMA table_info(user)"))
                columns = [row[1] for row in result]
                if 'subject' not in columns:
                    shema_veca = True
                    print("⚠️  Database schema outdated (missing 'subject' column).")
            except:
                # If everything fails, assume we need to create tables
                db.create_all()
        
        if shema_veca:
            print("🔄 Recreating database with updated schema...")
            db.drop_all()
            db.create_all()
            print("✅ Database recreated. Seeding data...")
            # Import and run seed_database to populate (it handles admin and slots)
            from seed_database import seed_database
            seed_database()
        else:
            # Ensure tables exist
            db.create_all()
            # Only seed if tables are empty (seed_database already handles this)
            if not User.query.first():
                print("📦 Database empty. Seeding initial data...")
                from seed_database import seed_database
                seed_database()
            else:
                # Just ensure admin exists
                seed_admin()
                seed_slots()

            # Start background cleanup scheduler (daemon thread)
            try:
                start_cleanup_scheduler()
            except Exception:
                pass

            app.run(debug=True)