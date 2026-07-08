import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy import func, and_
from app.models import Report, Assignment, Team, Status
from app import db
from app.services.whatsapp_bot import send_whatsapp_message

supervisor_bp = Blueprint('supervisor', __name__, url_prefix='/supervisor')


def es_supervisor():
    if not current_user.is_authenticated:
        return False
    return (
        current_user.team is not None and
        current_user.team.nombre and
        current_user.team.nombre.strip().lower() == 'supervisor'
    )


@supervisor_bp.route('/dashboard')
@login_required
def dashboard_supervisor():
    if not es_supervisor():
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for('auth.login'))

    tipo = request.args.get('tipo')
    subtipo = request.args.get('subtipo')
    localidad = request.args.get('localidad')
    status_id = request.args.get('status_id', type=int)

    reportes_query = Report.query.order_by(Report.timestamp.desc())

    if tipo:
        reportes_query = reportes_query.filter(Report.tipo == tipo)
    if subtipo:
        reportes_query = reportes_query.filter(Report.subtipo == subtipo)
    if localidad:
        reportes_query = reportes_query.filter(Report.localidad == localidad)

    reportes = reportes_query.all()

    if status_id:
        reportes = [
            r for r in reportes
            if r.asignaciones and r.asignaciones[-1].status_id == status_id
        ]

    for r in reportes:
        asignacion = r.asignaciones[-1] if r.asignaciones else None
        if asignacion:
            r.materiales_utilizados = asignacion.materiales_utilizados
            r.observaciones = asignacion.observaciones
            r.evidencia_cuadrilla = asignacion.evidencia_cuadrilla
            r.motivo_reasignacion = asignacion.motivo_reasignacion
            r.cuadrilla = asignacion.team.nombre if asignacion.team else "Sin cuadrilla"
            r.estado = asignacion.status.descripcion if asignacion.status else "Sin estado"
            if asignacion.status and asignacion.status.descripcion.lower() == "en revisión":
                r.estado_color = "#ffcccc"
            else:
                r.estado_color = None
        else:
            r.materiales_utilizados = None
            r.observaciones = None
            r.evidencia_cuadrilla = None
            r.motivo_reasignacion = None
            r.cuadrilla = "Sin asignación"
            r.estado = "Sin estado"

    tipos_disponibles = [t[0] for t in db.session.query(Report.tipo).distinct().all()]
    subtipos_disponibles = [s[0] for s in db.session.query(Report.subtipo).distinct().all()]
    localidades_disponibles = [l[0] for l in db.session.query(Report.localidad).distinct().all()]
    estados_disponibles = db.session.query(Status.id, Status.descripcion).all()
    cuadrillas_disponibles = db.session.query(Team.id, Team.nombre).all()

    return render_template(
        'supervisor/supervisor_dashboard.html',
        reportes=reportes,
        tipos_disponibles=tipos_disponibles,
        subtipos_disponibles=subtipos_disponibles,
        localidades_disponibles=localidades_disponibles,
        cuadrillas_disponibles=cuadrillas_disponibles,
        estados_disponibles=estados_disponibles,
        tipo_seleccionado=tipo,
        subtipo_seleccionado=subtipo,
        localidad_seleccionada=localidad,
        status_id_seleccionado=status_id
    )


@supervisor_bp.route('/dashboard/exportar_excel', methods=['GET'])
@login_required
def exportar_excel_supervisor():
    from io import BytesIO
    import pandas as pd
    from flask import send_file

    if not es_supervisor():
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for('auth.login'))

    tipo = request.args.get('tipo')
    subtipo = request.args.get('subtipo')
    localidad = request.args.get('localidad')
    status_id = request.args.get('status_id', type=int)

    subq = db.session.query(
        Assignment.report_id,
        func.max(Assignment.timestamp).label('max_timestamp')
    ).group_by(Assignment.report_id).subquery()

    ultima_asignacion = db.session.query(Assignment).join(
        subq,
        and_(
            Assignment.report_id == subq.c.report_id,
            Assignment.timestamp == subq.c.max_timestamp
        )
    ).subquery()

    asignaciones_query = db.session.query(Assignment).join(
        ultima_asignacion,
        Assignment.id == ultima_asignacion.c.id
    ).join(
        Report,
        Assignment.report_id == Report.id
    ).join(
        Status,
        Assignment.status_id == Status.id,
        isouter=True
    ).join(
        Team,
        Assignment.team_id == Team.id,
        isouter=True
    )

    if tipo:
        asignaciones_query = asignaciones_query.filter(Report.tipo == tipo)
    if subtipo:
        asignaciones_query = asignaciones_query.filter(Report.subtipo == subtipo)
    if localidad:
        asignaciones_query = asignaciones_query.filter(Report.localidad == localidad)
    if status_id:
        asignaciones_query = asignaciones_query.filter(Assignment.status_id == status_id)

    asignaciones = asignaciones_query.order_by(Assignment.id.desc()).all()

    data = []
    for asignacion in asignaciones:
        reporte = asignacion.report
        data.append({
            'ID': reporte.id,
            'Fecha': reporte.timestamp.strftime("%Y-%m-%d %H:%M:%S") if reporte.timestamp else '',
            'Número de Cuenta': reporte.numero_cuenta or '',
            'Teléfono': reporte.telefono or '',
            'Reportante': reporte.reportante or '',
            'Tipo': reporte.tipo or '',
            'Subtipo': reporte.subtipo or '',
            'Calle': reporte.calle or '',
            'Número': reporte.numero or '',
            'Localidad': reporte.localidad or '',
            'Entre Calles': reporte.entre_calles or '',
            'Descripción': reporte.descripcion_problema or '',
            'Estado': asignacion.status.descripcion if asignacion.status else '',
            'Motivo de Reasignación': asignacion.motivo_reasignacion or '',
            'Observaciones': asignacion.observaciones or '',
            'Materiales Utilizados': asignacion.materiales_utilizados or '',
            'Evidencia Cuadrilla': asignacion.evidencia_cuadrilla or '',
        })

    df = pd.DataFrame(data)
    output = BytesIO()

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reportes')
        workbook = writer.book
        worksheet = writer.sheets['Reportes']

        format_en_revision = workbook.add_format({'bg_color': '#FFFACD'})
        estado_col_idx = df.columns.get_loc("Estado")

        for row_num, estado in enumerate(df["Estado"], start=1):
            if estado and estado.lower() == "en revisión":
                worksheet.set_row(row_num, cell_format=format_en_revision)

    output.seek(0)
    return send_file(output, download_name="reportes_supervisor.xlsx", as_attachment=True)


@supervisor_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    uploads_dir = os.path.abspath(os.path.join(current_app.root_path, '..', 'uploads'))

    if '..' in filename or filename.startswith('/'):
        abort(404)

    return send_from_directory(uploads_dir, filename)


@supervisor_bp.route('/historial/<int:report_id>', methods=['GET'])
@login_required
def historial_reporte_supervisor(report_id):
    if not es_supervisor():
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for('auth.login'))

    report = Report.query.get_or_404(report_id)
    historial = Assignment.query.filter_by(report_id=report_id).order_by(Assignment.timestamp.desc()).all()
    estados_disponibles = Status.query.all()
    cuadrillas_disponibles = Team.query.all()

    return render_template(
        'supervisor/historial_reporte_supervisor.html',
        reporte=report,
        asignaciones=historial,
        estados_disponibles=estados_disponibles,
        cuadrillas_disponibles=cuadrillas_disponibles
    )


@supervisor_bp.route('/historial/<int:report_id>/cambiar_estado', methods=['POST'])
@login_required
def cambiar_estado_reporte(report_id):
    if not es_supervisor():
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for('auth.login'))

    report = Report.query.get_or_404(report_id)
    nuevo_status_id = request.form.get('status_id', type=int)
    nueva_team_id = request.form.get('team_id', type=int)
    observaciones = request.form.get('observaciones') or None

    if not nuevo_status_id:
        flash("Debe seleccionar un estado.", "warning")
        return redirect(url_for('supervisor.historial_reporte_supervisor', report_id=report_id))

    ultima_asignacion = report.asignaciones[-1] if report.asignaciones else None
    nueva_asignacion = Assignment(
        report_id=report.id,
        team_id=nueva_team_id if nueva_team_id else (ultima_asignacion.team_id if ultima_asignacion else None),
        status_id=nuevo_status_id,
        observaciones=observaciones,
        materiales_utilizados=None,
        evidencia_cuadrilla=None
    )
    db.session.add(nueva_asignacion)
    db.session.commit()

    # WhatsApp solo si es Finalizado (id=4)
    if nuevo_status_id == 4:
        try:
            telefono = str(report.telefono).strip()
            if not telefono.startswith("+1"):
                telefono = f"+52{telefono}"

            mensaje = (
                f"✅ Estimado {report.reportante}, su reporte #{report.id} ha sido atendido.\n"
                f"📍 Cuadrilla: {nueva_asignacion.team.nombre if nueva_asignacion.team else 'N/A'}\n"
                f"📅 Fecha: {nueva_asignacion.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
                "Muchas gracias por confiar en nosotros."
            )
            send_whatsapp_message(telefono, mensaje)
        except Exception as e:
            print("❌ Error enviando WhatsApp:", str(e))

    flash("Reporte actualizado correctamente.", "success")
    return redirect(url_for('supervisor.historial_reporte_supervisor', report_id=report_id))


@supervisor_bp.route('/historial/<int:report_id>/rechazar', methods=['POST'])
@login_required
def rechazar_reporte(report_id):
    if not es_supervisor():
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for('auth.login'))

    report = Report.query.get_or_404(report_id)
    ultima_asignacion = report.asignaciones[-1] if report.asignaciones else None
    motivo = request.form.get('motivo', 'Sin motivo especificado')

    # Crear nueva asignación con estado "En Proceso" o "Pendiente"
    nueva_asignacion = Assignment(
        report_id=report.id,
        team_id=ultima_asignacion.team_id if ultima_asignacion else None,
        status_id=2,  # Por ejemplo: 2 = "En Proceso"
        observaciones=f"Rechazado por supervisor: {motivo}"
    )
    db.session.add(nueva_asignacion)
    db.session.commit()

    # Enviar WhatsApp al reportante
    try:
        telefono = str(report.telefono).strip()
        if not telefono.startswith("+1"):
            telefono = f"+52{telefono}"

        mensaje = (
            f"⚠️ Estimado {report.reportante}, su reporte #{report.id} requiere corrección.\n"
            f"📍 Cuadrilla: {nueva_asignacion.team.nombre if nueva_asignacion.team else 'N/A'}\n"
            f"📅 Fecha: {nueva_asignacion.timestamp.strftime('%d/%m/%Y %H:%M')}\n"
            f"Motivo: {motivo}\n\n"
            "Por favor, la cuadrilla realizará las correcciones necesarias."
        )
        send_whatsapp_message(telefono, mensaje)
    except Exception as e:
        print("❌ Error enviando WhatsApp:", str(e))

    flash("❌ Reporte devuelto a la cuadrilla para corrección.", "warning")
    return redirect(url_for('supervisor.historial_reporte_supervisor', report_id=report.id))

@supervisor_bp.route('/aprobar/<int:assignment_id>', methods=['POST'])
@login_required
def aprobar_reporte(assignment_id):
    if not es_supervisor():
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for('auth.login'))

    # Obtener la asignación y reporte
    asignacion = Assignment.query.get_or_404(assignment_id)
    report = asignacion.report

    # Crear nueva asignación con estado "Finalizado" (id=4)
    nueva_asignacion = Assignment(
        report_id=report.id,
        team_id=asignacion.team_id,
        status_id=4,  # Finalizado
        observaciones="Reporte aprobado por supervisor",
        materiales_utilizados=asignacion.materiales_utilizados,
        evidencia_cuadrilla=asignacion.evidencia_cuadrilla
    )
    db.session.add(nueva_asignacion)
    db.session.commit()

    # Preparar número de WhatsApp con formato sandbox
    telefono = str(report.telefono).strip()
    if not telefono.startswith("whatsapp:"):
        telefono = "whatsapp:" + (telefono if telefono.startswith("+") else "+52" + telefono)

    # Función de envío de WhatsApp segura
    def enviar_whatsapp_sandbox(reportante, telefono, report_id, team_nombre, timestamp):
        try:
            mensaje = (
                f"✅ Estimado {reportante}, su reporte #{report_id} ha sido atendido y aprobado.\n"
                f"📍 Cuadrilla: {team_nombre}\n"
                f"📅 Fecha: {timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
                "Muchas gracias por confiar en nosotros."
            )
            msg = send_whatsapp_message(telefono, mensaje)
            if msg:
                print(f"✅ WhatsApp enviado, SID: {msg.sid}")
        except Exception as e:
            print(f"❌ Error enviando WhatsApp: {e}")

    # Enviar WhatsApp al reportante
    enviar_whatsapp_sandbox(
        report.reportante,
        telefono,
        report.id,
        nueva_asignacion.team.nombre if nueva_asignacion.team else "N/A",
        nueva_asignacion.timestamp
    )

    flash("Reporte aprobado correctamente.", "success")
    return redirect(url_for('supervisor.dashboard_supervisor'))

@supervisor_bp.route('/test_whatsapp')
@login_required
def test_whatsapp():
    if not es_supervisor():
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for('auth.login'))

    # Número de prueba configurado (o tu propio número registrado en el Sandbox)
    numero_prueba = "5213344431518"  # Cambia esto al número registrado
    numero_whatsapp = f"whatsapp:+{numero_prueba}"
    mensaje = "✅ Este es un mensaje de prueba desde el dashboard del supervisor."

    try:
        send_whatsapp_message(numero_whatsapp, mensaje)
        flash(f"✅ Mensaje de prueba enviado correctamente a {numero_whatsapp}.", "success")
    except Exception as e:
        error_text = str(e)
        if "21211" in error_text:
            flash(
                f"❌ Falló el envío: el número {numero_whatsapp} no está registrado en el sandbox de WhatsApp de Twilio.", 
                "danger"
            )
        else:
            flash(f"❌ Falló el envío, revisa la consola. Error: {error_text}", "danger")
        print("❌ Error enviando WhatsApp:", error_text)

    return redirect(url_for('supervisor.dashboard_supervisor'))
