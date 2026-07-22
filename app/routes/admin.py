from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_login import login_required, current_user
import pandas as pd
import io
import os
import asyncio
import nest_asyncio
from datetime import datetime, timedelta
from app.models.report import Report, Assignment
from app.models.team import Team
from app.models.status import Status
from app.extensions import db
from app.services.report_service import (
    obtener_reportes,
    obtener_reportes_filtrados,
    duplicar_reporte,
    obtener_tipos_unicos,
    obtener_subtipos_unicos,
    obtener_localidades_unicas
)
from flask import current_app, send_from_directory
from functools import wraps
from sqlalchemy import desc, func, and_
from sqlalchemy.orm import aliased
from app.models.user import User
from werkzeug.security import generate_password_hash
from app.services.whatsapp_bot import twilio_client, TWILIO_PHONE_NUMBER
from app.services.whatsapp_bot import send_whatsapp_message
from app.services.notification_service import notificar_asignacion_sync
from app.routes.telegram_routes import get_telegram_app
import logging

# ⭐⭐⭐ APLICAR NEST_ASYNCIO PARA PERMITIR LOOPS ANIDADOS ⭐⭐⭐
nest_asyncio.apply()

logger = logging.getLogger(__name__)

# -------------------------------------
# Decorador de administrador
# -------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Debes iniciar sesión como administrador.", "warning")
            return redirect(url_for('auth.login'))
        if not current_user.is_admin():
            flash("Acceso solo permitido para administradores.", "danger")
            return redirect(url_for('teams.cuadrilla_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------
# Blueprint
# -------------------------------------
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# -------------------------------------
# Dashboard
# -------------------------------------
@admin_bp.route('/', methods=['GET'])
@login_required
@admin_required
def dashboard():
    tipo = request.args.get('tipo')
    subtipo = request.args.get('subtipo')
    localidad = request.args.get('localidad')
    team_id = request.args.get('team_id')
    status_id = request.args.get('status_id')
    plataforma = request.args.get('plataforma')

    if any([tipo, subtipo, localidad, team_id, status_id, plataforma]):
        reportes = obtener_reportes_filtrados(tipo, subtipo, localidad, team_id, status_id)
        if plataforma:
            reportes = [r for r in reportes if r.plataforma == plataforma]
    else:
        reportes = obtener_reportes()

    subq = db.session.query(
        Assignment.report_id,
        func.max(Assignment.timestamp).label('max_ts')
    ).filter(
        Assignment.report_id.in_([r.id for r in reportes])
    ).group_by(Assignment.report_id).subquery()

    A2 = aliased(Assignment)
    asignaciones = db.session.query(A2).join(
        subq,
        and_(A2.report_id == subq.c.report_id, A2.timestamp == subq.c.max_ts)
    ).all()

    asignaciones_por_reporte = {a.report_id: a for a in asignaciones}

    for r in reportes:
        ultima = asignaciones_por_reporte.get(r.id)
        if ultima:
            r.team_id = ultima.team_id
            r.status_id = ultima.status_id
            team = Team.query.get(ultima.team_id) if ultima.team_id else None
            status = Status.query.get(ultima.status_id) if ultima.status_id else None
            r.cuadrilla = team.nombre if team else '—'
            r.estado = status.descripcion if status else '—'
            r.estado_color = status.color if status and status.color else '#ccc'
            r.materiales_utilizados = ultima.materiales_utilizados
            r.observaciones = ultima.observaciones
            r.evidencia_cuadrilla = ultima.evidencia_cuadrilla
        else:
            r.team_id = None
            r.status_id = None
            r.cuadrilla = '—'
            r.estado = '—'
            r.estado_color = '#ccc'
            r.materiales_utilizados = None
            r.observaciones = None
            r.evidencia_cuadrilla = None

    try:
        team_id_seleccionado = int(team_id) if team_id else ''
    except ValueError:
        team_id_seleccionado = ''
    try:
        status_id_seleccionado = int(status_id) if status_id else ''
    except ValueError:
        status_id_seleccionado = ''

    tipos_disponibles = obtener_tipos_unicos()
    subtipos_disponibles = obtener_subtipos_unicos()
    localidades_disponibles = obtener_localidades_unicas()
    cuadrillas_disponibles = [(t.id, t.nombre) for t in Team.query.all()]
    estados_disponibles = [(s.id, s.descripcion) for s in Status.query.all()]
    plataformas_disponibles = ['telegram', 'whatsapp', 'ventanilla', 'web']
    plataforma_seleccionada = plataforma if plataforma else ''

    return render_template(
        'admin/dashboard.html',
        reportes=reportes,
        tipo_seleccionado=tipo,
        subtipo_seleccionado=subtipo,
        localidad_seleccionada=localidad,
        team_id_seleccionado=team_id_seleccionado,
        status_id_seleccionado=status_id_seleccionado,
        plataforma_seleccionada=plataforma_seleccionada,
        tipos_disponibles=tipos_disponibles,
        subtipos_disponibles=subtipos_disponibles,
        localidades_disponibles=localidades_disponibles,
        cuadrillas_disponibles=cuadrillas_disponibles,
        estados_disponibles=estados_disponibles,
        plataformas_disponibles=plataformas_disponibles
    )

# -------------------------------------
# Ver historial
# -------------------------------------
@admin_bp.route('/historial/<int:reporte_id>')
@login_required
@admin_required
def ver_historial(reporte_id):
    reporte = Report.query.get_or_404(reporte_id)
    asignaciones = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).all()
    return render_template('admin/historial.html', reporte=reporte, asignaciones=asignaciones)

# -------------------------------------
# Ruta para cambiar estado de un reporte desde Admin
# -------------------------------------
@admin_bp.route('/historial/<int:reporte_id>/cambiar_estado', methods=['POST'])
@login_required
@admin_required
def cambiar_estado_reporte_admin(reporte_id):
    reporte = Report.query.get_or_404(reporte_id)
    nuevo_status_id = request.form.get('status_id', type=int)
    nueva_team_id = request.form.get('team_id', type=int)
    observaciones = request.form.get('observaciones') or None

    if not nuevo_status_id:
        flash("Debe seleccionar un estado.", "warning")
        return redirect(url_for('admin.ver_historial', reporte_id=reporte_id))

    ultima_asignacion = reporte.asignaciones[-1] if reporte.asignaciones else None
    nueva_asignacion = Assignment(
        report_id=reporte.id,
        team_id=nueva_team_id if nueva_team_id else (ultima_asignacion.team_id if ultima_asignacion else None),
        status_id=nuevo_status_id,
        observaciones=observaciones,
        materiales_utilizados=None,
        evidencia_cuadrilla=None,
        motivo_reasignacion=None
    )
    db.session.add(nueva_asignacion)
    db.session.commit()

    status = Status.query.get(nuevo_status_id)
    if status and status.descripcion.strip().lower() in ["finalizado", "terminado", "atendido"]:
        from app.services.whatsapp_bot import send_whatsapp_message
        telefono = str(reporte.telefono).strip()
        if not telefono.startswith("+1"):
            telefono = "+52" + telefono
        mensaje = (
            f"✅ Estimado {reporte.reportante}, su reporte #{reporte.id} ha sido atendido.\n"
            f"📍 Cuadrilla: {nueva_asignacion.team.nombre if nueva_asignacion.team else 'N/A'}\n"
            f"📅 Fecha: {nueva_asignacion.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
            "Muchas gracias por confiar en nosotros."
        )
        logger.info(f"📲 Enviando WhatsApp a: {telefono}")
        send_whatsapp_message(telefono, mensaje)

    flash("Reporte actualizado correctamente.", "success")
    return redirect(url_for('admin.ver_historial', reporte_id=reporte_id))

# -------------------------------------
# Reasignar reporte
# -------------------------------------
@admin_bp.route('/reasignar/<int:reporte_id>', methods=['POST'])
@login_required
@admin_required
def reasignar_reporte(reporte_id):
    nueva_cuadrilla = request.form.get('nueva_team_id', type=int)
    motivo = request.form.get('motivo_reasignacion', '').strip()

    if not nueva_cuadrilla:
        flash("Debes seleccionar una cuadrilla para la reasignación.", "error")
        return redirect(url_for('admin.dashboard'))

    status_en_rev = Status.query.filter(func.lower(Status.descripcion) == 'en revisión').first()

    crear_asignacion_snapshot(
        reporte_id,
        team_id=nueva_cuadrilla,
        status_id=status_en_rev.id if status_en_rev else None,
        motivo_reasignacion=motivo if motivo else None
    )

    flash(f"Reporte #{reporte_id} reasignado a nueva cuadrilla.", "success")
    return redirect(url_for('admin.dashboard'))

# -------------------------------------
# Descargar Excel
# -------------------------------------
@admin_bp.route('/descargar_excel', methods=['GET'])
@login_required
@admin_required
def descargar_excel():
    tipo = request.args.get('tipo')
    subtipo = request.args.get('subtipo')
    localidad = request.args.get('localidad')
    team_id = request.args.get('team_id')
    status_id = request.args.get('status_id')
    plataforma = request.args.get('plataforma')

    if any([tipo, subtipo, localidad, team_id, status_id, plataforma]):
        reportes = obtener_reportes_filtrados(tipo, subtipo, localidad, team_id, status_id)
        if plataforma:
            reportes = [r for r in reportes if r.plataforma == plataforma]
    else:
        reportes = obtener_reportes()

    datos = []
    for r in reportes:
        asignacion = Assignment.query.filter_by(report_id=r.id).order_by(Assignment.timestamp.desc()).first()
        cuadrilla = Team.query.get(asignacion.team_id).nombre if asignacion and asignacion.team_id else '—'
        estado = Status.query.get(asignacion.status_id).descripcion if asignacion and asignacion.status_id else '—'
        materiales = asignacion.materiales_utilizados if asignacion else ''
        observaciones = asignacion.observaciones if asignacion else ''
        datos.append({
            'ID': r.id,
            'Fecha': r.timestamp.strftime('%Y-%m-%d %H:%M') if r.timestamp else '',
            'Número de Cuenta': r.numero_cuenta,
            'Teléfono': r.telefono,
            'Reportante': r.reportante,
            'Tipo': r.tipo,
            'Subtipo': r.subtipo,
            'Calle': r.calle,
            'Número': r.numero,
            'Localidad': r.localidad,
            'Entre Calles': r.entre_calles,
            'Descripción': r.descripcion_problema,
            'Materiales': materiales,
            'Observaciones': observaciones,
            'Cuadrilla': cuadrilla,
            'Estado': estado,
            'Plataforma': r.plataforma
        })

    df = pd.DataFrame(datos)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reportes')
    output.seek(0)
    return send_file(output, download_name='reportes.xlsx', as_attachment=True)

# -------------------------------------
# Asignar cuadrilla CON NOTIFICACIÓN A TELEGRAM
# -------------------------------------
@admin_bp.route('/asignar_cuadrilla/<int:report_id>', methods=['POST'])
@login_required
@admin_required
def asignar_cuadrilla(report_id):
    try:
        nueva_cuadrilla_id = request.form.get('team_id')
        if not nueva_cuadrilla_id:
            flash("Debes seleccionar una cuadrilla.", "error")
            return redirect(url_for('admin.dashboard'))
        
        nueva_cuadrilla_id = int(nueva_cuadrilla_id)
        reporte = Report.query.get_or_404(report_id)
        
        status_asignado = Status.query.filter(Status.descripcion.ilike('%asignado%')).first()
        if not status_asignado:
            status_asignado = Status(descripcion="Asignado", color="#007bff")
            db.session.add(status_asignado)
            db.session.commit()
        
        nueva_asignacion = Assignment(
            report_id=report_id,
            team_id=nueva_cuadrilla_id,
            status_id=status_asignado.id,
            timestamp=datetime.utcnow()
        )
        db.session.add(nueva_asignacion)
        db.session.commit()
        
        usuario_notificar = User.query.filter_by(team_id=nueva_cuadrilla_id).filter(User.telegram_id.isnot(None)).first()
        if not usuario_notificar:
            usuario_notificar = User.query.filter_by(team_id=nueva_cuadrilla_id).first()
        
        if usuario_notificar and usuario_notificar.telegram_id:
            success = notificar_asignacion_sync(report_id, usuario_notificar.id)
            if success:
                flash(f"✅ Reporte #{report_id} asignado a {nueva_asignacion.team.nombre}. Notificación enviada.", "success")
            else:
                flash(f"⚠️ Reporte #{report_id} asignado. Error en notificación.", "warning")
        else:
            cuadrilla_nombre = Team.query.get(nueva_cuadrilla_id).nombre
            flash(f"✅ Reporte #{report_id} asignado a {cuadrilla_nombre}. Sin usuarios con Telegram.", "info")
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error al asignar cuadrilla: {str(e)[:100]}", "danger")
        return redirect(url_for('admin.dashboard'))

# -------------------------------------
# Rutas de archivos
# -------------------------------------
@admin_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    nombre_archivo = os.path.basename(filename)
    extensiones_permitidas = {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.avi', '.pdf'}
    _, ext = os.path.splitext(nombre_archivo)
    ext = ext.lower()
    if not ext or ext not in extensiones_permitidas or '..' in filename or filename.startswith('/'):
        abort(404)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@admin_bp.route('/archivo/<path:filename>')
@login_required
def archivo_publico(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# -------------------------------------
# Gestión de status
# -------------------------------------
@admin_bp.route('/gestionar_status', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_status():
    if request.method == 'POST':
        descripcion = request.form.get('descripcion')
        color = request.form.get('color')
        if descripcion:
            nuevo_status = Status(descripcion=descripcion, color=color)
            db.session.add(nuevo_status)
            db.session.commit()
            flash('Estado creado exitosamente.', 'success')
            return redirect(url_for('admin.gestionar_status'))
    estados = Status.query.order_by(Status.id).all()
    return render_template('admin/gestionar_status.html', estados=estados)

@admin_bp.route('/crear_status', methods=['POST'])
@login_required
@admin_required
def crear_status():
    descripcion = request.form.get('descripcion')
    color = request.form.get('color', '#cccccc')
    if descripcion:
        nuevo = Status(descripcion=descripcion, color=color)
        db.session.add(nuevo)
        db.session.commit()
        flash('Estado creado correctamente.', 'success')
    return redirect(url_for('admin.gestionar_status'))

@admin_bp.route('/editar_status/<int:id>', methods=['POST'])
@login_required
@admin_required
def editar_status(id):
    estado = Status.query.get_or_404(id)
    estado.descripcion = request.form.get('descripcion')
    estado.color = request.form.get('color', '#cccccc')
    db.session.commit()
    flash('Estado actualizado.', 'success')
    return redirect(url_for('admin.gestionar_status'))

@admin_bp.route('/eliminar_status/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_status(id):
    estado = Status.query.get_or_404(id)
    db.session.delete(estado)
    db.session.commit()
    flash('Estado eliminado.', 'warning')
    return redirect(url_for('admin.gestionar_status'))

# -------------------------------------
# Gestión de usuarios y cuadrillas
# -------------------------------------
@admin_bp.route('/gestionar_cuadrillas', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_cuadrillas():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'cuadrilla')
        rol_especifico = request.form.get('rol_especifico') or role
        area = request.form.get('area')
        team_id = request.form.get('team_id') or None
        telegram_id = request.form.get('telegram_id') or None
        
        if not nombre or not username or not password:
            flash("Nombre, usuario y contraseña son obligatorios.", "warning")
            return redirect(url_for('admin.gestionar_cuadrillas'))

        if User.query.filter_by(username=username).first():
            flash("El nombre de usuario ya existe.", "error")
            return redirect(url_for('admin.gestionar_cuadrillas'))

        nuevo_usuario = User(
            nombre=nombre,
            username=username,
            role=role,
            rol_especifico=rol_especifico,
            area=area,
            team_id=team_id if team_id else None,
            telegram_id=telegram_id if telegram_id else None
        )
        nuevo_usuario.set_password(password)
        db.session.add(nuevo_usuario)
        db.session.commit()
        flash(f'Usuario {username} creado exitosamente como {role} ({rol_especifico}).', 'success')
        return redirect(url_for('admin.gestionar_cuadrillas'))

    usuarios = User.query.all()
    all_teams = Team.query.all()
    usuarios_por_cuadrilla = {}
    for team in all_teams:
        usuarios_por_cuadrilla[team.id] = User.query.filter_by(team_id=team.id).all()
    
    return render_template('admin/gestionar_cuadrillas.html', 
                         usuarios=usuarios, 
                         all_teams=all_teams,
                         usuarios_por_cuadrilla=usuarios_por_cuadrilla)

@admin_bp.route('/usuario/<int:user_id>/actualizar', methods=['POST'])
@login_required
@admin_required
def actualizar_usuario(user_id):
    try:
        usuario = User.query.get_or_404(user_id)
        nombre = request.form.get('nombre')
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        rol_especifico = request.form.get('rol_especifico') or role
        area = request.form.get('area')
        team_id = request.form.get('team_id')
        telegram_id = request.form.get('telegram_id')
        
        if not nombre or not username or not role:
            flash("Nombre, usuario y rol son obligatorios.", "warning")
            return redirect(url_for('admin.gestionar_cuadrillas'))
        
        if User.query.filter_by(username=username).first() and User.query.filter_by(username=username).first().id != usuario.id:
            flash("El nombre de usuario ya está en uso.", "error")
            return redirect(url_for('admin.gestionar_cuadrillas'))
        
        if telegram_id:
            telegram_existente = User.query.filter_by(telegram_id=telegram_id).first()
            if telegram_existente and telegram_existente.id != usuario.id:
                flash("Este Telegram ID ya está en uso.", "error")
                return redirect(url_for('admin.gestionar_cuadrillas'))
        
        usuario.nombre = nombre
        usuario.username = username
        usuario.role = role
        usuario.rol_especifico = rol_especifico
        usuario.area = area if area and area.strip() else None
        if password and password.strip():
            usuario.set_password(password)
        usuario.team_id = int(team_id) if team_id and team_id.strip() else None
        usuario.telegram_id = telegram_id if telegram_id and telegram_id.strip() else None
        db.session.commit()
        flash(f'Usuario {usuario.username} actualizado correctamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando usuario {user_id}: {e}")
        flash(f'Error al actualizar el usuario: {str(e)[:100]}', 'danger')
    
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/usuario/<int:user_id>/eliminar', methods=['POST'])
@login_required
@admin_required
def eliminar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    if usuario.id == current_user.id:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('admin.gestionar_cuadrillas'))
    username = usuario.username
    db.session.delete(usuario)
    db.session.commit()
    flash(f'Usuario {username} eliminado correctamente.', 'success')
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/actualizar_rol_usuario/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def actualizar_rol_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    nuevo_rol = request.form.get('role')
    if nuevo_rol in ['admin', 'director', 'supervisor', 'cuadrilla', 'jefe_area']:
        usuario.role = nuevo_rol
        db.session.commit()
        flash(f'Rol de {usuario.username} actualizado a {nuevo_rol}', 'success')
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/actualizar_area_usuario/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def actualizar_area_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    if usuario.role == 'director':
        usuario.area = request.form.get('area')
        db.session.commit()
        flash(f'Área de {usuario.username} actualizada', 'success')
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/editar_usuario/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def editar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    nuevo_telegram_id = request.form.get('nuevo_telegram_id')
    if nuevo_telegram_id:
        existente = User.query.filter_by(telegram_id=nuevo_telegram_id).first()
        if existente and existente.id != usuario.id:
            flash('Este Telegram ID ya está en uso.', 'error')
        else:
            usuario.telegram_id = nuevo_telegram_id if nuevo_telegram_id.strip() else None
            db.session.commit()
            flash(f'Telegram ID de {usuario.username} actualizado', 'success')
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/crear_cuadrilla', methods=['POST'])
@login_required
@admin_required
def crear_cuadrilla():
    try:
        nombre = request.form.get('nombre')
        area = request.form.get('area')
        descripcion = request.form.get('descripcion', '')
        if not nombre or not area:
            flash("El nombre y el área de la cuadrilla son obligatorios.", "warning")
            return redirect(url_for('admin.gestionar_cuadrillas'))
        if Team.query.filter_by(nombre=nombre).first():
            flash("Ya existe una cuadrilla con ese nombre.", "error")
            return redirect(url_for('admin.gestionar_cuadrillas'))
        nueva_cuadrilla = Team(nombre=nombre, area=area, descripcion=descripcion)
        db.session.add(nueva_cuadrilla)
        db.session.commit()
        flash(f'Cuadrilla "{nombre}" ({area}) creada correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear la cuadrilla: {str(e)[:100]}', 'danger')
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/editar_cuadrilla/<int:team_id>', methods=['POST'])
@login_required
@admin_required
def editar_cuadrilla(team_id):
    team = Team.query.get_or_404(team_id)
    nuevo_nombre = request.form.get('nombre')
    nueva_area = request.form.get('area')
    nueva_descripcion = request.form.get('descripcion', '')
    if not nuevo_nombre or not nueva_area:
        flash("El nombre y el área son obligatorios.", "warning")
        return redirect(url_for('admin.gestionar_cuadrillas'))
    team.nombre = nuevo_nombre
    team.area = nueva_area
    team.descripcion = nueva_descripcion
    db.session.commit()
    flash("Cuadrilla actualizada correctamente.", "success")
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/eliminar_cuadrilla/<int:team_id>', methods=['POST'])
@login_required
@admin_required
def eliminar_cuadrilla(team_id):
    team = Team.query.get_or_404(team_id)
    if Assignment.query.filter_by(team_id=team.id).count() > 0:
        flash("No se puede eliminar una cuadrilla con reportes asignados.", "danger")
        return redirect(url_for('admin.gestionar_cuadrillas'))
    for usuario in User.query.filter_by(team_id=team.id).all():
        db.session.delete(usuario)
    db.session.delete(team)
    db.session.commit()
    flash("Cuadrilla y usuarios asociados eliminados correctamente.", "warning")
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/historial_completo/<int:reporte_id>')
@login_required
@admin_required
def historial_completo(reporte_id):
    reporte = Report.query.get_or_404(reporte_id)
    asignaciones = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.asc()).all()
    return render_template('admin/historial.html', reporte=reporte, asignaciones=asignaciones)

@admin_bp.route('/admin/asignar_por_defecto/<int:report_id>', methods=['POST'])
@login_required
@admin_required
def asignar_por_defecto(report_id):
    reporte = Report.query.get_or_404(report_id)
    asignacion = Assignment.query.filter_by(report_id=reporte.id).first()
    if asignacion:
        if not asignacion.team_id:
            asignacion.team_id = 1
        if not asignacion.status_id:
            asignacion.status_id = 1
    else:
        asignacion = Assignment(report_id=reporte.id, team_id=1, status_id=1, timestamp=datetime.utcnow())
        db.session.add(asignacion)
    db.session.commit()
    flash(f'Reporte {report_id} asignado con valores por defecto.', 'success')
    return redirect(url_for('admin.dashboard'))

def crear_asignacion_snapshot(report_id, **overrides):
    reporte = Report.query.get_or_404(report_id)
    last = Assignment.query.filter_by(report_id=report_id).order_by(Assignment.timestamp.desc()).first()
    new = Assignment(
        report_id=report_id,
        team_id=overrides.get('team_id', last.team_id if last else None),
        status_id=overrides.get('status_id', last.status_id if last else None),
        materiales_utilizados=overrides.get('materiales_utilizados', last.materiales_utilizados if last else None),
        observaciones=overrides.get('observaciones', last.observaciones if last else None),
        evidencia_cuadrilla=overrides.get('evidencia_cuadrilla', last.evidencia_cuadrilla if last else None),
        motivo_reasignacion=overrides.get('motivo_reasignacion', last.motivo_reasignacion if last else None),
        timestamp=datetime.utcnow()
    )
    db.session.add(new)
    db.session.commit()
    return new

@admin_bp.route('/asignar_estado/<int:reporte_id>', methods=['POST'])
@login_required
@admin_required
def asignar_estado(reporte_id):
    status_id = request.form.get('status_id')
    if status_id:
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        if not asignacion:
            asignacion = Assignment(report_id=reporte_id)
            db.session.add(asignacion)
        asignacion.status_id = status_id
        asignacion.timestamp = datetime.utcnow()
        db.session.commit()
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/asignar_reporte', methods=['POST'])
def asignar_reporte():
    try:
        data = request.get_json()
        reporte_id = data.get('reporte_id')
        user_id = data.get('user_id')
        team_id = data.get('team_id')
        nueva_asignacion = Assignment(
            report_id=reporte_id,
            team_id=team_id,
            status_id=Status.query.filter_by(descripcion="Asignado").first().id,
            timestamp=datetime.utcnow()
        )
        db.session.add(nueva_asignacion)
        db.session.commit()
        if user_id:
            notificar_asignacion_sync(reporte_id, user_id)
        return jsonify({"success": True, "message": f"Reporte #{reporte_id} asignado y notificado"})
    except Exception as e:
        logger.error(f"Error asignando reporte: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/directores_por_area/<area>', methods=['GET'])
@login_required
@admin_required
def api_directores_por_area(area):
    try:
        directores = User.query.filter_by(role='director', area=area, is_active=True).all()
        resultado = [{'id': d.id, 'nombre': d.nombre, 'username': d.username, 'telegram_id': d.telegram_id, 'area': d.area} for d in directores]
        return jsonify({"success": True, "area": area, "count": len(resultado), "directores": resultado}), 200
    except Exception as e:
        logger.error(f"Error obteniendo directores: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/cuadrillas_por_area/<area>', methods=['GET'])
@login_required
@admin_required
def api_cuadrillas_por_area(area):
    try:
        cuadrillas = Team.query.filter(Team.nombre.ilike(f"%{area}%")).filter(Team.nombre != "Sin asignar").all()
        if not cuadrillas:
            cuadrillas = Team.query.filter(Team.nombre != "Sin asignar").all()
        resultado = [{'id': c.id, 'nombre': c.nombre, 'descripcion': c.descripcion or '', 'usuarios': User.query.filter_by(team_id=c.id).count()} for c in cuadrillas]
        return jsonify({"success": True, "area": area, "count": len(resultado), "cuadrillas": resultado}), 200
    except Exception as e:
        logger.error(f"Error obteniendo cuadrillas: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/actualizar_roles_existentes', methods=['POST'])
@login_required
@admin_required
def actualizar_roles_existentes():
    try:
        admin_user = User.query.filter_by(username='Admin').first()
        if admin_user:
            admin_user.role = 'admin'
        supervisores = User.query.filter_by(team_id=11).all()
        for supervisor in supervisores:
            supervisor.role = 'supervisor'
        for team_id in range(2, 11):
            for cuadrilla in User.query.filter_by(team_id=team_id).all():
                cuadrilla.role = 'cuadrilla'
        db.session.commit()
        flash('Roles de usuarios existentes actualizados correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error actualizando roles: {str(e)[:100]}', 'danger')
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/exportar_usuarios_excel', methods=['GET'])
@login_required
@admin_required
def exportar_usuarios_excel():
    try:
        usuarios = User.query.all()
        datos = []
        for usuario in usuarios:
            datos.append({
                'ID': usuario.id,
                'Nombre': usuario.nombre,
                'Usuario': usuario.username,
                'Rol': usuario.role,
                'Área': usuario.area or 'N/A',
                'Cuadrilla': usuario.team.nombre if usuario.team else 'N/A',
                'Telegram ID': usuario.telegram_id or 'No vinculado',
                'Fecha Creación': usuario.created_at.strftime('%Y-%m-%d %H:%M') if usuario.created_at else 'N/A',
                'Activo': 'Sí' if usuario.is_active else 'No'
            })
        df = pd.DataFrame(datos)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Usuarios')
        output.seek(0)
        return send_file(output, download_name=f'usuarios_samapa_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx', as_attachment=True)
    except Exception as e:
        logger.error(f"Error exportando usuarios: {e}")
        flash(f'Error al exportar usuarios: {str(e)[:100]}', 'danger')
        return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/api/usuarios_por_cuadrilla/<int:team_id>', methods=['GET'])
@login_required
@admin_required
def api_usuarios_por_cuadrilla(team_id):
    try:
        usuarios = User.query.filter_by(team_id=team_id, is_active=True).all()
        resultado = [{'id': u.id, 'nombre': u.nombre, 'username': u.username, 'telegram_id': u.telegram_id, 'role': u.role} for u in usuarios]
        return jsonify({"success": True, "team_id": team_id, "count": len(resultado), "usuarios": resultado}), 200
    except Exception as e:
        logger.error(f"Error obteniendo usuarios: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/vincular_telegram', methods=['GET', 'POST'])
@login_required
@admin_required
def vincular_telegram():
    if request.method == 'POST':
        try:
            user_id = request.form.get('user_id')
            telegram_id = request.form.get('telegram_id')
            if not user_id or not telegram_id:
                flash("Debe seleccionar un usuario y proporcionar un Telegram ID.", "warning")
                return redirect(url_for('admin.vincular_telegram'))
            usuario = User.query.get_or_404(int(user_id))
            existente = User.query.filter_by(telegram_id=telegram_id).first()
            if existente and existente.id != usuario.id:
                flash(f"Este Telegram ID ya está en uso por {existente.nombre}.", "error")
                return redirect(url_for('admin.vincular_telegram'))
            usuario.telegram_id = telegram_id
            db.session.commit()
            flash(f'Usuario {usuario.nombre} vinculado con Telegram ID {telegram_id}.', 'success')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error vinculando Telegram: {e}")
            flash(f'Error al vincular Telegram: {str(e)[:100]}', 'danger')
    
    usuarios_sin_telegram = User.query.filter((User.telegram_id.is_(None)) | (User.telegram_id == '')).filter_by(is_active=True).all()
    usuarios_con_telegram = User.query.filter(User.telegram_id.isnot(None), User.telegram_id != '').filter_by(is_active=True).all()
    return render_template('admin/vincular_telegram.html',
                         usuarios_sin_telegram=usuarios_sin_telegram,
                         usuarios_con_telegram=usuarios_con_telegram)

@admin_bp.route('/evidencia/<path:filename>')
def evidencia_publica(filename):
    current_app.logger.info(f"📎 Acceso público a evidencia: {filename}")
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        current_app.logger.warning(f"Archivo no encontrado: {filename}")
        abort(404)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# ============================================================================
# RUTAS PARA REENVÍO DE VALIDACIÓN DEL SUPERVISOR
# ============================================================================
@admin_bp.route('/reporte/<int:reporte_id>/reenviar_validacion', methods=['POST'])
@login_required
@admin_required
def reenviar_validacion(reporte_id):
    try:
        from app.services.notification_service import notificar_supervisor_revision
        logger.info(f"📤 [ADMIN] Reenviando reporte #{reporte_id} a validación")
        reporte = Report.query.get_or_404(reporte_id)
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        if not asignacion or not asignacion.team_id:
            flash('❌ El reporte no está asignado a ninguna cuadrilla', 'error')
            return redirect(request.referrer or url_for('admin.dashboard'))
        if not asignacion.evidencia_cuadrilla:
            flash('⚠️ La cuadrilla no ha subido evidencia de reparación', 'warning')
            return redirect(request.referrer or url_for('admin.dashboard'))
        
        estado_revision = Status.query.filter_by(descripcion="En revisión").first()
        if not estado_revision:
            estado_revision = Status(descripcion="En revisión")
            db.session.add(estado_revision)
            db.session.commit()
        if asignacion.status_id != estado_revision.id:
            asignacion.status_id = estado_revision.id
            asignacion.observaciones = f"Reenviado a validación desde admin el {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()
        
        async def enviar():
            return await notificar_supervisor_revision(reporte_id, asignacion.team_id)
        
        success = asyncio.run(enviar())
        cuadrilla = Team.query.get(asignacion.team_id)
        cuadrilla_nombre = cuadrilla.nombre if cuadrilla else "Cuadrilla desconocida"
        if success:
            flash(f'✅ Reporte #{reporte_id} reenviado a validación del supervisor (Cuadrilla: {cuadrilla_nombre})', 'success')
        else:
            flash(f'⚠️ Error al reenviar a validación', 'warning')
        logger.info(f"📤 [ADMIN] Reporte #{reporte_id} reenviado a validación")
    except Exception as e:
        flash(f'❌ Error al reenviar: {str(e)[:100]}', 'error')
        logger.error(f"❌ [ADMIN] Error reenviando validación: {e}")
    return redirect(request.referrer or url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/validar_manual', methods=['POST'])
@login_required
@admin_required
def validar_manual(reporte_id):
    try:
        logger.info(f"✅ [ADMIN] Validando manualmente reporte #{reporte_id}")
        reporte = Report.query.get_or_404(reporte_id)
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        if asignacion:
            estado_finalizado = Status.query.filter_by(descripcion="Finalizado").first()
            if not estado_finalizado:
                estado_finalizado = Status(descripcion="Finalizado")
                db.session.add(estado_finalizado)
                db.session.commit()
            asignacion.status_id = estado_finalizado.id
            asignacion.observaciones = f"Validado manualmente desde admin el {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()
            cuadrilla = Team.query.get(asignacion.team_id)
            cuadrilla_nombre = cuadrilla.nombre if cuadrilla else "Cuadrilla desconocida"
            flash(f'✅ Reporte #{reporte_id} validado manualmente (Cuadrilla: {cuadrilla_nombre})', 'success')
            logger.info(f"✅ [ADMIN] Reporte #{reporte_id} validado manualmente")
        else:
            flash('❌ No hay asignación para este reporte', 'error')
    except Exception as e:
        flash(f'❌ Error al validar manualmente: {str(e)[:100]}', 'error')
        logger.error(f"❌ [ADMIN] Error validando manualmente: {e}")
    return redirect(request.referrer or url_for('admin.dashboard'))

# ============================================================================
# RUTA PARA VER DETALLE DEL REPORTE
# ============================================================================
@admin_bp.route('/reporte/<int:reporte_id>')
@login_required
@admin_required
def report_detail(reporte_id):
    try:
        reporte = Report.query.get_or_404(reporte_id)
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        cuadrilla = None
        estado = None
        if asignacion:
            cuadrilla = Team.query.get(asignacion.team_id) if asignacion.team_id else None
            estado = Status.query.get(asignacion.status_id) if asignacion.status_id else None
        historial = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).all()
        return render_template('admin/report_detail.html',
                             reporte=reporte,
                             asignacion=asignacion,
                             cuadrilla=cuadrilla,
                             estado=estado,
                             historial=historial)
    except Exception as e:
        flash(f'❌ Error al cargar el reporte: {str(e)[:100]}', 'error')
        logger.error(f"Error cargando reporte #{reporte_id}: {e}")
        return redirect(url_for('admin.dashboard'))

# ============================================================================
# RUTAS PARA PRUEBAS DE NOTIFICACIONES (CORREGIDAS CON asyncio.run)
# ============================================================================

@admin_bp.route('/reporte/<int:reporte_id>/test_notificaciones', methods=['POST'])
@login_required
@admin_required
def test_notificaciones_reporte(reporte_id):
    try:
        logger.info(f"🔍 [TEST] Iniciando prueba de notificaciones para reporte #{reporte_id}")
        from app.services.notification_service import notificar_director_nuevo_reporte
        
        reporte = Report.query.get_or_404(reporte_id)
        tipo_reporte = reporte.tipo
        logger.info(f"📋 [TEST] Tipo de reporte: {tipo_reporte}, Subtipo: {reporte.subtipo}")
        
        resultados = []
        
        if tipo_reporte in ["Agua potable", "Drenaje"]:
            # ========== JEFE TÉCNICO ==========
            jefe_tecnico = User.query.filter_by(
                area='agua', 
                rol_especifico='jefe_area_tecnica', 
                is_active=True
            ).first()
            
            if jefe_tecnico and jefe_tecnico.telegram_id:
                try:
                    telegram_id = int(jefe_tecnico.telegram_id)
                    logger.info(f"👷 [TEST] Enviando a Jefe Técnico: {jefe_tecnico.nombre}")
                    async def enviar_jefe():
                        return await notificar_director_nuevo_reporte(reporte_id, telegram_id, tipo_reporte)
                    success = asyncio.run(enviar_jefe())
                    resultados.append(f"✅ Jefe Técnico ({jefe_tecnico.nombre}): {'ENVIADO' if success else 'ERROR'}")
                except Exception as e:
                    resultados.append(f"❌ Jefe Técnico: {str(e)[:50]}")
            else:
                resultados.append(f"⚠️ Jefe Técnico: {'No encontrado' if not jefe_tecnico else 'Sin Telegram ID'}")
            
            # ========== DIRECTOR AGUA (CORREGIDO) ==========
            director_agua = User.query.filter_by(
                area='agua', 
                rol_especifico='director', 
                is_active=True
            ).first()
            
            if director_agua and director_agua.telegram_id:
                try:
                    telegram_id = int(director_agua.telegram_id)
                    logger.info(f"👨‍💼 [TEST] Enviando a Director Agua: {director_agua.nombre}")
                    # Usamos la misma función notificar_director_nuevo_reporte
                    # (ya maneja el tipo de mensaje según el rol)
                    async def enviar_director():
                        return await notificar_director_nuevo_reporte(reporte_id, telegram_id, tipo_reporte)
                    success = asyncio.run(enviar_director())
                    resultados.append(f"✅ Director Agua ({director_agua.nombre}): {'ENVIADO' if success else 'ERROR'}")
                except Exception as e:
                    resultados.append(f"❌ Director Agua: {str(e)[:50]}")
            else:
                resultados.append(f"⚠️ Director Agua: {'No encontrado' if not director_agua else 'Sin Telegram ID'}")
        
        # ========== OTROS DEPARTAMENTOS ==========
        else:
            logger.info(f"🏗️ [TEST] Reporte de {tipo_reporte} - Buscando responsable...")
            
            CONFIG_DEPARTAMENTOS = {
                "Aseo público": ("jefe_area", "aseo"),
                "Alumbrado público": ("jefe_area", "alumbrado"),
                "Parques y jardines": ("jefe_area", "parques"),
                "Ecología": ("jefe_area", "ecologia"),
                "Seguridad pública": ("jefe_area", "seguridad"),
                "Obras públicas": ("jefe_area", "obras"),
                "Bomberos": ("jefe_area", "bomberos"),
            }
            
            config = CONFIG_DEPARTAMENTOS.get(tipo_reporte)
            
            if config:
                rol_principal, area = config
                # Buscar rol principal
                responsable = User.query.filter_by(
                    area=area,
                    rol_especifico=rol_principal,
                    is_active=True
                ).first()
                
                # Fallback a director
                if not responsable:
                    responsable = User.query.filter_by(
                        area=area,
                        rol_especifico='director',
                        is_active=True
                    ).first()
                
                if responsable and responsable.telegram_id:
                    try:
                        telegram_id = int(responsable.telegram_id)
                        logger.info(f"👷 [TEST] Enviando a {rol_principal} de {area}: {responsable.nombre}")
                        async def enviar():
                            return await notificar_director_nuevo_reporte(reporte_id, telegram_id, tipo_reporte)
                        success = asyncio.run(enviar())
                        resultados.append(f"✅ {rol_principal} {area.title()} ({responsable.nombre}): {'ENVIADO' if success else 'ERROR'}")
                    except Exception as e:
                        resultados.append(f"❌ {rol_principal} {area.title()}: {str(e)[:50]}")
                else:
                    resultados.append(f"⚠️ {rol_principal} {area.title()}: {'No encontrado' if not responsable else 'Sin Telegram ID'}")
            else:
                resultados.append(f"⚠️ Departamento no configurado: {tipo_reporte}")
        
        # ========== MOSTRAR RESULTADOS ==========
        if resultados:
            mensaje_flash = "🔍 Resultados de prueba:<br>" + "<br>".join(resultados)
            flash(mensaje_flash, 'info')
        else:
            flash('⚠️ No se ejecutaron pruebas', 'warning')
        
        logger.info(f"✅ [TEST] Prueba completada para reporte #{reporte_id}")
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ [TEST] Error en prueba de notificaciones: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_inicial', methods=['POST'])
@login_required
@admin_required
def test_notificar_inicial(reporte_id):
    """Prueba: Notificación inicial - busca Jefe de Área o Director según departamento"""
    try:
        logger.info(f"🔔 [TEST] Notificación inicial para reporte #{reporte_id}")
        
        from app.services.notification_service import notificar_director_nuevo_reporte
        import asyncio
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Configuración por departamento: (rol_principal, area)
        CONFIG_DEPARTAMENTOS = {
            "Agua potable": ("jefe_area_tecnica", "agua"),
            "Drenaje": ("jefe_area_tecnica", "agua"),
            "Aseo público": ("jefe_area", "aseo"),
            "Alumbrado público": ("jefe_area", "alumbrado"),
            "Parques y jardines": ("jefe_area", "parques"),
            "Ecología": ("jefe_area", "ecologia"),
            "Seguridad pública": ("jefe_area", "seguridad"),
            "Obras públicas": ("jefe_area", "obras"),
            "Bomberos": ("jefe_area", "bomberos"),
        }
        
        config = CONFIG_DEPARTAMENTOS.get(reporte.tipo)
        
        if config:
            rol_principal, area = config
            # Buscar primero el rol principal (jefe_area, jefe_area_tecnica, etc.)
            responsable = User.query.filter_by(
                area=area,
                rol_especifico=rol_principal,
                is_active=True
            ).first()
            
            # Si no encuentra el rol principal, buscar director como fallback
            if not responsable:
                responsable = User.query.filter_by(
                    area=area,
                    rol_especifico='director',
                    is_active=True
                ).first()
        else:
            flash(f'❌ Departamento no configurado: {reporte.tipo}', 'error')
            return redirect(url_for('admin.dashboard'))
        
        if not responsable or not responsable.telegram_id:
            flash(f'❌ No se encontró responsable para {reporte.tipo} (área: {area})', 'error')
            return redirect(url_for('admin.dashboard'))
        
        # Enviar notificación
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(
            notificar_director_nuevo_reporte(
                reporte_id, 
                int(responsable.telegram_id), 
                reporte.tipo
            )
        )
        loop.close()
        
        if success:
            flash(f'✅ Notificación enviada a {responsable.nombre} ({rol_principal} de {area})', 'success')
        else:
            flash('❌ Error al enviar notificación', 'error')
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_notificar_inicial: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_asignar_cuadrilla', methods=['POST'])
@login_required
@admin_required
def test_asignar_cuadrilla(reporte_id):
    try:
        team_id = request.form.get('team_id')
        if not team_id:
            flash('❌ Debe seleccionar una cuadrilla', 'error')
            return redirect(url_for('admin.dashboard'))
        logger.info(f"👷 [TEST] Asignando reporte #{reporte_id} a cuadrilla {team_id}")
        usuario_cuadrilla = User.query.filter_by(team_id=team_id).first()
        if usuario_cuadrilla and usuario_cuadrilla.telegram_id:
            success = notificar_asignacion_sync(reporte_id, usuario_cuadrilla.id)
            cuadrilla = Team.query.get(team_id)
            flash(f'✅ Notificación enviada a {usuario_cuadrilla.nombre} ({cuadrilla.nombre})' if success else f'⚠️ Error al notificar a {usuario_cuadrilla.nombre}', 'warning')
        else:
            cuadrilla = Team.query.get(team_id)
            flash(f'⚠️ Cuadrilla {cuadrilla.nombre} no tiene usuarios con Telegram configurado', 'warning')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_asignar_cuadrilla: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_cuadrilla_termina', methods=['POST'])
@login_required
@admin_required
def test_cuadrilla_termina(reporte_id):
    try:
        logger.info(f"🔧 [TEST] Cuadrilla termina reporte #{reporte_id}")
        from app.services.notification_service import notificar_supervisor_revision
        reporte = Report.query.get_or_404(reporte_id)
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        if not asignacion or not asignacion.team_id:
            flash('❌ El reporte no está asignado a ninguna cuadrilla', 'error')
            return redirect(url_for('admin.dashboard'))
        if reporte.tipo == "Agua potable":
            supervisor = User.query.filter_by(area='agua', rol_especifico='supervisor').first()
            if supervisor and supervisor.telegram_id:
                async def enviar():
                    return await notificar_supervisor_revision(reporte_id, asignacion.team_id)
                success = asyncio.run(enviar())
                flash(f'✅ Notificación enviada al supervisor {supervisor.nombre}' if success else f'⚠️ Error al notificar al supervisor', 'warning')
            else:
                flash('⚠️ Supervisor no configurado o sin Telegram', 'warning')
        else:
            flash('ℹ️ Para áreas diferentes a agua, se notificaría al director', 'info')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_cuadrilla_termina: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_validar_usuario', methods=['POST'])
@login_required
@admin_required
def test_validacion_usuario(reporte_id):
    try:
        reporte = Report.query.get_or_404(reporte_id)
        flash(f'ℹ️ Prueba: Se enviaría validación al usuario {reporte.reportante} ({reporte.telefono})', 'info')
        flash('⚠️ Nota: Para probar realmente, el usuario debe tener Telegram vinculado', 'warning')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_validacion_usuario: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_problema_ubicacion', methods=['POST'])
@login_required
@admin_required
def test_problema_ubicacion(reporte_id):
    """Prueba REAL: Problema de ubicación (simula que la cuadrilla presiona el botón)"""
    try:
        logger.info(f"📍 [TEST] Problema ubicación para reporte #{reporte_id}")
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Obtener asignación para saber nombre de cuadrilla
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if not asignacion or not asignacion.team_id:
            flash('❌ El reporte no tiene cuadrilla asignada', 'error')
            return redirect(url_for('admin.dashboard'))
        
        cuadrilla = Team.query.get(asignacion.team_id)
        cuadrilla_nombre = cuadrilla.nombre if cuadrilla else "Cuadrilla desconocida"
        
        # ========== REPLICAR FLUJO REAL ==========
        import asyncio
        
        async def ejecutar_flujo():
            from app.telegram.handlers.ubicacion import solicitar_ubicacion_exacta_al_reportante
            from app.services.notification_service import notificar_director_nuevo_reporte
            
            # 1. Solicitar ubicación al reportante
            result1 = await solicitar_ubicacion_exacta_al_reportante(reporte_id, cuadrilla_nombre, context=None)
            
            # 2. Notificar al responsable (sin duplicar)
            # Solo notificar al principal; la función se encarga del resto
            if reporte.tipo in ["Agua potable", "Drenaje"]:
                responsable = User.query.filter_by(
                    area='agua',
                    rol_especifico='jefe_area_tecnica',
                    is_active=True
                ).first()
            else:
                mapeo = {
                    "Aseo público": "aseo",
                    "Alumbrado público": "alumbrado",
                    "Parques y jardines": "parques",
                    "Ecología": "ecologia",
                    "Seguridad pública": "seguridad",
                    "Obras públicas": "obras",
                    "Bomberos": "bomberos"
                }
                area = mapeo.get(reporte.tipo)
                responsable = User.query.filter_by(
                    area=area,
                    rol_especifico='director',
                    is_active=True
                ).first() if area else None
            
            if responsable and responsable.telegram_id:
                from app.services.notification_service import notificar_director_nuevo_reporte
                result2 = await notificar_director_nuevo_reporte(
                    reporte_id, 
                    int(responsable.telegram_id), 
                    reporte.tipo
                )
            else:
                result2 = False
            
            return result1 and result2
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(ejecutar_flujo())
        loop.close()
        
        if success:
            flash('✅ Proceso de ubicación ejecutado correctamente', 'success')
        else:
            flash('⚠️ Error en el proceso de ubicación', 'warning')
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_problema_ubicacion: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_presidente', methods=['POST'])
@login_required
@admin_required
def test_notificar_presidente(reporte_id):
    try:
        logger.info(f"🏛️ [TEST] Notificando presidente para reporte #{reporte_id}")
        from app.services.notification_service import notificar_presidente_reporte
        presidente = User.query.filter_by(rol_especifico='presidente').first()
        if presidente and presidente.telegram_id:
            async def enviar():
                return await notificar_presidente_reporte(reporte_id, "nuevo_reporte")
            success = asyncio.run(enviar())
            flash(f'✅ Notificación enviada al presidente' if success else f'⚠️ Error al notificar al presidente', 'warning')
        else:
            flash('⚠️ Presidente no tiene Telegram configurado', 'warning')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_notificar_presidente: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_enviar_validacion', methods=['POST'])
@login_required
@admin_required
def test_enviar_validacion(reporte_id):
    flash(f'ℹ️ Prueba: Se enviaría notificación de validación para reporte #{reporte_id}', 'info')
    flash('⚠️ Esta prueba usa la misma función que "Reenviar a validación"', 'warning')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_jefe_tecnico_agua', methods=['POST'])
@login_required
@admin_required
def test_jefe_tecnico_agua(reporte_id):
    try:
        logger.info(f"👷 [TEST ESPECÍFICO] Jefe Técnico Agua para reporte #{reporte_id}")
        from app.services.notification_service import notificar_director_nuevo_reporte
        reporte = Report.query.get_or_404(reporte_id)
        if reporte.tipo not in ["Agua potable", "Drenaje"]:
            flash('⚠️ Esta prueba solo es para reportes de AGUA/DRENAJE', 'warning')
            return redirect(url_for('admin.dashboard'))
        jefe_tecnico = User.query.filter_by(area='agua', rol_especifico='jefe_area_tecnica', is_active=True).first()
        if not jefe_tecnico or not jefe_tecnico.telegram_id:
            flash('❌ Jefe técnico no encontrado o sin Telegram ID', 'error')
            return redirect(url_for('admin.dashboard'))
        async def enviar():
            return await notificar_director_nuevo_reporte(reporte_id, int(jefe_tecnico.telegram_id), reporte.tipo)
        success = asyncio.run(enviar())
        flash(f'✅ Mensaje COMPLETO enviado al Jefe Técnico: {jefe_tecnico.nombre}' if success else '❌ Error al enviar mensaje', 'success' if success else 'error')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_jefe_tecnico_agua: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_director_agua', methods=['POST'])
@login_required
@admin_required
def test_director_agua(reporte_id):
    try:
        logger.info(f"👨‍💼 [TEST ESPECÍFICO] Director Agua para reporte #{reporte_id}")
        reporte = Report.query.get_or_404(reporte_id)
        if reporte.tipo not in ["Agua potable", "Drenaje"]:
            flash('⚠️ Esta prueba solo es para reportes de AGUA/DRENAJE', 'warning')
            return redirect(url_for('admin.dashboard'))
        director_agua = User.query.filter_by(area='agua', rol_especifico='director', is_active=True).first()
        if not director_agua or not director_agua.telegram_id:
            flash('❌ Director no encontrado o sin Telegram ID', 'error')
            return redirect(url_for('admin.dashboard'))
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode
        async def enviar():
            bot_app = get_telegram_app()
            if not bot_app or not bot_app.bot:
                return False
            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            mensaje = (
                f"💧 *INFORMACIÓN - NUEVO REPORTE {reporte.tipo.upper()}*\n\n"
                f"📋 *Folio:* #{reporte.id}\n"
                f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                f"👤 *Reportante:* {reporte.reportante}\n"
                f"📱 *Teléfono:* {reporte.telefono}\n"
                f"🔧 *Problema:* {reporte.subtipo}\n\n"
                f"📅 *Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
                f"*📋 Jefe Técnico ha sido notificado para asignación.*"
            )
            keyboard = [[InlineKeyboardButton("📋 Ver Detalles", callback_data=f"dir_detalle_{reporte.id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await bot_app.bot.send_message(
                chat_id=int(director_agua.telegram_id),
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            return True
        success = asyncio.run(enviar())
        flash(f'✅ Mensaje INFORMATIVO enviado al Director Agua: {director_agua.nombre}' if success else '❌ Error al enviar mensaje', 'success' if success else 'error')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_director_agua: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_supervisor_agua', methods=['POST'])
@login_required
@admin_required
def test_supervisor_agua(reporte_id):
    try:
        logger.info(f"👁️ [TEST ESPECÍFICO] Supervisor Agua para reporte #{reporte_id}")
        from app.services.notification_service import notificar_supervisor_revision
        reporte = Report.query.get_or_404(reporte_id)
        if reporte.tipo not in ["Agua potable", "Drenaje"]:
            flash('⚠️ Esta prueba solo es para reportes de AGUA/DRENAJE', 'warning')
            return redirect(url_for('admin.dashboard'))
        supervisor = User.query.filter_by(area='agua', rol_especifico='supervisor', is_active=True).first()
        if not supervisor or not supervisor.telegram_id:
            flash('❌ Supervisor no encontrado o sin Telegram ID', 'error')
            return redirect(url_for('admin.dashboard'))
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        if not asignacion or not asignacion.team_id:
            flash('⚠️ Reporte sin cuadrilla asignada', 'warning')
            return redirect(url_for('admin.dashboard'))
        async def enviar():
            return await notificar_supervisor_revision(reporte_id, asignacion.team_id)
        success = asyncio.run(enviar())
        flash(f'✅ Mensaje de VALIDACIÓN enviado al Supervisor Agua: {supervisor.nombre}' if success else '❌ Error al enviar mensaje', 'success' if success else 'error')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_supervisor_agua: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_director_area', methods=['POST'])
@login_required
@admin_required
def test_director_area(reporte_id):
    try:
        logger.info(f"🏗️ [TEST ESPECÍFICO] Director de área para reporte #{reporte_id}")
        from app.services.notification_service import notificar_director_nuevo_reporte
        reporte = Report.query.get_or_404(reporte_id)
        if reporte.tipo in ["Agua potable", "Drenaje"]:
            flash('⚠️ Para AGUA/DRENAJE use pruebas específicas', 'warning')
            return redirect(url_for('admin.dashboard'))
        mapeo_tipo_a_area = {
            "Aseo público": "aseo", "Alumbrado público": "alumbrado", "Parques y jardines": "parques",
            "Ecología": "ecologia", "Seguridad pública": "seguridad", "Obras públicas": "obra", "Bomberos": "bomberos"
        }
        area = mapeo_tipo_a_area.get(reporte.tipo)
        if not area:
            flash(f'❌ Área no configurada para: {reporte.tipo}', 'error')
            return redirect(url_for('admin.dashboard'))
        director = User.query.filter_by(area=area, rol_especifico='director', is_active=True).first()
        if not director or not director.telegram_id:
            flash(f'❌ Director de {area} no encontrado o sin Telegram ID', 'error')
            return redirect(url_for('admin.dashboard'))
        async def enviar():
            return await notificar_director_nuevo_reporte(reporte_id, int(director.telegram_id), reporte.tipo)
        success = asyncio.run(enviar())
        flash(f'✅ Mensaje COMPLETO enviado al Director de {area.title()}: {director.nombre}' if success else '❌ Error al enviar mensaje', 'success' if success else 'error')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_director_area: {e}")
        return redirect(url_for('admin.dashboard'))

# ============================================================================
# RUTAS PARA COORDENADAS
# ============================================================================
@admin_bp.route('/reporte/<int:reporte_id>/obtener_coordenadas', methods=['POST'])
@login_required
@admin_required
def obtener_coordenadas(reporte_id):
    try:
        reporte = Report.query.get_or_404(reporte_id)
        if reporte.localidad and reporte.localidad.latitud_central and reporte.localidad.longitud_central:
            reporte.latitud = reporte.localidad.latitud_central
            reporte.longitud = reporte.localidad.longitud_central
            db.session.commit()
            flash(f'✅ Coordenadas asignadas desde localidad: {reporte.latitud}, {reporte.longitud}', 'success')
        else:
            reporte.latitud = 19.432608
            reporte.longitud = -99.133209
            db.session.commit()
            flash('✅ Coordenadas por defecto asignadas', 'info')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al obtener coordenadas: {str(e)[:100]}', 'error')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/actualizar_coordenada', methods=['POST'])
@login_required
@admin_required
def actualizar_coordenada():
    try:
        reporte_id = request.form.get('reporte_id')
        field = request.form.get('field')
        valor = request.form.get('valor')
        if not all([reporte_id, field, valor]):
            return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
        reporte = Report.query.get_or_404(reporte_id)
        try:
            valor_float = float(valor)
            if field == 'latitud' and (-90 <= valor_float <= 90):
                reporte.latitud = valor_float
            elif field == 'longitud' and (-180 <= valor_float <= 180):
                reporte.longitud = valor_float
            else:
                return jsonify({'success': False, 'error': 'Valor fuera de rango'}), 400
        except ValueError:
            return jsonify({'success': False, 'error': 'Valor no numérico'}), 400
        db.session.commit()
        return jsonify({'success': True, 'message': 'Coordenada actualizada'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando coordenada: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/reporte/<int:reporte_id>/mapa')
@login_required
@admin_required
def ver_mapa_reporte(reporte_id):
    try:
        reporte = Report.query.get_or_404(reporte_id)
        if not reporte.latitud or not reporte.longitud:
            flash('❌ El reporte no tiene coordenadas.', 'warning')
            return redirect(url_for('admin.dashboard'))
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        cuadrilla = asignacion.team.nombre if asignacion and asignacion.team else "Sin asignar"
        estado = asignacion.status.descripcion if asignacion and asignacion.status else "Sin estado"
        return render_template('admin/mapa_reporte.html', reporte=reporte, cuadrilla=cuadrilla, estado=estado,
                               latitud=float(reporte.latitud), longitud=float(reporte.longitud))
    except Exception as e:
        flash(f'❌ Error al mostrar mapa: {str(e)[:100]}', 'error')
        logger.error(f"Error mostrando mapa: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reportes/<int:reporte_id>/actualizar_ubicacion', methods=['POST'])
@login_required
def actualizar_ubicacion(reporte_id):
    try:
        nueva_latitud = request.form.get('latitud', type=float)
        nueva_longitud = request.form.get('longitud', type=float)
        if nueva_latitud is None or nueva_longitud is None:
            return jsonify({'success': False, 'message': 'Debe proporcionar latitud y longitud'}), 400
        reporte = Report.query.get_or_404(reporte_id)
        lat_anterior = reporte.latitud
        lng_anterior = reporte.longitud
        reporte.latitud = nueva_latitud
        reporte.longitud = nueva_longitud
        db.session.commit()
        logger.info(f"📍 Coordenadas actualizadas para reporte #{reporte_id}: {lat_anterior},{lng_anterior} → {nueva_latitud},{nueva_longitud}")
        return jsonify({'success': True, 'message': 'Ubicación actualizada correctamente', 'nueva_latitud': nueva_latitud, 'nueva_longitud': nueva_longitud})
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Error actualizando ubicación: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
# ============================================================
# DASHBOARD DE ENCUESTAS DE SATISFACCIÓN
# ============================================================
@admin_bp.route('/encuestas')
@login_required
@admin_required
def encuestas_dashboard():
    """Dashboard de encuestas de satisfacción"""
    from app.models.feedback import EncuestaSatisfaccion
    from app.models.report import Report
    
    # Filtros
    dias = request.args.get('dias', 30, type=int)
    tipo = request.args.get('tipo', '')
    fecha_limite = datetime.utcnow() - timedelta(days=dias)
    
    # Query base
    query = db.session.query(EncuestaSatisfaccion).join(
        Report, EncuestaSatisfaccion.reporte_id == Report.id
    ).filter(EncuestaSatisfaccion.fecha >= fecha_limite)
    
    if tipo:
        query = query.filter(Report.tipo == tipo)
    
    encuestas = query.order_by(EncuestaSatisfaccion.fecha.desc()).all()
    
    # Métricas generales
    total_encuestas = len(encuestas)
    promedio_calificacion = round(sum(e.calificacion for e in encuestas) / total_encuestas, 1) if total_encuestas > 0 else 0
    promedio_velocidad = round(sum(e.velocidad for e in encuestas) / total_encuestas, 1) if total_encuestas > 0 else 0
    
    # Por departamento
    por_depto_query = db.session.query(
        Report.tipo,
        func.count(EncuestaSatisfaccion.id).label('total'),
        func.round(func.avg(EncuestaSatisfaccion.calificacion), 1).label('promedio_calif'),
        func.round(func.avg(EncuestaSatisfaccion.velocidad), 1).label('promedio_vel')
    ).join(Report, EncuestaSatisfaccion.reporte_id == Report.id).filter(
        EncuestaSatisfaccion.fecha >= fecha_limite
    )
    
    if tipo:
        por_depto_query = por_depto_query.filter(Report.tipo == tipo)
    
    por_depto = por_depto_query.group_by(Report.tipo).order_by(func.avg(EncuestaSatisfaccion.calificacion).desc()).all()
    
    # Mejor y peor departamento
    mejor_depto = por_depto[0] if por_depto else None
    peor_depto = por_depto[-1] if por_depto else None
    
    # Distribución de calificaciones (1-5)
    distribucion = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for e in encuestas:
        if e.calificacion in distribucion:
            distribucion[e.calificacion] += 1
    
    # Tipos para filtro
    tipos_disponibles = db.session.query(Report.tipo).distinct().filter(Report.tipo.isnot(None)).all()
    tipos_disponibles = [t[0] for t in tipos_disponibles if t[0]]
    
    return render_template(
        'admin/encuestas.html',
        total_encuestas=total_encuestas,
        promedio_calificacion=promedio_calificacion,
        promedio_velocidad=promedio_velocidad,
        mejor_depto=mejor_depto,
        peor_depto=peor_depto,
        por_depto=por_depto,
        distribucion=distribucion,
        encuestas=encuestas,
        dias=dias,
        tipo_seleccionado=tipo,
        tipos_disponibles=tipos_disponibles
    )
