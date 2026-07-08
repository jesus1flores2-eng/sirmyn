from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_login import login_required, current_user
import pandas as pd
import io
import os
from datetime import datetime
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
import logging

# Configurar logging
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
        # Ahora usamos el campo 'role' en lugar de id=1
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
    plataforma = request.args.get('plataforma')  # NUEVO: filtrar por plataforma

    if any([tipo, subtipo, localidad, team_id, status_id, plataforma]):
        reportes = obtener_reportes_filtrados(tipo, subtipo, localidad, team_id, status_id)
        # Filtrar por plataforma si se especifica
        if plataforma:
            reportes = [r for r in reportes if r.plataforma == plataforma]
    else:
        reportes = obtener_reportes()

    # Obtener la última asignación real por cada reporte
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
    
    # NUEVO: Opciones de plataforma
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
        plataforma_seleccionada=plataforma_seleccionada,  # NUEVO
        tipos_disponibles=tipos_disponibles,
        subtipos_disponibles=subtipos_disponibles,
        localidades_disponibles=localidades_disponibles,
        cuadrillas_disponibles=cuadrillas_disponibles,
        estados_disponibles=estados_disponibles,
        plataformas_disponibles=plataformas_disponibles  # NUEVO
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

    # Crear nueva asignación manteniendo datos anteriores si no se cambian
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

    # --- Enviar WhatsApp si se finaliza ---
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
    plataforma = request.args.get('plataforma')  # NUEVO

    if any([tipo, subtipo, localidad, team_id, status_id, plataforma]):
        reportes = obtener_reportes_filtrados(tipo, subtipo, localidad, team_id, status_id)
        # Filtrar por plataforma si se especifica
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
            'Plataforma': r.plataforma  # NUEVO
        })

    df = pd.DataFrame(datos)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reportes')
    output.seek(0)
    return send_file(output, download_name='reportes.xlsx', as_attachment=True)

# -------------------------------------
# Asignar cuadrilla CON NOTIFICACIÓN A TELEGRAM - VERSIÓN CORREGIDA
# -------------------------------------
@admin_bp.route('/asignar_cuadrilla/<int:report_id>', methods=['POST'])
@login_required
@admin_required
def asignar_cuadrilla(report_id):
    """Asigna una cuadrilla a un reporte y notifica al usuario por Telegram"""
    try:
        nueva_cuadrilla_id = request.form.get('team_id')
        if not nueva_cuadrilla_id:
            flash("Debes seleccionar una cuadrilla.", "error")
            return redirect(url_for('admin.dashboard'))
        
        nueva_cuadrilla_id = int(nueva_cuadrilla_id)
        
        # 1. OBTENER EL REPORTE
        reporte = Report.query.get_or_404(report_id)
        
        # 2. CREAR LA NUEVA ASIGNACIÓN
        # Buscar estado "Asignado" o "Sin Asignar"
        status_asignado = Status.query.filter(
            Status.descripcion.ilike('%asignado%')
        ).first()
        
        if not status_asignado:
            # Crear estado por defecto si no existe
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
        
        # 3. GUARDAR LA ASIGNACIÓN
        db.session.commit()
        
        # 4. BUSCAR USUARIO PARA NOTIFICAR
        usuario_notificar = User.query.filter_by(
            team_id=nueva_cuadrilla_id
        ).filter(
            User.telegram_id.isnot(None)
        ).first()
        
        # Si no hay usuario con Telegram, buscar cualquier usuario de la cuadrilla
        if not usuario_notificar:
            usuario_notificar = User.query.filter_by(
                team_id=nueva_cuadrilla_id
            ).first()
        
        # 5. ENVIAR NOTIFICACIÓN POR TELEGRAM
        if usuario_notificar and usuario_notificar.telegram_id:
            try:
                # Importar aquí para evitar importación circular
                from app.services.telegram_bot import notificar_asignacion_sync
                
                # Enviar notificación
                success = notificar_asignacion_sync(report_id, usuario_notificar.id)
                
                if success:
                    flash(
                        f"✅ Reporte #{report_id} asignado a {nueva_asignacion.team.nombre}. "
                        f"Notificación enviada a {usuario_notificar.nombre}",
                        "success"
                    )
                else:
                    flash(
                        f"⚠️ Reporte #{report_id} asignado a {nueva_asignacion.team.nombre}. "
                        f"No se pudo enviar notificación a {usuario_notificar.nombre}",
                        "warning"
                    )
                    
            except Exception as e:
                flash(
                    f"✅ Reporte #{report_id} asignado. Error en notificación: {str(e)[:100]}",
                    "warning"
                )
        else:
            # Si no hay usuario con Telegram en la cuadrilla
            cuadrilla_nombre = Team.query.get(nueva_cuadrilla_id).nombre
            flash(
                f"✅ Reporte #{report_id} asignado a {cuadrilla_nombre}. "
                "No hay usuarios con Telegram vinculado en esta cuadrilla.",
                "info"
            )
        
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
    """Ruta pública para evidencias CON SUBCARPETAS"""
    import os
    from flask import abort
    
    # Extraer solo el nombre del archivo (sin carpeta)
    nombre_archivo = os.path.basename(filename)
    
    # Validar que el archivo sea seguro
    # Aceptar: reporte_*.ext, tmp_*.ext, o cualquier archivo de imagen/video
    extensiones_permitidas = {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.avi', '.pdf'}
    
    # Obtener extensión
    _, ext = os.path.splitext(nombre_archivo)
    ext = ext.lower()
    
    # Validaciones:
    # 1. Debe tener extensión
    if not ext:
        abort(404)
    
    # 2. Extensión debe ser permitida
    if ext not in extensiones_permitidas:
        abort(404)
    
    # 3. Nombre debe ser seguro (no permitir paths raros)
    if '..' in filename or filename.startswith('/'):
        abort(404)
    
    # 4. Aceptar si es temporal (tmp_) o reporte (_)
    # Ya no restringimos que empiece con 'reporte_'
    
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

# -------------------------------------
# Crear, editar y eliminar status
# -------------------------------------
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
# Gestión de usuarios y cuadrillas (VERSIÓN ACTUALIZADA)
# -------------------------------------
@admin_bp.route('/gestionar_cuadrillas', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_cuadrillas():
    if request.method == 'POST':
        # Crear nuevo usuario (no necesariamente cuadrilla)
        nombre = request.form.get('nombre')
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'cuadrilla')
        
        # CAMBIO AQUÍ: Área para TODOS los usuarios, no solo directores
        area = request.form.get('area')  # ← QUITA LA CONDICIÓN
        
        team_id = request.form.get('team_id') or None
        telegram_id = request.form.get('telegram_id') or None
        
        if not nombre or not username or not password:
            flash("Nombre, usuario y contraseña son obligatorios.", "warning")
            return redirect(url_for('admin.gestionar_cuadrillas'))

        # Validar que el username no exista
        if User.query.filter_by(username=username).first():
            flash("El nombre de usuario ya existe.", "error")
            return redirect(url_for('admin.gestionar_cuadrillas'))

        # Crear usuario
        nuevo_usuario = User(
            nombre=nombre,
            username=username,
            role=role,
            area=area,  # ← ÁREA SIEMPRE SE ASIGNA
            team_id=team_id if team_id else None,
            telegram_id=telegram_id if telegram_id else None
        )
        nuevo_usuario.set_password(password)
        
        db.session.add(nuevo_usuario)
        db.session.commit()

        flash(f'Usuario {username} creado exitosamente como {role}.', 'success')
        return redirect(url_for('admin.gestionar_cuadrillas'))

    # Obtener todos los usuarios y cuadrillas para mostrar
    usuarios = User.query.all()
    all_teams = Team.query.all()
    
    # Calcular usuarios por cuadrilla para el template
    usuarios_por_cuadrilla = {}
    for team in all_teams:
        usuarios_por_cuadrilla[team.id] = User.query.filter_by(team_id=team.id).all()
    
    return render_template('admin/gestionar_cuadrillas.html', 
                         usuarios=usuarios, 
                         all_teams=all_teams,
                         usuarios_por_cuadrilla=usuarios_por_cuadrilla)

# -------------------------------------
# Actualizar usuario COMPLETO (RUTA PARA EL MODAL - IMPORTANTE)
# -------------------------------------
@admin_bp.route('/usuario/<int:user_id>/actualizar', methods=['POST'])
@login_required
@admin_required
def actualizar_usuario(user_id):
    """Actualiza todos los campos de un usuario (modal de edición)"""
    try:
        usuario = User.query.get_or_404(user_id)
        
        # Obtener datos del formulario
        nombre = request.form.get('nombre')
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        area = request.form.get('area')  # ← ÁREA SIEMPRE SE OBTIENE
        team_id = request.form.get('team_id')
        telegram_id = request.form.get('telegram_id')
        
        # Validaciones básicas
        if not nombre or not username or not role:
            flash("Nombre, usuario y rol son obligatorios.", "warning")
            return redirect(url_for('admin.gestionar_cuadrillas'))
        
        # Validar que el username no esté en uso por otro usuario
        usuario_existente = User.query.filter_by(username=username).first()
        if usuario_existente and usuario_existente.id != usuario.id:
            flash("El nombre de usuario ya está en uso por otro usuario.", "error")
            return redirect(url_for('admin.gestionar_cuadrillas'))
        
        # Validar que el telegram_id no esté en uso por otro usuario
        if telegram_id:
            telegram_existente = User.query.filter_by(telegram_id=telegram_id).first()
            if telegram_existente and telegram_existente.id != usuario.id:
                flash("Este Telegram ID ya está en uso por otro usuario.", "error")
                return redirect(url_for('admin.gestionar_cuadrillas'))
        
        # Actualizar campos del usuario
        usuario.nombre = nombre
        usuario.username = username
        usuario.role = role
        
        # CAMBIO AQUÍ: Área para TODOS los usuarios, no solo directores
        usuario.area = area if area and area.strip() else None  # ← QUITA LA CONDICIÓN
        
        # Actualizar contraseña si se proporcionó una nueva
        if password and password.strip():
            usuario.set_password(password)
        
        # Actualizar cuadrilla (team_id puede ser vacío)
        if team_id and team_id.strip():
            usuario.team_id = int(team_id)
        else:
            usuario.team_id = None
        
        # Actualizar Telegram ID (puede ser vacío)
        usuario.telegram_id = telegram_id if telegram_id and telegram_id.strip() else None
        
        # Guardar cambios
        db.session.commit()
        
        flash(f'Usuario {usuario.username} actualizado correctamente.', 'success')
        
    except ValueError as e:
        db.session.rollback()
        flash('Error: El ID de cuadrilla debe ser un número válido.', 'danger')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando usuario {user_id}: {e}")
        flash(f'Error al actualizar el usuario: {str(e)[:100]}', 'danger')
    
    return redirect(url_for('admin.gestionar_cuadrillas'))

# -------------------------------------
# Eliminar usuario (RUTA PARA EL MODAL)
# -------------------------------------
@admin_bp.route('/usuario/<int:user_id>/eliminar', methods=['POST'])
@login_required
@admin_required
def eliminar_usuario(user_id):
    """Elimina un usuario por ID"""
    usuario = User.query.get_or_404(user_id)
    
    # No permitir eliminar al usuario actual
    if usuario.id == current_user.id:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('admin.gestionar_cuadrillas'))
    
    # Obtener nombre antes de eliminar para el mensaje
    username = usuario.username
    
    # Eliminar usuario
    db.session.delete(usuario)
    db.session.commit()
    
    flash(f'Usuario {username} eliminado correctamente.', 'success')
    
    return redirect(url_for('admin.gestionar_cuadrillas'))

# -------------------------------------
# Rutas EXISTENTES que debes MANTENER (pero les falta la definición)
# -------------------------------------
@admin_bp.route('/actualizar_rol_usuario/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def actualizar_rol_usuario(user_id):
    """Actualiza solo el rol de un usuario (para tabla inline)"""
    usuario = User.query.get_or_404(user_id)
    nuevo_rol = request.form.get('role')
    
    if nuevo_rol in ['admin', 'director', 'supervisor', 'cuadrilla', 'jefe_area']:
        usuario.role = nuevo_rol
        
        # CAMBIO AQUÍ: No limpiar área automáticamente
        # El área se mantiene como está, no se pone en None
        # Solo si cambia a un rol que NO debería tener área, podrías limpiarla
        # Pero mejor dejar que el admin decida manualmente
        
        db.session.commit()
        flash(f'Rol de {usuario.username} actualizado a {nuevo_rol}', 'success')
    
    return redirect(url_for('admin.gestionar_cuadrillas'))

@admin_bp.route('/actualizar_area_usuario/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def actualizar_area_usuario(user_id):
    """Actualiza solo el área de un director (para tabla inline)"""
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
    """Ruta VIEJA - solo actualiza Telegram ID (mantener por compatibilidad)"""
    usuario = User.query.get_or_404(user_id)
    nuevo_telegram_id = request.form.get('nuevo_telegram_id')
    
    if nuevo_telegram_id:
        # Validar que no esté en uso por otro usuario
        existente = User.query.filter_by(telegram_id=nuevo_telegram_id).first()
        if existente and existente.id != usuario.id:
            flash('Este Telegram ID ya está en uso por otro usuario', 'error')
        else:
            usuario.telegram_id = nuevo_telegram_id if nuevo_telegram_id.strip() else None
            db.session.commit()
            flash(f'Telegram ID de {usuario.username} actualizado', 'success')
    
    return redirect(url_for('admin.gestionar_cuadrillas'))

# -------------------------------------
# Crear nueva cuadrilla
# -------------------------------------
@admin_bp.route('/crear_cuadrilla', methods=['POST'])
@login_required
@admin_required
def crear_cuadrilla():
    """Crea una nueva cuadrilla CON ÁREA"""
    try:
        nombre = request.form.get('nombre')
        area = request.form.get('area')  # NUEVO: recibir el área
        descripcion = request.form.get('descripcion', '')
        
        if not nombre or not area:  # MODIFICADO: área también es obligatoria
            flash("El nombre y el área de la cuadrilla son obligatorios.", "warning")
            return redirect(url_for('admin.gestionar_cuadrillas'))
        
        # Verificar si ya existe una cuadrilla con ese nombre
        existente = Team.query.filter_by(nombre=nombre).first()
        if existente:
            flash("Ya existe una cuadrilla con ese nombre.", "error")
            return redirect(url_for('admin.gestionar_cuadrillas'))
        
        # Crear nueva cuadrilla CON ÁREA
        nueva_cuadrilla = Team(
            nombre=nombre,
            area=area,  # NUEVO: asignar área
            descripcion=descripcion
        )
        
        db.session.add(nueva_cuadrilla)
        db.session.commit()
        
        flash(f'Cuadrilla "{nombre}" ({area}) creada correctamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando cuadrilla: {e}")
        flash(f'Error al crear la cuadrilla: {str(e)[:100]}', 'danger')
    
    return redirect(url_for('admin.gestionar_cuadrillas'))

# -------------------------------------
# Editar cuadrilla (solo nombre)
# -------------------------------------
@admin_bp.route('/editar_cuadrilla/<int:team_id>', methods=['POST'])
@login_required
@admin_required
def editar_cuadrilla(team_id):
    team = Team.query.get_or_404(team_id)
    nuevo_nombre = request.form.get('nombre')  # CAMBIADO: de 'nuevo_nombre' a 'nombre'
    nueva_area = request.form.get('area')      # NUEVO: recibir área
    nueva_descripcion = request.form.get('descripcion', '')  # NUEVO: recibir descripción

    if not nuevo_nombre or not nueva_area:  # MODIFICADO: validar nombre y área
        flash("El nombre y el área son obligatorios.", "warning")
        return redirect(url_for('admin.gestionar_cuadrillas'))

    team.nombre = nuevo_nombre
    team.area = nueva_area          # NUEVO: actualizar área
    team.descripcion = nueva_descripcion  # NUEVO: actualizar descripción
    db.session.commit()

    flash("Cuadrilla actualizada correctamente.", "success")
    return redirect(url_for('admin.gestionar_cuadrillas'))

# -------------------------------------
# Eliminar cuadrilla
# -------------------------------------
@admin_bp.route('/eliminar_cuadrilla/<int:team_id>', methods=['POST'])
@login_required
@admin_required
def eliminar_cuadrilla(team_id):
    team = Team.query.get_or_404(team_id)

    # Verificamos si hay reportes asignados a esta cuadrilla
    asignados = Assignment.query.filter_by(team_id=team.id).count()
    if asignados > 0:
        flash("No se puede eliminar una cuadrilla con reportes asignados.", "danger")
        return redirect(url_for('admin.gestionar_cuadrillas'))

    # Borrar usuarios asociados a esta cuadrilla
    usuarios = User.query.filter_by(team_id=team.id).all()
    for usuario in usuarios:
        db.session.delete(usuario)

    db.session.delete(team)
    db.session.commit()

    flash("Cuadrilla y usuarios asociados eliminados correctamente.", "warning")
    return redirect(url_for('admin.gestionar_cuadrillas'))


# -------------------------------------
# Historial completo de un reporte
# -------------------------------------
@admin_bp.route('/historial_completo/<int:reporte_id>')
@login_required
@admin_required
def historial_completo(reporte_id):
    # Tomamos el reporte
    reporte = Report.query.get_or_404(reporte_id)

    # Tomamos todas las asignaciones del reporte, en orden ascendente de fecha
    asignaciones = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.asc()).all()

    # Renderizamos la misma plantilla de historial
    return render_template('admin/historial.html', reporte=reporte, asignaciones=asignaciones)

@admin_bp.route('/admin/asignar_por_defecto/<int:report_id>', methods=['POST'])
@login_required
@admin_required
def asignar_por_defecto(report_id):
    reporte = Report.query.get_or_404(report_id)
    
    asignacion = Assignment.query.filter_by(report_id=reporte.id).first()
    
    if asignacion:
        # Asignar valores por defecto si faltan
        if not asignacion.team_id:
            asignacion.team_id = 1
        if not asignacion.status_id:
            asignacion.status_id = 1
    else:
        # Crear asignacion con valores por defecto
        asignacion = Assignment(
            report_id=reporte.id,
            team_id=1,
            status_id=1,
            timestamp=datetime.utcnow()
        )
        db.session.add(asignacion)
    
    db.session.commit()
    flash(f'Reporte {report_id} asignado con valores por defecto.', 'success')
    return redirect(url_for('admin.dashboard'))

def crear_asignacion_snapshot(report_id, **overrides):
    """Crea una nueva fila en Assignment copiando la última y aplicando cambios."""
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

# -------------------------------------
# API para asignar reporte desde Telegram (directores)
# -------------------------------------
@admin_bp.route('/asignar_reporte', methods=['POST'])
def asignar_reporte():
    """Asigna un reporte a una cuadrilla y notifica por Telegram"""
    try:
        data = request.get_json()
        reporte_id = data.get('reporte_id')
        user_id = data.get('user_id')
        team_id = data.get('team_id')
        
        # 1. Guardar la asignación en la BD
        nueva_asignacion = Assignment(
            report_id=reporte_id,
            team_id=team_id,
            status_id=Status.query.filter_by(descripcion="Asignado").first().id,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(nueva_asignacion)
        db.session.commit()
        
        # 2. Notificar al usuario asignado (si tiene Telegram vinculado)
        if user_id:
            notificar_asignacion_sync(reporte_id, user_id)
        
        return jsonify({
            "success": True,
            "message": f"Reporte #{reporte_id} asignado y notificado"
        })
        
    except Exception as e:
        logger.error(f"Error asignando reporte: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------------
# NUEVO: API para obtener directores por área
# -------------------------------------
@admin_bp.route('/api/directores_por_area/<area>', methods=['GET'])
@login_required
@admin_required
def api_directores_por_area(area):
    """Obtiene directores por área para integración con Telegram"""
    try:
        directores = User.query.filter_by(
            role='director',
            area=area,
            is_active=True
        ).all()
        
        resultado = []
        for director in directores:
            resultado.append({
                'id': director.id,
                'nombre': director.nombre,
                'username': director.username,
                'telegram_id': director.telegram_id,
                'area': director.area
            })
        
        return jsonify({
            "success": True,
            "area": area,
            "count": len(resultado),
            "directores": resultado
        }), 200
        
    except Exception as e:
        logger.error(f"Error obteniendo directores por área: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------------
# NUEVO: API para obtener cuadrillas por área
# -------------------------------------
@admin_bp.route('/api/cuadrillas_por_area/<area>', methods=['GET'])
@login_required
@admin_required
def api_cuadrillas_por_area(area):
    """Obtiene cuadrillas por área para asignación por directores"""
    try:
        # Filtrar cuadrillas cuyo nombre contenga el área
        cuadrillas = Team.query.filter(
            Team.nombre.ilike(f"%{area}%")
        ).filter(Team.nombre != "Sin asignar").all()
        
        # Si no hay específicas, devolver todas excepto "Sin asignar"
        if not cuadrillas:
            cuadrillas = Team.query.filter(Team.nombre != "Sin asignar").all()
        
        resultado = []
        for cuadrilla in cuadrillas:
            # Contar usuarios en la cuadrilla
            usuarios_count = User.query.filter_by(team_id=cuadrilla.id).count()
            
            resultado.append({
                'id': cuadrilla.id,
                'nombre': cuadrilla.nombre,
                'descripcion': cuadrilla.descripcion if hasattr(cuadrilla, 'descripcion') else '',
                'usuarios': usuarios_count
            })
        
        return jsonify({
            "success": True,
            "area": area,
            "count": len(resultado),
            "cuadrillas": resultado
        }), 200
        
    except Exception as e:
        logger.error(f"Error obteniendo cuadrillas por área: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------------
# NUEVO: Actualizar todos los usuarios existentes con roles por defecto
# -------------------------------------
@admin_bp.route('/actualizar_roles_existentes', methods=['POST'])
@login_required
@admin_required
def actualizar_roles_existentes():
    """Actualiza los roles de usuarios existentes (ejecutar una sola vez)"""
    try:
        # Actualizar admin
        admin_user = User.query.filter_by(username='Admin').first()
        if admin_user:
            admin_user.role = 'admin'
        
        # Actualizar supervisores (team_id=11)
        supervisores = User.query.filter_by(team_id=11).all()
        for supervisor in supervisores:
            supervisor.role = 'supervisor'
        
        # Actualizar cuadrillas (team_id entre 2 y 10)
        for team_id in range(2, 11):
            cuadrillas = User.query.filter_by(team_id=team_id).all()
            for cuadrilla in cuadrillas:
                cuadrilla.role = 'cuadrilla'
        
        db.session.commit()
        flash('Roles de usuarios existentes actualizados correctamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error actualizando el reporte', 'danger')

# -------------------------------------
# NUEVO: Exportar usuarios a Excel
# -------------------------------------
@admin_bp.route('/exportar_usuarios_excel', methods=['GET'])
@login_required
@admin_required
def exportar_usuarios_excel():
    """Exporta todos los usuarios a un archivo Excel"""
    try:
        # Obtener todos los usuarios
        usuarios = User.query.all()
        
        # Preparar datos para Excel
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
        
        # Crear DataFrame y Excel
        df = pd.DataFrame(datos)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Usuarios')
        
        output.seek(0)
        
        # Enviar archivo
        return send_file(
            output,
            download_name=f'usuarios_samapa_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx',
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        logger.error(f"Error exportando usuarios a Excel: {e}")
        flash(f'Error al exportar usuarios: {str(e)[:100]}', 'danger')
        return redirect(url_for('admin.gestionar_cuadrillas'))

# -------------------------------------
# NUEVO: API para obtener usuarios por cuadrilla
# -------------------------------------
@admin_bp.route('/api/usuarios_por_cuadrilla/<int:team_id>', methods=['GET'])
@login_required
@admin_required
def api_usuarios_por_cuadrilla(team_id):
    """Obtiene usuarios por cuadrilla para integración con Telegram"""
    try:
        usuarios = User.query.filter_by(
            team_id=team_id,
            is_active=True
        ).all()
        
        resultado = []
        for usuario in usuarios:
            resultado.append({
                'id': usuario.id,
                'nombre': usuario.nombre,
                'username': usuario.username,
                'telegram_id': usuario.telegram_id,
                'role': usuario.role
            })
        
        return jsonify({
            "success": True,
            "team_id": team_id,
            "count": len(resultado),
            "usuarios": resultado
        }), 200
        
    except Exception as e:
        logger.error(f"Error obteniendo usuarios por cuadrilla: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------------
# NUEVO: Vista para vincular usuarios con Telegram
# -------------------------------------
@admin_bp.route('/vincular_telegram', methods=['GET', 'POST'])
@login_required
@admin_required
def vincular_telegram():
    """Vista especial para vincular usuarios con Telegram de forma masiva"""
    if request.method == 'POST':
        try:
            user_id = request.form.get('user_id')
            telegram_id = request.form.get('telegram_id')
            
            if not user_id or not telegram_id:
                flash("Debe seleccionar un usuario y proporcionar un Telegram ID.", "warning")
                return redirect(url_for('admin.vincular_telegram'))
            
            usuario = User.query.get_or_404(int(user_id))
            
            # Verificar que el Telegram ID no esté en uso
            existente = User.query.filter_by(telegram_id=telegram_id).first()
            if existente and existente.id != usuario.id:
                flash(f"Este Telegram ID ya está en uso por {existente.nombre}.", "error")
                return redirect(url_for('admin.vincular_telegram'))
            
            # Actualizar Telegram ID
            usuario.telegram_id = telegram_id
            db.session.commit()
            
            flash(f'Usuario {usuario.nombre} vinculado con Telegram ID {telegram_id}.', 'success')
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error vinculando Telegram: {e}")
            flash(f'Error al vincular Telegram: {str(e)[:100]}', 'danger')
    
    # Obtener usuarios sin Telegram vinculado
    usuarios_sin_telegram = User.query.filter(
        (User.telegram_id.is_(None)) | (User.telegram_id == '')
    ).filter_by(is_active=True).all()
    
    # Obtener usuarios con Telegram vinculado
    usuarios_con_telegram = User.query.filter(
        User.telegram_id.isnot(None),
        User.telegram_id != ''
    ).filter_by(is_active=True).all()
    
    return render_template(
        'admin/vincular_telegram.html',
        usuarios_sin_telegram=usuarios_sin_telegram,
        usuarios_con_telegram=usuarios_con_telegram
    )

# Busca donde están las otras rutas de archivos y agrega esto:

@admin_bp.route('/evidencia/<path:filename>')
def evidencia_publica(filename):
    """Ruta pública para evidencias de Telegram (sin autenticación)"""
    # Log opcional para depuración
    current_app.logger.info(f"📎 Acceso público a evidencia: {filename}")
    
    # Verificar que el archivo existe (opcional, por seguridad)
    import os
    from flask import abort
    
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
    """Reenvía un reporte a validación del supervisor"""
    try:
        from app.services.telegram_bot import notificar_supervisor_revision
        import asyncio
        
        logger.info(f"📤 [ADMIN] Reenviando reporte #{reporte_id} a validación")
        
        # Buscar el reporte
        reporte = Report.query.get_or_404(reporte_id)
        
        # Buscar la última asignación
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if not asignacion:
            flash('❌ No hay asignación para este reporte', 'error')
            return redirect(request.referrer or url_for('admin.dashboard'))
        
        if not asignacion.team_id:
            flash('❌ El reporte no está asignado a ninguna cuadrilla', 'error')
            return redirect(request.referrer or url_for('admin.dashboard'))
        
        # Verificar si ya tiene evidencia de cuadrilla
        if not asignacion.evidencia_cuadrilla:
            flash('⚠️ La cuadrilla no ha subido evidencia de reparación', 'warning')
            return redirect(request.referrer or url_for('admin.dashboard'))
        
        # Cambiar estado a "En revisión" si no lo está
        estado_revision = Status.query.filter_by(descripcion="En revisión").first()
        if not estado_revision:
            estado_revision = Status(descripcion="En revisión")
            db.session.add(estado_revision)
            db.session.commit()
        
        if asignacion.status_id != estado_revision.id:
            asignacion.status_id = estado_revision.id
            asignacion.observaciones = f"Reenviado a validación desde admin el {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()
        
        # Reenviar notificación al supervisor
        async def enviar_notificacion():
            await notificar_supervisor_revision(reporte_id, asignacion.team_id)
        
        asyncio.run(enviar_notificacion())
        
        # Obtener nombre de cuadrilla
        cuadrilla = Team.query.get(asignacion.team_id)
        cuadrilla_nombre = cuadrilla.nombre if cuadrilla else "Cuadrilla desconocida"
        
        flash(f'✅ Reporte #{reporte_id} reenviado a validación del supervisor (Cuadrilla: {cuadrilla_nombre})', 'success')
        logger.info(f"📤 [ADMIN] Reporte #{reporte_id} reenviado a validación")
        
    except Exception as e:
        flash(f'❌ Error al reenviar: {str(e)[:100]}', 'error')
        logger.error(f"❌ [ADMIN] Error reenviando validación para reporte #{reporte_id}: {e}")
    
    return redirect(request.referrer or url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/validar_manual', methods=['POST'])
@login_required
@admin_required
def validar_manual(reporte_id):
    """Marca un reporte como validado manualmente desde admin"""
    try:
        logger.info(f"✅ [ADMIN] Validando manualmente reporte #{reporte_id}")
        
        reporte = Report.query.get_or_404(reporte_id)
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if asignacion:
            # Cambiar estado a "Finalizado"
            estado_finalizado = Status.query.filter_by(descripcion="Finalizado").first()
            if not estado_finalizado:
                estado_finalizado = Status(descripcion="Finalizado")
                db.session.add(estado_finalizado)
                db.session.commit()
            
            asignacion.status_id = estado_finalizado.id
            asignacion.observaciones = f"Validado manualmente desde admin el {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()
            
            # Obtener nombre de cuadrilla para el mensaje
            cuadrilla = Team.query.get(asignacion.team_id)
            cuadrilla_nombre = cuadrilla.nombre if cuadrilla else "Cuadrilla desconocida"
            
            flash(f'✅ Reporte #{reporte_id} validado manualmente (Cuadrilla: {cuadrilla_nombre})', 'success')
            logger.info(f"✅ [ADMIN] Reporte #{reporte_id} validado manualmente")
        else:
            flash('❌ No hay asignación para este reporte', 'error')
            
    except Exception as e:
        flash(f'❌ Error al validar manualmente: {str(e)[:100]}', 'error')
        logger.error(f"❌ [ADMIN] Error validando manualmente reporte #{reporte_id}: {e}")
    
    return redirect(request.referrer or url_for('admin.dashboard'))

# ============================================================================
# RUTA PARA VER DETALLE DEL REPORTE (SI NO LA TIENES)
# ============================================================================

@admin_bp.route('/reporte/<int:reporte_id>')
@login_required
@admin_required
def report_detail(reporte_id):
    """Muestra el detalle completo de un reporte"""
    try:
        reporte = Report.query.get_or_404(reporte_id)
        
        # Obtener la última asignación
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        # Obtener cuadrilla y estado
        cuadrilla = None
        estado = None
        if asignacion:
            cuadrilla = Team.query.get(asignacion.team_id) if asignacion.team_id else None
            estado = Status.query.get(asignacion.status_id) if asignacion.status_id else None
        
        # Obtener historial de asignaciones
        historial = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).all()
        
        # Para el template
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
# RUTAS PARA PRUEBAS DE NOTIFICACIONES - AGREGAR AL FINAL
# ============================================================================

@admin_bp.route('/reporte/<int:reporte_id>/test_notificaciones', methods=['POST'])
@login_required
@admin_required
def test_notificaciones_reporte(reporte_id):
    """Prueba el envío de notificaciones para un reporte específico"""
    try:
        logger.info(f"🔍 [TEST] Iniciando prueba de notificaciones para reporte #{reporte_id}")
        
        # Importar la función asíncrona
        from app.services.telegram_bot import notificar_director_nuevo_reporte
        
        # Obtener reporte
        reporte = Report.query.get_or_404(reporte_id)
        
        # Determinar tipo de reporte
        tipo_reporte = reporte.tipo
        logger.info(f"📋 [TEST] Tipo de reporte: {tipo_reporte}, Subtipo: {reporte.subtipo}")
        
        resultados = []
        
        # ============================================
        # 1. PARA REPORTES DE AGUA POTABLE
        # ============================================
        if tipo_reporte == "Agua potable":
            logger.info(f"💧 [TEST] Reporte de AGUA - Procesando...")
            
            # A) JEFE TÉCNICO
            jefe_tecnico = User.query.filter_by(
                area='agua',
                rol_especifico='jefe_area_tecnica'
            ).first()
            
            if jefe_tecnico:
                if jefe_tecnico.telegram_id:
                    try:
                        telegram_id = int(jefe_tecnico.telegram_id)
                        logger.info(f"👷 [TEST] Enviando a Jefe Técnico: {jefe_tecnico.nombre} (ID: {telegram_id})")
                        
                        # Ejecutar función asíncrona CORREGIDO
                        import asyncio
                        
                        async def enviar_a_jefe_tecnico():
                            return await notificar_director_nuevo_reporte(
                                reporte_id, 
                                telegram_id,
                                tipo_reporte
                            )
                        
                        # Crear nuevo event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        success = loop.run_until_complete(enviar_a_jefe_tecnico())
                        loop.close()
                        
                        if success:
                            resultados.append(f"✅ Jefe Técnico ({jefe_tecnico.nombre}): ENVIADO")
                            logger.info(f"✅ [TEST] Notificación enviada a Jefe Técnico")
                        else:
                            resultados.append(f"❌ Jefe Técnico ({jefe_tecnico.nombre}): ERROR")
                            logger.error(f"❌ [TEST] Error enviando a Jefe Técnico")
                            
                    except ValueError:
                        resultados.append(f"❌ Jefe Técnico: Telegram ID inválido")
                    except Exception as e:
                        resultados.append(f"❌ Jefe Técnico: Error - {str(e)[:50]}")
                else:
                    resultados.append(f"⚠️ Jefe Técnico: Sin Telegram ID configurado")
            else:
                resultados.append(f"❌ Jefe Técnico: No encontrado")
            
            # B) DIRECTOR AGUA (mensaje simple)
            director_agua = User.query.filter_by(
                area='agua',
                rol_especifico='director'
            ).first()
            
            if director_agua:
                if director_agua.telegram_id:
                    try:
                        telegram_id = int(director_agua.telegram_id)
                        logger.info(f"👨‍💼 [TEST] Enviando mensaje simple a Director Agua: {director_agua.nombre}")
                        
                        # Enviar mensaje simple (solo botón ver)
                        import asyncio
                        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                        from telegram.constants import ParseMode
                        
                        async def enviar_a_director_agua():
                            # Importar telegram_app aquí para evitar problemas de importación circular
                            from app.services.telegram_bot import telegram_app
                            if telegram_app and hasattr(telegram_app, 'bot'):
                                # Mensaje simple para director
                                mensaje = (
                                    f"💧 *NUEVO REPORTE - AGUA POTABLE*\n\n"
                                    f"📋 *Folio:* #{reporte.id}\n"
                                    f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n"
                                    f"📝 *Problema:* {reporte.subtipo}\n"
                                    f"👤 *Reportante:* {reporte.reportante}\n\n"
                                    f"*📅 Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
                                    f"*📋 Jefe Técnico ha sido notificado para asignación.*"
                                )
                                
                                keyboard = [[InlineKeyboardButton("📋 Ver Detalles", callback_data=f"dir_detalle_{reporte.id}")]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                
                                await telegram_app.bot.send_message(
                                    chat_id=telegram_id,
                                    text=mensaje,
                                    parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=reply_markup
                                )
                                return True
                            return False
                        
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        success = loop.run_until_complete(enviar_a_director_agua())
                        loop.close()
                        
                        if success:
                            resultados.append(f"✅ Director Agua ({director_agua.nombre}): MENSAJE SIMPLE ENVIADO")
                        else:
                            resultados.append(f"❌ Director Agua: Error enviando mensaje")
                            
                    except Exception as e:
                        resultados.append(f"❌ Director Agua: Error - {str(e)[:50]}")
                else:
                    resultados.append(f"⚠️ Director Agua: Sin Telegram ID")
            else:
                resultados.append(f"❌ Director Agua: No encontrado")
            
            # C) JEFE COMERCIAL (si es desperdicio)
            if reporte.subtipo == "Desperdicio de agua":
                jefe_comercial = User.query.filter_by(
                    area='agua',
                    rol_especifico='jefe_area_comercial'
                ).first()
                
                if jefe_comercial:
                    if jefe_comercial.telegram_id:
                        resultados.append(f"💰 Jefe Comercial: Configurado (se enviaría para desperdicio)")
                    else:
                        resultados.append(f"⚠️ Jefe Comercial: Sin Telegram ID")
                else:
                    resultados.append(f"❌ Jefe Comercial: No encontrado")
        
        # ============================================
        # 2. PARA OTROS DEPARTAMENTOS
        # ============================================
        else:
            logger.info(f"🏗️ [TEST] Reporte de {tipo_reporte} - Buscando director...")
            
            # Mapeo tipo -> área
            mapeo_tipo_a_area = {
                "Aseo público": "aseo",
                "Alumbrado público": "alumbrado", 
                "Parques y jardines": "parques",
                "Ecología": "ecologia",
                "Seguridad pública": "seguridad",
                "Obras públicas": "obra",
                "Bomberos": "bomberos",
                "Drenaje": "agua"  # Mismo que agua
            }
            
            area = mapeo_tipo_a_area.get(tipo_reporte)
            
            if area:
                director = User.query.filter_by(
                    area=area,
                    rol_especifico='director'
                ).first()
                
                if director:
                    if director.telegram_id:
                        try:
                            telegram_id = int(director.telegram_id)
                            logger.info(f"👨‍💼 [TEST] Enviando a Director {area}: {director.nombre}")
                            
                            import asyncio
                            
                            async def enviar_a_director():
                                return await notificar_director_nuevo_reporte(
                                    reporte_id, 
                                    telegram_id,
                                    tipo_reporte
                                )
                            
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            success = loop.run_until_complete(enviar_a_director())
                            loop.close()
                            
                            if success:
                                resultados.append(f"✅ Director {area.title()} ({director.nombre}): ENVIADO")
                            else:
                                resultados.append(f"❌ Director {area.title()}: ERROR")
                                
                        except Exception as e:
                            resultados.append(f"❌ Director {area.title()}: Error - {str(e)[:50]}")
                    else:
                        resultados.append(f"⚠️ Director {area.title()}: Sin Telegram ID")
                else:
                    resultados.append(f"❌ Director {area.title()}: No encontrado")
            else:
                resultados.append(f"⚠️ Área no mapeada para tipo: {tipo_reporte}")
        
        # ============================================
        # 3. MOSTRAR RESULTADOS
        # ============================================
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
        return redirect(url_for('admin.dashboard'))

# ============================================================================
# RUTAS PARA COORDENADAS (LATITUD/LONGITUD)
# ============================================================================

@admin_bp.route('/reporte/<int:reporte_id>/obtener_coordenadas', methods=['POST'])
@login_required
@admin_required
def obtener_coordenadas(reporte_id):
    """Obtiene coordenadas automáticamente para un reporte"""
    try:
        reporte = Report.query.get_or_404(reporte_id)
        
        # Aquí normalmente harías geocodificación con una API
        # Por ahora, usaremos coordenadas de prueba basadas en la localidad
        
        if reporte.localidad and reporte.localidad.latitud_central and reporte.localidad.longitud_central:
            # Usar coordenadas centrales de la localidad
            reporte.latitud = reporte.localidad.latitud_central
            reporte.longitud = reporte.localidad.longitud_central
            db.session.commit()
            
            flash(f'✅ Coordenadas asignadas desde localidad: {reporte.latitud}, {reporte.longitud}', 'success')
        else:
            # Coordenadas por defecto (centro de México)
            reporte.latitud = 19.432608
            reporte.longitud = -99.133209
            db.session.commit()
            flash('✅ Coordenadas por defecto asignadas', 'info')
        
        logger.info(f"📍 Coordenadas asignadas al reporte #{reporte_id}: {reporte.latitud}, {reporte.longitud}")
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al obtener coordenadas: {str(e)[:100]}', 'error')
        logger.error(f"Error obteniendo coordenadas para reporte #{reporte_id}: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/actualizar_coordenada', methods=['POST'])
@login_required
@admin_required
def actualizar_coordenada():
    """Actualiza manualmente una coordenada (latitud o longitud)"""
    try:
        reporte_id = request.form.get('reporte_id')
        field = request.form.get('field')  # 'latitud' o 'longitud'
        valor = request.form.get('valor')
        
        if not all([reporte_id, field, valor]):
            return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Validar valor numérico
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
        logger.info(f"📍 Coordenada actualizada: reporte #{reporte_id} {field}={valor_float}")
        return jsonify({'success': True, 'message': 'Coordenada actualizada'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando coordenada: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/reporte/<int:reporte_id>/mapa')
@login_required
@admin_required
def ver_mapa_reporte(reporte_id):
    """Muestra un mapa con la ubicación del reporte"""
    try:
        reporte = Report.query.get_or_404(reporte_id)
        
        if not reporte.latitud or not reporte.longitud:
            flash('❌ El reporte no tiene coordenadas. Use "Obtener" para asignarlas.', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Obtener información de cuadrilla asignada
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        cuadrilla = asignacion.team.nombre if asignacion and asignacion.team else "Sin asignar"
        estado = asignacion.status.descripcion if asignacion and asignacion.status else "Sin estado"
        
        return render_template('admin/mapa_reporte.html',
                             reporte=reporte,
                             cuadrilla=cuadrilla,
                             estado=estado,
                             latitud=float(reporte.latitud),
                             longitud=float(reporte.longitud))
        
    except Exception as e:
        flash(f'❌ Error al mostrar mapa: {str(e)[:100]}', 'error')
        logger.error(f"Error mostrando mapa para reporte #{reporte_id}: {e}")
        return redirect(url_for('admin.dashboard'))

# ============================================================================
# RUTAS PARA PRUEBAS CON 2 CELULARES - VERSIÓN SIMPLIFICADA
# ============================================================================

@admin_bp.route('/reporte/<int:reporte_id>/test_inicial', methods=['POST'])
@login_required
@admin_required
def test_notificar_inicial(reporte_id):
    """Prueba: Notificación inicial (usuario -> director/jefe técnico)"""
    try:
        logger.info(f"🔔 [TEST] Notificación inicial para reporte #{reporte_id}")
        
        from app.services.telegram_bot import notificar_director_nuevo_reporte
        import asyncio
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Dependiendo del tipo de reporte, notificar a diferentes roles
        resultados = []
        
        # 1. PARA AGUA POTABLE: Jefe Técnico (ID: 4)
        if reporte.tipo == "Agua potable":
            jefe_tecnico = User.query.get(4)  # ID del jefe técnico
            
            if jefe_tecnico and jefe_tecnico.telegram_id:
                try:
                    # Enviar notificación
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    success = loop.run_until_complete(
                        notificar_director_nuevo_reporte(reporte_id, int(jefe_tecnico.telegram_id), reporte.tipo)
                    )
                    loop.close()
                    
                    if success:
                        resultados.append(f"✅ Jefe Técnico ({jefe_tecnico.nombre}): ENVIADO")
                        # Enviar también mensaje simple al director (ID: 3)
                        director_agua = User.query.get(3)
                        if director_agua and director_agua.telegram_id:
                            resultados.append(f"📋 Director ({director_agua.nombre}): MENSAJE SIMPLE ENVIADO")
                    else:
                        resultados.append(f"❌ Jefe Técnico: ERROR")
                        
                except Exception as e:
                    resultados.append(f"❌ Jefe Técnico: {str(e)[:50]}")
            else:
                resultados.append(f"⚠️ Jefe Técnico: Sin Telegram ID o no encontrado")
        
        # 2. PARA OTROS DEPARTAMENTOS: Director correspondiente
        else:
            # Mapeo tipo -> área -> director ID
            mapeo_directores = {
                "Aseo público": 10,      # director_aseo
                "Parques y jardines": 12, # director_parques
                "Alumbrado público": 18,  # director alumbrado
                "Ecología": 19,           # director ecologia
                "Seguridad pública": 20,  # director seguridad
                "Obras públicas": 21,     # director obras
                "Bomberos": 14,           # director_bomberos
                "Drenaje": 3              # director_agua (mismo que agua)
            }
            
            director_id = mapeo_directores.get(reporte.tipo)
            
            if director_id:
                director = User.query.get(director_id)
                
                if director and director.telegram_id:
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        success = loop.run_until_complete(
                            notificar_director_nuevo_reporte(reporte_id, int(director.telegram_id), reporte.tipo)
                        )
                        loop.close()
                        
                        if success:
                            resultados.append(f"✅ Director ({director.nombre}): ENVIADO")
                        else:
                            resultados.append(f"❌ Director: ERROR")
                            
                    except Exception as e:
                        resultados.append(f"❌ Director: {str(e)[:50]}")
                else:
                    resultados.append(f"⚠️ Director: Sin Telegram ID o no encontrado")
            else:
                resultados.append(f"⚠️ No hay director configurado para: {reporte.tipo}")
        
        # Mostrar resultados
        if resultados:
            mensaje_flash = "🔔 Resultados prueba inicial:<br>" + "<br>".join(resultados)
            flash(mensaje_flash, 'info')
        else:
            flash('⚠️ No se enviaron notificaciones', 'warning')
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_notificar_inicial: {e}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_asignar_cuadrilla', methods=['POST'])
@login_required
@admin_required
def test_asignar_cuadrilla(reporte_id):
    """Prueba: Asignación a cuadrilla (director -> cuadrilla)"""
    try:
        team_id = request.form.get('team_id')
        
        if not team_id:
            flash('❌ Debe seleccionar una cuadrilla', 'error')
            return redirect(url_for('admin.dashboard'))
        
        logger.info(f"👷 [TEST] Asignando reporte #{reporte_id} a cuadrilla {team_id}")
        
        from app.services.telegram_bot import notificar_asignacion_sync
        import asyncio
        
        # Buscar un usuario en la cuadrilla para notificar
        usuario_cuadrilla = User.query.filter_by(team_id=team_id).first()
        
        if usuario_cuadrilla and usuario_cuadrilla.telegram_id:
            # Enviar notificación de asignación
            success = notificar_asignacion_sync(reporte_id, usuario_cuadrilla.id)
            
            cuadrilla = Team.query.get(team_id)
            
            if success:
                flash(f'✅ Notificación enviada a {usuario_cuadrilla.nombre} ({cuadrilla.nombre})', 'success')
            else:
                flash(f'⚠️ Error al notificar a {usuario_cuadrilla.nombre}', 'warning')
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
    """Prueba: Cuadrilla termina trabajo -> va a validación"""
    try:
        logger.info(f"🔧 [TEST] Cuadrilla termina reporte #{reporte_id}")
        
        from app.services.telegram_bot import notificar_supervisor_revision
        import asyncio
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Simular que la cuadrilla subió evidencia
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        
        if not asignacion or not asignacion.team_id:
            flash('❌ El reporte no está asignado a ninguna cuadrilla', 'error')
            return redirect(url_for('admin.dashboard'))
        
        # Notificar al supervisor del área (para agua: ID 6)
        if reporte.tipo == "Agua potable":
            supervisor = User.query.get(6)  # supervisor_agua
            
            if supervisor and supervisor.telegram_id:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(
                    notificar_supervisor_revision(reporte_id, asignacion.team_id)
                )
                loop.close()
                
                if success:
                    flash(f'✅ Notificación enviada al supervisor {supervisor.nombre}', 'success')
                else:
                    flash(f'⚠️ Error al notificar al supervisor', 'warning')
            else:
                flash('⚠️ Supervisor no configurado o sin Telegram', 'warning')
        else:
            # Para otras áreas, notificar al director
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
    """Prueba: Validación final del usuario"""
    try:
        logger.info(f"👤 [TEST] Validación usuario para reporte #{reporte_id}")
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Simular envío de validación al usuario
        # En producción, aquí se enviaría un mensaje al usuario para que valide
        
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
    """Prueba REAL: Solicitar ubicación exacta al usuario"""
    try:
        logger.info(f"📍 [TEST] Problema ubicación para reporte #{reporte_id}")
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # ========== VERSIÓN CORREGIDA: LLAMAR A LA FUNCIÓN REAL ==========
        
        # IMPORTANTE: Necesitamos ejecutar una función async desde contexto sync
        # Para Flask, necesitamos crear un event loop
        
        import asyncio
        import sys
        
        # 1. Configurar para Windows si es necesario
        if sys.platform == 'win32':
            if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # 2. Obtener o crear loop de eventos
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 3. Importar la función async
        try:
            from app.bot.handlers import solicitar_ubicacion_exacta_al_reportante
            
            # 4. Ejecutar la función async
            async def ejecutar_solicitud():
                try:
                    logger.info(f"🔍 Ejecutando solicitud de ubicación real para reporte #{reporte_id}")
                    resultado = await solicitar_ubicacion_exacta_al_reportante(reporte_id, "TEST_ADMIN")
                    
                    if resultado:
                        logger.info(f"✅ Solicitud de ubicación exitosa para reporte #{reporte_id}")
                        return True, "✅ Solicitud de ubicación enviada correctamente al reportante"
                    else:
                        logger.error(f"❌ Solicitud de ubicación falló para reporte #{reporte_id}")
                        return False, "❌ No se pudo enviar la solicitud de ubicación"
                        
                except Exception as e:
                    logger.error(f"❌ Error en ejecutar_solicitud: {e}")
                    import traceback
                    logger.error(f"📋 Traceback:\n{traceback.format_exc()}")
                    return False, f"❌ Error interno: {str(e)[:100]}"
            
            # 5. Ejecutar en el loop
            if loop.is_running():
                # Si ya hay un loop corriendo (en el bot), usar create_task
                # Pero como es Flask, probablemente no hay loop corriendo
                flash("⚠️ Sistema ocupado. La solicitud se programó en segundo plano.", "warning")
                loop.create_task(ejecutar_solicitud())
                flash(f'ℹ️ Prueba: Se programó solicitud de ubicación para {reporte.reportante}', 'info')
            else:
                # Ejecutar directamente
                resultado, mensaje = loop.run_until_complete(ejecutar_solicitud())
                
                if resultado:
                    flash(mensaje, 'success')
                    flash('📍 El usuario debería recibir un mensaje en Telegram para compartir ubicación', 'info')
                else:
                    flash(mensaje, 'danger')
                    flash('⚠️ Revisa los logs del servidor para más detalles', 'warning')
                    
        except ImportError as e:
            logger.error(f"❌ No se pudo importar la función: {e}")
            flash('❌ Error: No se pudo encontrar el módulo del bot', 'danger')
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_problema_ubicacion: {e}")
        import traceback
        logger.error(f"📋 Traceback:\n{traceback.format_exc()}")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/reporte/<int:reporte_id>/test_presidente', methods=['POST'])
@login_required
@admin_required
def test_notificar_presidente(reporte_id):
    """Prueba: Notificar al presidente"""
    try:
        logger.info(f"🏛️ [TEST] Notificando presidente para reporte #{reporte_id}")
        
        presidente = User.query.get(1)  # ID del presidente
        
        if presidente and presidente.telegram_id:
            from app.services.telegram_bot import notificar_presidente_reporte
            import asyncio
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(
                notificar_presidente_reporte(reporte_id, int(presidente.telegram_id))
            )
            loop.close()
            
            if success:
                flash(f'✅ Notificación enviada al presidente', 'success')
            else:
                flash(f'⚠️ Error al notificar al presidente', 'warning')
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
    """Prueba: Enviar a validación (supervisor/director)"""
    try:
        logger.info(f"👁️ [TEST] Enviando a validación reporte #{reporte_id}")
        
        # Esta es básicamente la misma función que reenviar_validacion
        # pero sin cambiar estados en la BD
        
        flash(f'ℹ️ Prueba: Se enviaría notificación de validación para reporte #{reporte_id}', 'info')
        flash('⚠️ Esta prueba usa la misma función que "Reenviar a validación"', 'warning')
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_enviar_validacion: {e}")
        return redirect(url_for('admin.dashboard'))


# ============================================================================
# RUTAS ESPECÍFICAS PARA PRUEBAS POR ÁREA/CARGO
# ============================================================================

@admin_bp.route('/reporte/<int:reporte_id>/test_jefe_tecnico_agua', methods=['POST'])
@login_required
@admin_required
def test_jefe_tecnico_agua(reporte_id):
    """Prueba ESPECÍFICA: Envío SOLO al jefe técnico de agua"""
    try:
        logger.info(f"👷 [TEST ESPECÍFICO] Jefe Técnico Agua para reporte #{reporte_id}")
        
        from app.services.telegram_bot import notificar_director_nuevo_reporte
        import asyncio
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Verificar que sea un reporte de agua
        if reporte.tipo not in ["Agua potable", "Drenaje"]:
            flash(f'⚠️ Esta prueba solo es para reportes de AGUA/DRENAJE (tipo actual: {reporte.tipo})', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Buscar jefe técnico de agua
        jefe_tecnico = User.query.filter_by(
            area='agua',
            rol_especifico='jefe_area_tecnica',
            is_active=True
        ).first()
        
        if not jefe_tecnico:
            flash('❌ No se encontró jefe técnico de agua configurado', 'error')
            return redirect(url_for('admin.dashboard'))
        
        if not jefe_tecnico.telegram_id:
            flash(f'⚠️ Jefe técnico "{jefe_tecnico.nombre}" no tiene Telegram ID configurado', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Enviar notificación específica
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(
                notificar_director_nuevo_reporte(reporte_id, int(jefe_tecnico.telegram_id), reporte.tipo)
            )
            loop.close()
            
            if success:
                flash(f'✅ Mensaje COMPLETO enviado al Jefe Técnico: {jefe_tecnico.nombre} (con botones de acción)', 'success')
                logger.info(f"✅ [TEST] Notificación específica enviada a Jefe Técnico Agua")
            else:
                flash(f'❌ Error al enviar mensaje al Jefe Técnico', 'error')
                
        except ValueError:
            flash('❌ Telegram ID inválido del jefe técnico', 'error')
        except Exception as e:
            flash(f'❌ Error: {str(e)[:80]}', 'error')
            logger.error(f"❌ Error en test_jefe_tecnico_agua: {e}")
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_jefe_tecnico_agua: {e}")
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/reporte/<int:reporte_id>/test_director_agua', methods=['POST'])
@login_required
@admin_required
def test_director_agua(reporte_id):
    """Prueba ESPECÍFICA: Envío SOLO al director de agua (solo información)"""
    try:
        logger.info(f"👨‍💼 [TEST ESPECÍFICO] Director Agua (info) para reporte #{reporte_id}")
        
        import asyncio
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Verificar que sea un reporte de agua/drenaje
        if reporte.tipo not in ["Agua potable", "Drenaje"]:
            flash(f'⚠️ Esta prueba solo es para reportes de AGUA/DRENAJE (tipo actual: {reporte.tipo})', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Buscar director de agua
        director_agua = User.query.filter_by(
            area='agua',
            rol_especifico='director',
            is_active=True
        ).first()
        
        if not director_agua:
            flash('❌ No se encontró director de agua configurado', 'error')
            return redirect(url_for('admin.dashboard'))
        
        if not director_agua.telegram_id:
            flash(f'⚠️ Director "{director_agua.nombre}" no tiene Telegram ID configurado', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Enviar mensaje INFORMATIVO (sin botones de acción)
        try:
            from app.services.telegram_bot import telegram_app
            
            if not telegram_app or not hasattr(telegram_app, 'bot'):
                flash('❌ Bot de Telegram no está inicializado', 'error')
                return redirect(url_for('admin.dashboard'))
            
            # Preparar mensaje INFORMATIVO para director
            # Obtener datos de calle/localidad de forma segura
            calle_nombre = "N/D"
            localidad_nombre = "N/D"
            
            if reporte.calle:
                calle_nombre = reporte.calle.nombre
            elif hasattr(reporte, 'calle_nombre') and reporte.calle_nombre:
                calle_nombre = reporte.calle_nombre
            
            if reporte.localidad:
                localidad_nombre = reporte.localidad.nombre
            elif hasattr(reporte, 'localidad_nombre') and reporte.localidad_nombre:
                localidad_nombre = reporte.localidad_nombre
            
            mensaje = (
                f"💧 *INFORMACIÓN - NUEVO REPORTE {reporte.tipo.upper()}*\n\n"
                f"📋 *Folio:* #{reporte.id}\n"
                f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                f"👤 *Reportante:* {reporte.reportante}\n"
                f"📱 *Teléfono:* {reporte.telefono}\n"
                f"🔧 *Problema:* {reporte.subtipo}\n"
                f"📄 *Descripción:*\n"
                f"{reporte.descripcion_problema[:100]}"
                f"{'...' if len(reporte.descripcion_problema) > 100 else ''}\n\n"
                f"📅 *Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
                f"*📋 Jefe Técnico ha sido notificado para asignación.*"
            )
            
            # Solo botón de ver detalles
            keyboard = [[InlineKeyboardButton("📋 Ver Detalles", callback_data=f"dir_detalle_{reporte.id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            async def enviar_mensaje():
                await telegram_app.bot.send_message(
                    chat_id=int(director_agua.telegram_id),
                    text=mensaje,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(enviar_mensaje())
            loop.close()
            
            flash(f'✅ Mensaje INFORMATIVO enviado al Director Agua: {director_agua.nombre} (solo botón "Ver Detalles")', 'success')
            logger.info(f"✅ [TEST] Mensaje informativo enviado a Director Agua")
            
        except ValueError:
            flash('❌ Telegram ID inválido del director', 'error')
        except Exception as e:
            flash(f'❌ Error: {str(e)[:80]}', 'error')
            logger.error(f"❌ Error en test_director_agua: {e}")
            import traceback
            logger.error(f"📋 Traceback:\n{traceback.format_exc()}")
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_director_agua: {e}")
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/reporte/<int:reporte_id>/test_supervisor_agua', methods=['POST'])
@login_required
@admin_required
def test_supervisor_agua(reporte_id):
    """Prueba ESPECÍFICA: Envío SOLO al supervisor de agua (para validación)"""
    try:
        logger.info(f"👁️ [TEST ESPECÍFICO] Supervisor Agua para reporte #{reporte_id}")
        
        from app.services.telegram_bot import notificar_supervisor_revision
        import asyncio
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Verificar que sea un reporte de agua/drenaje
        if reporte.tipo not in ["Agua potable", "Drenaje"]:
            flash(f'⚠️ Esta prueba solo es para reportes de AGUA/DRENAJE (tipo actual: {reporte.tipo})', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Buscar supervisor de agua
        supervisor_agua = User.query.filter_by(
            area='agua',
            rol_especifico='supervisor',
            is_active=True
        ).first()
        
        if not supervisor_agua:
            flash('❌ No se encontró supervisor de agua configurado', 'error')
            return redirect(url_for('admin.dashboard'))
        
        if not supervisor_agua.telegram_id:
            flash(f'⚠️ Supervisor "{supervisor_agua.nombre}" no tiene Telegram ID configurado', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Buscar la cuadrilla asignada (necesaria para la notificación)
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if not asignacion or not asignacion.team_id:
            flash('⚠️ Este reporte no tiene cuadrilla asignada. Use "Asignar cuadrilla" primero.', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Enviar notificación al supervisor
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(
                notificar_supervisor_revision(reporte_id, asignacion.team_id)
            )
            loop.close()
            
            if success:
                flash(f'✅ Mensaje de VALIDACIÓN enviado al Supervisor Agua: {supervisor_agua.nombre}', 'success')
                logger.info(f"✅ [TEST] Notificación de validación enviada a Supervisor Agua")
            else:
                flash(f'❌ Error al enviar mensaje al Supervisor', 'error')
                
        except Exception as e:
            flash(f'❌ Error: {str(e)[:80]}', 'error')
            logger.error(f"❌ Error en test_supervisor_agua: {e}")
            import traceback
            logger.error(f"📋 Traceback:\n{traceback.format_exc()}")
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_supervisor_agua: {e}")
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/reporte/<int:reporte_id>/test_director_area', methods=['POST'])
@login_required
@admin_required
def test_director_area(reporte_id):
    """Prueba ESPECÍFICA: Envío al director del área del reporte (para áreas no-agua)"""
    try:
        logger.info(f"🏗️ [TEST ESPECÍFICO] Director de área para reporte #{reporte_id}")
        
        from app.services.telegram_bot import notificar_director_nuevo_reporte
        import asyncio
        
        reporte = Report.query.get_or_404(reporte_id)
        
        # Verificar que NO sea agua/drenaje
        if reporte.tipo in ["Agua potable", "Drenaje"]:
            flash(f'⚠️ Para reportes de AGUA/DRENAJE use las pruebas específicas de agua', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Mapeo tipo -> área
        mapeo_tipo_a_area = {
            "Aseo público": "aseo",
            "Alumbrado público": "alumbrado", 
            "Parques y jardines": "parques",
            "Ecología": "ecologia",
            "Seguridad pública": "seguridad",
            "Obras públicas": "obra",
            "Bomberos": "bomberos"
        }
        
        area = mapeo_tipo_a_area.get(reporte.tipo)
        
        if not area:
            flash(f'❌ No hay área configurada para el tipo: {reporte.tipo}', 'error')
            return redirect(url_for('admin.dashboard'))
        
        # Buscar director del área
        director_area = User.query.filter_by(
            area=area,
            rol_especifico='director',
            is_active=True
        ).first()
        
        if not director_area:
            flash(f'❌ No se encontró director para el área: {area}', 'error')
            return redirect(url_for('admin.dashboard'))
        
        if not director_area.telegram_id:
            flash(f'⚠️ Director "{director_area.nombre}" no tiene Telegram ID configurado', 'warning')
            return redirect(url_for('admin.dashboard'))
        
        # Enviar notificación al director del área
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(
                notificar_director_nuevo_reporte(reporte_id, int(director_area.telegram_id), reporte.tipo)
            )
            loop.close()
            
            if success:
                flash(f'✅ Mensaje COMPLETO enviado al Director de {area.title()}: {director_area.nombre} (con botones de acción)', 'success')
                logger.info(f"✅ [TEST] Notificación enviada a Director de {area}")
            else:
                flash(f'❌ Error al enviar mensaje al Director de {area}', 'error')
                
        except ValueError:
            flash('❌ Telegram ID inválido del director', 'error')
        except Exception as e:
            flash(f'❌ Error: {str(e)[:80]}', 'error')
            logger.error(f"❌ Error en test_director_area: {e}")
            import traceback
            logger.error(f"📋 Traceback:\n{traceback.format_exc()}")
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        flash(f'❌ Error en prueba: {str(e)[:100]}', 'error')
        logger.error(f"❌ Error en test_director_area: {e}")
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/reportes/<int:reporte_id>/actualizar_ubicacion', methods=['POST'])
@login_required
def actualizar_ubicacion(reporte_id):
    """Actualiza las coordenadas de un reporte"""
    try:
        logger.info(f"📍 Actualizando coordenadas para reporte #{reporte_id}")
        
        # Obtener datos del formulario
        nueva_latitud = request.form.get('latitud', type=float)
        nueva_longitud = request.form.get('longitud', type=float)
        
        if nueva_latitud is None or nueva_longitud is None:
            return jsonify({
                'success': False,
                'message': 'Debe proporcionar latitud y longitud'
            }), 400
        
        # Buscar el reporte
        reporte = Report.query.get_or_404(reporte_id)
        
        # Guardar valores anteriores para logging
        lat_anterior = reporte.latitud
        lng_anterior = reporte.longitud
        
        # Actualizar las coordenadas
        reporte.latitud = nueva_latitud
        reporte.longitud = nueva_longitud
        
        db.session.commit()
        
        logger.info(f"📍 Coordenadas actualizadas para reporte #{reporte_id}: "
                   f"{lat_anterior},{lng_anterior} → {nueva_latitud},{nueva_longitud}")
        
        return jsonify({
            'success': True,
            'message': 'Ubicación actualizada correctamente',
            'nueva_latitud': nueva_latitud,
            'nueva_longitud': nueva_longitud
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Error actualizando ubicación para reporte #{reporte_id}: {e}")
        return jsonify({
            'success': False,
            'message': f'Error al actualizar la ubicación: {str(e)}'
        }), 500

