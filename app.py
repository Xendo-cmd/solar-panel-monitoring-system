import io
import os
import secrets
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    import cloudinary
    import cloudinary.uploader
    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "dwg", "docx"}

# Cloudinary is used in production so uploaded blueprints/photos/diagrams
# survive Render restarts. Render provides the credentials as separate
# environment variables. For local development, if those variables are
# absent, the app falls back to the local uploads/ folder.
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")
USE_CLOUDINARY = all((CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET))
if USE_CLOUDINARY and not CLOUDINARY_AVAILABLE:
    raise RuntimeError("Cloudinary credentials are set, but the cloudinary package is not installed.")
if USE_CLOUDINARY:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")

# Use a real Postgres database when deployed (DATABASE_URL is set by the host),
# otherwise fall back to a local SQLite file for testing on your own computer.
db_url = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "solar_system.db"))
if db_url.startswith("postgres://"):  # some hosts still hand out the old-style prefix
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."

# Fixed list of milestone types for the core workflow.
MILESTONE_TYPES = [
    "Site Blueprint",
    "Site Photos",
    "Wiring System Diagram",
    "Grid Connection Sign-off",
]

# Fixed list of security questions used for the forgot-password flow.
SECURITY_QUESTIONS = [
    "What is your mother's maiden name?",
    "What was the name of your first pet?",
    "What elementary school did you attend?",
    "What is your favorite color?",
]


# ---------- Models ----------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # "inspector" or "installer"

    # Only set for inspectors: the key installers use to sign up under them.
    business_key = db.Column(db.String(20), unique=True, nullable=True)

    # Only set for installers: which inspector they belong to.
    inspector_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Used for the forgot-password flow.
    security_question = db.Column(db.String(200), nullable=False, default=SECURITY_QUESTIONS[0])
    security_answer_hash = db.Column(db.String(255), nullable=False, default="")

    projects = db.relationship(
        "Project", backref="installer", lazy=True,
        foreign_keys="Project.installer_id"
    )

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def check_security_answer(self, answer):
        return check_password_hash(self.security_answer_hash, answer.strip().lower())


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(250), nullable=True)
    installer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    inspector_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    milestones = db.relationship("Milestone", backref="project", lazy=True,
                                  cascade="all, delete-orphan")


class Milestone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    milestone_type = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), default="pending")  # pending / approved / rejected
    note = db.Column(db.String(300), nullable=True)  # inspector's comment on reject
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------- Helpers ----------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def latest_milestones_by_type(project):
    """Return {milestone_type: latest Milestone} for a project, so re-uploads
    after a rejection only count once, using the newest attempt."""
    latest = {}
    for m in sorted(project.milestones, key=lambda x: x.uploaded_at):
        latest[m.milestone_type] = m
    return latest


def project_progress(project):
    """Return (percent, approved_count, total_types) based on the newest
    attempt of each milestone type being approved."""
    latest = latest_milestones_by_type(project)
    total = len(MILESTONE_TYPES)
    approved = sum(1 for t in MILESTONE_TYPES if latest.get(t) and latest[t].status == "approved")
    percent = round((approved / total) * 100) if total else 0
    return percent, approved, total


def installer_stats(installer):
    """Aggregate progress stats across all of one installer's sites."""
    projects = Project.query.filter_by(installer_id=installer.id).all()
    site_count = len(projects)
    total_percent = 0
    pending_total = 0
    rejected_total = 0
    approved_total = 0
    for p in projects:
        percent, _, _ = project_progress(p)
        total_percent += percent
        for m in p.milestones:
            if m.status == "pending":
                pending_total += 1
            elif m.status == "rejected":
                rejected_total += 1
            elif m.status == "approved":
                approved_total += 1
    avg_percent = round(total_percent / site_count) if site_count else 0
    return {
        "projects": projects,
        "site_count": site_count,
        "avg_percent": avg_percent,
        "pending_total": pending_total,
        "rejected_total": rejected_total,
        "approved_total": approved_total,
    }


def build_site_report_pdf(project):
    """Build a simple, plain (no decorative design) PDF summary report for one site."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                             topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                             leftMargin=0.75 * inch, rightMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=16)
    normal = ParagraphStyle("NormalStyle", parent=styles["Normal"], fontName="Helvetica", fontSize=12, leading=16)
    heading = ParagraphStyle("HeadingStyle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13)

    percent, approved, total = project_progress(project)
    inspector = User.query.get(project.inspector_id)
    installer = User.query.get(project.installer_id)

    elements = [
        Paragraph("Site Summary Report", title_style),
        Spacer(1, 12),
        Paragraph(f"Site Name: {project.site_name}", normal),
        Paragraph(f"Address: {project.address or 'Not given'}", normal),
        Paragraph(f"Installer: {installer.name} ({installer.email})", normal),
        Paragraph(f"Municipal Inspector: {inspector.name} ({inspector.email})", normal),
        Paragraph(f"Site Created: {project.created_at.strftime('%Y-%m-%d %H:%M')}", normal),
        Paragraph(f"Report Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC", normal),
        Spacer(1, 8),
        Paragraph(f"Overall Progress: {approved} of {total} milestones approved ({percent}%)", normal),
        Spacer(1, 16),
        Paragraph("Milestone History", heading),
        Spacer(1, 8),
    ]

    table_data = [["Type", "Status", "Uploaded", "Reviewed", "Note"]]
    milestones = sorted(project.milestones, key=lambda m: m.uploaded_at)
    for m in milestones:
        table_data.append([
            m.milestone_type,
            m.status,
            m.uploaded_at.strftime("%Y-%m-%d %H:%M"),
            m.reviewed_at.strftime("%Y-%m-%d %H:%M") if m.reviewed_at else "—",
            m.note or "—",
        ])

    if len(table_data) == 1:
        table_data.append(["No milestones uploaded", "", "", "", ""])

    table = Table(table_data, colWidths=[1.4 * inch, 0.9 * inch, 1.2 * inch, 1.2 * inch, 1.5 * inch])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_business_key():
    while True:
        key = "MUNI-" + secrets.token_hex(3).upper()
        if not User.query.filter_by(business_key=key).first():
            return key


def inspector_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "inspector":
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def installer_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "installer":
            abort(403)
        return func(*args, **kwargs)
    return wrapper


# ---------- Auth routes ----------

@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "inspector":
            return redirect(url_for("inspector_dashboard"))
        return redirect(url_for("installer_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("index"))
        flash("Wrong email or password.", "error")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    role = request.args.get("role", "installer")
    if request.method == "POST":
        role = request.form.get("role", "installer")
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        security_question = request.form.get("security_question", SECURITY_QUESTIONS[0])
        security_answer = request.form.get("security_answer", "").strip()

        if not name or not email or not password or not security_answer:
            flash("Please fill in all fields, including the security question.", "error")
            return render_template("signup.html", role=role, security_questions=SECURITY_QUESTIONS)

        if User.query.filter_by(email=email).first():
            flash("Email is already registered.", "error")
            return render_template("signup.html", role=role, security_questions=SECURITY_QUESTIONS)

        if role == "inspector":
            new_user = User(
                name=name, email=email,
                password_hash=generate_password_hash(password),
                role="inspector",
                business_key=generate_business_key(),
                security_question=security_question,
                security_answer_hash=generate_password_hash(security_answer.lower()),
            )
            db.session.add(new_user)
            db.session.commit()
            flash(f"Account created. Your business key is {new_user.business_key} "
                  f"— share it with your installers.", "success")
            login_user(new_user)
            return redirect(url_for("inspector_dashboard"))

        else:  # installer
            key = request.form.get("business_key", "").strip().upper()
            inspector = User.query.filter_by(business_key=key, role="inspector").first()
            if not inspector:
                flash("That business key was not found. Check with your municipal inspector.", "error")
                return render_template("signup.html", role=role, security_questions=SECURITY_QUESTIONS)

            new_user = User(
                name=name, email=email,
                password_hash=generate_password_hash(password),
                role="installer",
                inspector_id=inspector.id,
                security_question=security_question,
                security_answer_hash=generate_password_hash(security_answer.lower()),
            )
            db.session.add(new_user)
            db.session.commit()
            flash("Account created. You are now linked to your municipal inspector.", "success")
            login_user(new_user)
            return redirect(url_for("installer_dashboard"))

    return render_template("signup.html", role=role, security_questions=SECURITY_QUESTIONS)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("No account found with that email.", "error")
            return render_template("forgot_password.html", step=1)
        return render_template("forgot_password.html", step=2, email=user.email,
                                security_question=user.security_question)
    return render_template("forgot_password.html", step=1)


@app.route("/reset-password", methods=["POST"])
def reset_password():
    email = request.form.get("email", "").strip().lower()
    answer = request.form.get("security_answer", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("No account found with that email.", "error")
        return redirect(url_for("forgot_password"))

    if not user.check_security_answer(answer):
        flash("That answer doesn't match our records.", "error")
        return render_template("forgot_password.html", step=2, email=user.email,
                                security_question=user.security_question)

    if not new_password or new_password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template("forgot_password.html", step=2, email=user.email,
                                security_question=user.security_question)

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash("Password reset. You can now log in.", "success")
    return redirect(url_for("login"))


# ---------- Installer routes ----------

@app.route("/installer/dashboard")
@login_required
@installer_required
def installer_dashboard():
    projects = Project.query.filter_by(installer_id=current_user.id).order_by(Project.created_at.desc()).all()
    project_progress_map = {p.id: project_progress(p) for p in projects}
    return render_template("installer_dashboard.html", projects=projects,
                            project_progress_map=project_progress_map)


@app.route("/installer/project/new", methods=["GET", "POST"])
@login_required
@installer_required
def new_project():
    if request.method == "POST":
        site_name = request.form.get("site_name", "").strip()
        address = request.form.get("address", "").strip()
        if not site_name:
            flash("Site name is required.", "error")
            return render_template("new_project.html")

        project = Project(
            site_name=site_name,
            address=address,
            installer_id=current_user.id,
            inspector_id=current_user.inspector_id,
        )
        db.session.add(project)
        db.session.commit()
        flash("Site created. Now upload the blueprint, photos, and wiring diagram.", "success")
        return redirect(url_for("project_detail", project_id=project.id))

    return render_template("new_project.html")


@app.route("/installer/project/<int:project_id>", methods=["GET", "POST"])
@login_required
@installer_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if project.installer_id != current_user.id:
        abort(403)

    if request.method == "POST":
        milestone_type = request.form.get("milestone_type")
        file = request.files.get("file")

        if milestone_type not in MILESTONE_TYPES:
            flash("Choose a valid milestone type.", "error")
            return redirect(url_for("project_detail", project_id=project.id))

        file_path = None
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("File type not allowed. Use image, PDF, DWG, or DOCX.", "error")
                return redirect(url_for("project_detail", project_id=project.id))

            if USE_CLOUDINARY:
                # Upload directly to Cloudinary. The returned HTTPS URL is
                # stored in PostgreSQL instead of storing the actual file in
                # the database. This survives Render restarts/redeployments.
                public_id = f"p{project.id}_{secrets.token_hex(8)}_{secure_filename(file.filename)}"
                upload_result = cloudinary.uploader.upload(
                    file,
                    public_id=public_id,
                    folder="solar-panel-system",
                    resource_type="auto",
                    use_filename=False,
                    unique_filename=False,
                )
                file_path = upload_result["secure_url"]
            else:
                # Local development fallback.
                filename = secure_filename(f"p{project.id}_{datetime.utcnow().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                file_path = filename

        milestone = Milestone(
            project_id=project.id,
            milestone_type=milestone_type,
            file_path=file_path,
            status="pending",
        )
        db.session.add(milestone)
        db.session.commit()
        flash("Uploaded. Waiting for municipal inspector sign-off.", "success")
        return redirect(url_for("project_detail", project_id=project.id))

    milestones = Milestone.query.filter_by(project_id=project.id).order_by(Milestone.uploaded_at.desc()).all()
    percent, approved, total = project_progress(project)
    return render_template("project_detail.html", project=project, milestones=milestones,
                            milestone_types=MILESTONE_TYPES, is_inspector=False,
                            progress_percent=percent, progress_approved=approved, progress_total=total)


# ---------- Inspector routes ----------

@app.route("/inspector/dashboard")
@login_required
@inspector_required
def inspector_dashboard():
    installers = User.query.filter_by(inspector_id=current_user.id, role="installer").all()
    installer_ids = [i.id for i in installers]
    projects = Project.query.filter(Project.installer_id.in_(installer_ids)).order_by(Project.created_at.desc()).all() if installer_ids else []
    pending_count = Milestone.query.join(Project).filter(
        Project.inspector_id == current_user.id, Milestone.status == "pending"
    ).count()

    project_progress_map = {p.id: project_progress(p) for p in projects}

    return render_template("inspector_dashboard.html", installers=installers, projects=projects,
                            pending_count=pending_count, business_key=current_user.business_key,
                            project_progress_map=project_progress_map)


@app.route("/inspector/installer/<int:installer_id>")
@login_required
@inspector_required
def inspector_installer_progress(installer_id):
    installer = User.query.get_or_404(installer_id)
    if installer.inspector_id != current_user.id or installer.role != "installer":
        abort(403)
    stats = installer_stats(installer)
    project_progress_map = {p.id: project_progress(p) for p in stats["projects"]}
    return render_template("installer_progress.html", installer=installer, stats=stats,
                            project_progress_map=project_progress_map)


@app.route("/inspector/project/<int:project_id>")
@login_required
@inspector_required
def inspector_project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if project.inspector_id != current_user.id:
        abort(403)
    milestones = Milestone.query.filter_by(project_id=project.id).order_by(Milestone.uploaded_at.desc()).all()
    percent, approved, total = project_progress(project)
    return render_template("project_detail.html", project=project, milestones=milestones,
                            milestone_types=MILESTONE_TYPES, is_inspector=True,
                            progress_percent=percent, progress_approved=approved, progress_total=total)


@app.route("/inspector/project/<int:project_id>/report")
@login_required
@inspector_required
def download_report(project_id):
    project = Project.query.get_or_404(project_id)
    if project.inspector_id != current_user.id:
        abort(403)
    pdf_buffer = build_site_report_pdf(project)
    safe_name = secure_filename(project.site_name) or f"site-{project.id}"
    filename = f"{safe_name}-summary-report.pdf"
    return (
        pdf_buffer.getvalue(),
        200,
        {
            "Content-Type": "application/pdf",
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )


@app.route("/inspector/project/<int:project_id>/delete", methods=["POST"])
@login_required
@inspector_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.inspector_id != current_user.id:
        abort(403)
    site_name = project.site_name
    db.session.delete(project)  # cascades to milestones
    db.session.commit()
    flash(f'Site "{site_name}" was deleted. It is also removed from the installer\'s view.', "success")
    return redirect(url_for("inspector_dashboard"))


@app.route("/inspector/milestone/<int:milestone_id>/review", methods=["POST"])
@login_required
@inspector_required
def review_milestone(milestone_id):
    milestone = Milestone.query.get_or_404(milestone_id)
    project = Project.query.get_or_404(milestone.project_id)
    if project.inspector_id != current_user.id:
        abort(403)

    decision = request.form.get("decision")
    note = request.form.get("note", "").strip()

    if decision not in ("approved", "rejected"):
        flash("Invalid decision.", "error")
        return redirect(url_for("inspector_project_detail", project_id=project.id))

    milestone.status = decision
    milestone.note = note if decision == "rejected" else None
    milestone.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f"Milestone marked as {decision}.", "success")
    return redirect(url_for("inspector_project_detail", project_id=project.id))


# ---------- File serving ----------

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    # Cloudinary URLs are stored directly in the milestone record.
    # Local filenames continue to work during development.
    if filename.startswith(("https://", "http://")):
        return redirect(filename)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------- Database setup ----------
# Runs both when started directly (python app.py) and under a production
# server like gunicorn, so the tables always exist before the first request.
with app.app_context():
    db.create_all()

# ---------- Entry point ----------

if __name__ == "__main__":
    app.run(debug=True)
