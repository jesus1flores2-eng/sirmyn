import os
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from functools import wraps
from sqlalchemy import func

from app.models.report import Assignment
from app.models.team import Team
from app.models.status import Status
from app.extensions import db


# Blueprint
teams_bp = Blueprint('teams', __name__)


# ---- Decorador para restringir acceso a cuadrillas ----
def cuadrilla_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Debes iniciar sesión para acceder a esta sección.", "warning")
            return redirect(url_for('auth.login'))
        if current_user.id == 1:  # ID=1 reservado al admin
            flash("Esta sección es solo para cuadrillas.", "info")
            return redirect(url_for('admin.dashboard'))
        if current_user.team_id is None:
            flash("No tienes una cuadrilla asignada.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# ---- Dashboard de cuadrilla ----
@teams_bp.route('/cuadrilla/')
@login_required
@cuadrilla_required
def cuadrilla_dashboard():
    # Subconsulta para obtener la última asignación por reporte
    latest_assignments_subq = (
        db.session.query(
            Assignment.report_id,
            func.max(Assignment.id).label("max_id")
        )
        .group_by(Assignment.report_id)
        .subquery()
    )

    # Obtener solo las asignaciones más recientes de la cuadrilla actual
    assignments = (
        db.session.query(Assignment)
        .join(latest_assignments_subq, Assignment.id == latest_assignments_subq.c.max_id)
        .filter(
            Assignment.team_id == current_user.team_id,
            Assignment.status.has(Status.descripcion.in_(["Sin Asignar", "En proceso"]))
        )
        .all()
    )

    # Contar los reportes en revisión
    en_revision_count = (
        db.session.query(Assignment)
        .join(latest_assignments_subq, Assignment.id == latest_assignments_subq.c.max_id)
        .filter(
            Assignment.team_id == current_user.team_id,
            Assignment.status.has(Status.descripcion == "En revisión")
        )
        .count()
    )

    return render_template(
        'teams/dashboard.html',
        assignments=assignments,
        en_revision_count=en_revision_count,
        page_title="Samapa - Cuadrilla",
        section_name="Cuadrilla"
    )


# ---- Detalle de un reporte ----
@teams_bp.route('/cuadrilla/reporte/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
@cuadrilla_required
def report_detail(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    statuses = Status.query.all()
    all_teams = Team.query.all()

    # Para el navbar
    latest_assignments_subq = (
        db.session.query(
            Assignment.report_id,
            func.max(Assignment.id).label("max_id")
        )
        .group_by(Assignment.report_id)
        .subquery()
    )
    en_revision_count = (
        db.session.query(Assignment)
        .join(latest_assignments_subq, Assignment.id == latest_assignments_subq.c.max_id)
        .filter(
            Assignment.team_id == current_user.team_id,
            Assignment.status.has(Status.descripcion == "En revisión")
        )
        .count()
    )

    if request.method == 'POST':
        # Carpetas de almacenamiento
        evidencia_folder = os.path.join(current_app.root_path, 'static', 'evidencias', 'cuadrilla')
        materiales_folder = os.path.join(current_app.root_path, 'static', 'evidencias', 'materiales_utilizados')
        os.makedirs(evidencia_folder, exist_ok=True)
        os.makedirs(materiales_folder, exist_ok=True)

        # Evidencia de reparación
        evidencia_file = request.files.get('evidencia_cuadrilla')
        if evidencia_file and evidencia_file.filename != '':
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            ext = os.path.splitext(evidencia_file.filename)[1]
            filename = secure_filename(f"reporte-{assignment.report_id}_{timestamp}_cuadrilla{ext}")
            evidencia_file.save(os.path.join(evidencia_folder, filename))
            assignment.evidencia_cuadrilla = filename

        # Foto de materiales
        materiales_file = request.files.get('foto_materiales_utilizados')
        if materiales_file and materiales_file.filename != '':
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            ext = os.path.splitext(materiales_file.filename)[1]
            filename = secure_filename(f"reporte-{assignment.report_id}_{timestamp}_materiales{ext}")
            materiales_file.save(os.path.join(materiales_folder, filename))
            assignment.materiales_utilizados = filename

        # Observaciones
        assignment.observaciones = request.form.get('observaciones')

        # Actualizar estado solo si está permitido
        status_id = int(request.form.get('status_id'))
        estado_nombre = Status.query.get(status_id).descripcion.lower()
        if estado_nombre in ['en proceso', 'en revisión']:
            assignment.status_id = status_id
            db.session.commit()
            flash("Reporte actualizado correctamente.", "success")
        else:
            flash("Solo puedes actualizar reportes en proceso o en revisión.", "warning")

        return redirect(url_for('teams.report_detail', assignment_id=assignment.id))

    return render_template(
        'teams/report_detail.html',
        assignment=assignment,
        statuses=statuses,
        all_teams=all_teams,
        en_revision_count=en_revision_count
    )


# ---- Reasignar reporte a otra cuadrilla ----
@teams_bp.route('/cuadrilla/reasignar/<int:assignment_id>', methods=['POST'])
@login_required
@cuadrilla_required
def reasignar_reporte(assignment_id):
    old_assignment = Assignment.query.get_or_404(assignment_id)

    if old_assignment.team_id != current_user.team_id:
        flash("No tienes permiso para reasignar este reporte.", "danger")
        return redirect(url_for('teams.cuadrilla_dashboard'))

    new_team_id = request.form.get('new_team_id')
    motivo = request.form.get('motivo_reasignacion') or 'Sin motivo especificado'

    if not new_team_id:
        flash("Debes seleccionar una cuadrilla para reasignar.", "warning")
        return redirect(url_for('teams.report_detail', assignment_id=assignment_id))

    nueva_asignacion = Assignment(
        report_id=old_assignment.report_id,
        team_id=int(new_team_id),
        status_id=old_assignment.status_id,
        observaciones=(old_assignment.observaciones or '') + f"\nReasignado: {motivo}",
        evidencia_cuadrilla=old_assignment.evidencia_cuadrilla,
        materiales_utilizados=old_assignment.materiales_utilizados
    )

    db.session.add(nueva_asignacion)
    db.session.commit()

    flash("Reporte reasignado correctamente a otra cuadrilla.", "success")
    return redirect(url_for('teams.cuadrilla_dashboard'))


# ---- Vista de reportes en revisión ----
@teams_bp.route('/cuadrilla/en_revision/')
@login_required
@cuadrilla_required
def cuadrilla_en_revision():
    latest_assignments_subq = (
        db.session.query(
            Assignment.report_id,
            func.max(Assignment.id).label("max_id")
        )
        .group_by(Assignment.report_id)
        .subquery()
    )

    assignments = (
        db.session.query(Assignment)
        .join(latest_assignments_subq, Assignment.id == latest_assignments_subq.c.max_id)
        .filter(
            Assignment.team_id == current_user.team_id,
            Assignment.status.has(Status.descripcion == "En revisión")
        )
        .all()
    )

    return render_template('teams/en_revision.html', assignments=assignments)

@teams_bp.route('/cuadrilla/subir_evidencia/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
@cuadrilla_required
def subir_evidencia(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    statuses = Status.query.all()  # Para el select de estados

    # Contar reportes en revisión para el navbar
    latest_assignments_subq = (
        db.session.query(
            Assignment.report_id,
            func.max(Assignment.id).label("max_id")
        ).group_by(Assignment.report_id)
        .subquery()
    )

    en_revision_count = (
        db.session.query(Assignment)
        .join(latest_assignments_subq, Assignment.id == latest_assignments_subq.c.max_id)
        .filter(
            Assignment.team_id == current_user.team_id,
            Assignment.status.has(Status.descripcion == "En revisión")
        )
        .count()
    )

    if request.method == "POST":
        # Subida de evidencia
        evidencia_file = request.files.get('evidencia_cuadrilla')
        if evidencia_file and evidencia_file.filename != '':
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            ext = os.path.splitext(evidencia_file.filename)[1]
            filename = secure_filename(f"reporte-{assignment.report_id}_{timestamp}_cuadrilla{ext}")
            evidencia_folder = os.path.join(current_app.root_path, 'static', 'evidencias', 'cuadrilla')
            os.makedirs(evidencia_folder, exist_ok=True)
            evidencia_file.save(os.path.join(evidencia_folder, filename))
            assignment.evidencia_cuadrilla = filename

        materiales_file = request.files.get('foto_materiales_utilizados')
        if materiales_file and materiales_file.filename != '':
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            ext = os.path.splitext(materiales_file.filename)[1]
            filename = secure_filename(f"reporte-{assignment.report_id}_{timestamp}_materiales{ext}")
            materiales_folder = os.path.join(current_app.root_path, 'static', 'evidencias', 'materiales_utilizados')
            os.makedirs(materiales_folder, exist_ok=True)
            materiales_file.save(os.path.join(materiales_folder, filename))
            assignment.materiales_utilizados = filename

        assignment.observaciones = request.form.get('observaciones')

        # Actualizar estado si está permitido
        status_id = int(request.form.get('status_id'))
        estado_nombre = Status.query.get(status_id).descripcion.lower()
        if estado_nombre in ['en proceso', 'en revisión']:
            assignment.status_id = status_id
            db.session.commit()
            flash("Reporte actualizado correctamente.", "success")

            # Redirigir automáticamente al dashboard si el estado es "en revisión"
            if estado_nombre == 'en revisión':
                return redirect(url_for('teams.cuadrilla_dashboard'))

        else:
            flash("Solo puedes actualizar reportes en proceso o en revisión.", "warning")

        # Si no es "en revisión", quedarse en la misma página
        return redirect(url_for('teams.subir_evidencia', assignment_id=assignment.id))

    return render_template(
        'teams/subir_evidencia.html',
        assignment=assignment,
        statuses=statuses,
        en_revision_count=en_revision_count
    )


@teams_bp.route('/cuadrilla/reasignar/<int:assignment_id>', methods=['GET'])
@login_required
@cuadrilla_required
def mostrar_form_reasignar(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    all_teams = Team.query.all()

    return render_template(
        'teams/reasignar_reporte.html',
        assignment=assignment,
        all_teams=all_teams
    )
