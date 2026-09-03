from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required, current_user
from app.models.report import Report, Assignment, Localidad, Calle
from app.models.team import Team
from app.models.status import Status
from app.models.municipio_config import MunicipioConfig
from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import asyncio


municipio_bp = Blueprint('municipio', __name__, url_prefix='/municipio')


@municipio_bp.route('/dashboard')
def dashboard():
    """Dashboard del municipio - Vista limitada"""
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    if not municipio:
        flash("No hay municipio configurado.", "warning")
        return redirect(url_for('auth.login'))

    municipio_id = municipio.id

    departamentos_activos = municipio.get_departamentos_lista()

    mapeo_area_tipo = {
        'agua': 'Agua potable',
        'drenaje': 'Drenaje',
        'aseo': 'Aseo público',
        'alumbrado': 'Alumbrado público',
        'parques': 'Parques y jardines',
        'ecologia': 'Ecología',
        'seguridad': 'Seguridad pública',
        'obras': 'Obras públicas',
        'bomberos': 'Bomberos'
    }

    tipos_permitidos = [mapeo_area_tipo.get(d, d) for d in departamentos_activos]
    emergencias_activas = municipio.get_emergencias_lista() if municipio else []

    mapeo_emergencia_tipo = {
        'seguridad': 'Seguridad pública',
        'bomberos': 'Bomberos',
        'proteccion_civil': 'Protección Civil',
        'punto_violeta': 'Punto Violeta',
        'ambulancia': 'Ambulancia'
    }

    tipos_emergencias = [mapeo_emergencia_tipo.get(e, e) for e in emergencias_activas]

    tipos_permitidos = list(set(tipos_permitidos + tipos_emergencias))

    if tipos_permitidos:
        reportes = Report.query.filter(
            Report.tipo.in_(tipos_permitidos),
            Report.municipio_id == municipio_id
        ).order_by(Report.timestamp.desc()).all()
    else:
        reportes = []

    for r in reportes:
        asignacion = r.asignaciones[-1] if r.asignaciones else None
        if asignacion:
            r.cuadrilla = asignacion.team.nombre if asignacion.team else "Sin cuadrilla"
            r.estado = asignacion.status.descripcion if asignacion.status else "Sin estado"
        else:
            r.cuadrilla = "Sin asignación"
            r.estado = "Sin estado"

    total_reportes = len(reportes)
    atendidos = sum(1 for r in reportes if r.estado == 'Finalizado')
    pendientes = total_reportes - atendidos

    ver_cuadrillas = municipio.ver_cuadrillas
    ver_estados = municipio.ver_estados
    ver_inteligencia = municipio.ver_inteligencia
    ver_gps = municipio.ver_gps
    ver_encuestas = municipio.ver_encuestas
    ver_exportar = municipio.ver_exportar
    ver_historial = municipio.ver_historial
    ver_mapa = municipio.ver_mapa
    ver_test = municipio.ver_test
    ver_editar_coordenadas = municipio.ver_editar_coordenadas
    ver_filtros = municipio.ver_filtros

    return render_template(
        'municipio/dashboard.html',
        municipio=municipio,
        reportes=reportes,
        total_reportes=total_reportes,
        atendidos=atendidos,
        pendientes=pendientes,
        tipos_permitidos=tipos_permitidos,
        ver_cuadrillas=ver_cuadrillas,
        ver_estados=ver_estados,
        ver_inteligencia=ver_inteligencia,
        ver_gps=ver_gps,
        ver_encuestas=ver_encuestas,
        ver_exportar=ver_exportar,
        ver_historial=ver_historial,
        ver_mapa=ver_mapa,
        ver_test=ver_test,
        ver_editar_coordenadas=ver_editar_coordenadas,
        ver_filtros=ver_filtros
    )

@municipio_bp.route('/historial/<int:reporte_id>')
def historial_reporte(reporte_id):
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    reporte = Report.query.filter_by(
        id=reporte_id,
        municipio_id=municipio.id
    ).first_or_404()

    asignaciones = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).all()

    return render_template(
        'municipio/historial.html',
        municipio=municipio,
        reporte=reporte,
        asignaciones=asignaciones
    )

@municipio_bp.route('/cuadrillas')
def cuadrillas():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    if not municipio.ver_cuadrillas:
        flash("No tienes acceso a Cuadrillas.", "danger")
        return redirect(url_for('municipio.dashboard'))

    from app.models.user import User

    municipio_id = municipio.id
    areas_permitidas = municipio.get_departamentos_lista()

    cuadrillas = Team.query.filter(
        Team.municipio_id == municipio_id,
        Team.nombre != 'Sin asignar',
        Team.area.in_(areas_permitidas)
    ).all()

    if areas_permitidas:
        usuarios = User.query.filter(
            User.municipio_id == municipio_id,
            User.area.in_(areas_permitidas)
        ).all()
    else:
        usuarios = User.query.filter_by(municipio_id=municipio_id).all()

    return render_template(
        'municipio/cuadrillas.html',
        municipio=municipio,
        cuadrillas=cuadrillas,
        usuarios=usuarios,
        limite=municipio.limite_cuadrillas,
        areas_permitidas=areas_permitidas
    )

@municipio_bp.route('/cuadrillas/crear', methods=['POST'])
def crear_cuadrilla_municipio():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    nombre = request.form.get('nombre', '').strip()
    area = request.form.get('area', '').strip()
    descripcion = request.form.get('descripcion', '').strip()

    if not nombre or not area:
        flash("Nombre y área son obligatorios.", "warning")
        return redirect(url_for('municipio.cuadrillas'))

    total_cuadrillas = Team.query.filter(
        Team.nombre != 'Sin asignar',
        Team.municipio_id == municipio.id
    ).count()

    if total_cuadrillas >= municipio.limite_cuadrillas:
        flash(f"Límite de cuadrillas alcanzado. Tu plan permite {municipio.limite_cuadrillas}.", "danger")
        return redirect(url_for('municipio.cuadrillas'))

    if Team.query.filter_by(nombre=nombre, municipio_id=municipio.id).first():
        flash("Ya existe una cuadrilla con ese nombre.", "error")
        return redirect(url_for('municipio.cuadrillas'))

    nueva = Team(
        nombre=nombre,
        area=area,
        descripcion=descripcion,
        municipio_id=municipio.id
    )
    db.session.add(nueva)
    db.session.commit()

    flash(f"Cuadrilla '{nombre}' creada.", "success")
    return redirect(url_for('municipio.cuadrillas'))


@municipio_bp.route('/cuadrillas/<int:id>/editar', methods=['POST'])
def editar_cuadrilla_municipio(id):
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    cuadrilla = Team.query.get_or_404(id)

    cuadrilla.nombre = request.form.get('nombre', cuadrilla.nombre)
    cuadrilla.area = request.form.get('area', cuadrilla.area)
    cuadrilla.descripcion = request.form.get('descripcion', cuadrilla.descripcion or '')

    db.session.commit()
    flash(f"Cuadrilla '{cuadrilla.nombre}' actualizada.", "success")
    return redirect(url_for('municipio.cuadrillas'))
    
@municipio_bp.route('/usuarios')
def usuarios():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    from app.models.user import User

    usuarios = User.query.filter_by(municipio_id=municipio.id).all()
    cuadrillas = Team.query.filter(
        Team.municipio_id == municipio.id,
        Team.nombre != 'Sin asignar'
    ).all()

    areas_permitidas = municipio.get_departamentos_lista()

    return render_template(
        'municipio/usuarios.html',
        municipio=municipio,
        usuarios=usuarios,
        cuadrillas=cuadrillas,
        areas_permitidas=areas_permitidas
    )


@municipio_bp.route('/usuarios/crear', methods=['POST'])
def crear_usuario_municipio():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    from app.models.user import User

    nombre = request.form.get('nombre', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    team_id = request.form.get('team_id', type=int)
    rol_especifico = request.form.get('rol_especifico', 'cuadrilla')
    area = request.form.get('area', '').strip()
    telegram_id = request.form.get('telegram_id', '').strip()

    if not nombre or not username or not password:
        flash("Nombre, usuario y contraseña son obligatorios.", "warning")
        return redirect(url_for('municipio.usuarios'))

    if User.query.filter_by(username=username).first():
        flash("El nombre de usuario ya existe.", "error")
        return redirect(url_for('municipio.usuarios'))

    nuevo = User(
        nombre=nombre,
        username=username,
        team_id=team_id if team_id else None,
        rol_especifico=rol_especifico,
        area=area if area else None,
        telegram_id=telegram_id if telegram_id else None,
        municipio_id=municipio.id,
        role='cuadrilla',
        nivel='cuadrilla'
    )
    nuevo.set_password(password)

    db.session.add(nuevo)
    db.session.commit()

    flash(f"Usuario '{username}' creado correctamente.", "success")
    return redirect(url_for('municipio.usuarios'))

@municipio_bp.route('/encuestas')
def encuestas():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    if not municipio.ver_encuestas:
        flash("No tienes acceso a Encuestas.", "danger")
        return redirect(url_for('municipio.dashboard'))

    from app.models.feedback import EncuestaSatisfaccion

    encuestas = EncuestaSatisfaccion.query.filter_by(
        municipio_id=municipio.id
    ).order_by(EncuestaSatisfaccion.fecha.desc()).all()

    return render_template(
        'municipio/encuestas.html',
        municipio=municipio,
        encuestas=encuestas
    )

@municipio_bp.route('/gps')
def gps():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    if not municipio.ver_gps:
        flash("No tienes acceso a GPS.", "danger")
        return redirect(url_for('municipio.dashboard'))

    from app.models.gps_dispositivo import GpsDispositivo

    dispositivos = GpsDispositivo.query.filter_by(
        municipio_id=municipio.id
    ).all()

    cuadrillas = Team.query.filter_by(
        municipio_id=municipio.id,
    ).all()

    return render_template(
        'municipio/gps.html',
        municipio=municipio,
        dispositivos=dispositivos,
        cuadrillas=cuadrillas
    )


@municipio_bp.route('/gps/crear', methods=['POST'])
def crear_gps_municipio():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    from app.models.gps_dispositivo import GpsDispositivo

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    nombre = request.form.get('nombre', '').strip()
    imei = request.form.get('imei', '').strip()
    team_id = request.form.get('team_id', type=int)
    telefono_chip = request.form.get('telefono_chip', '').strip()
    compania = request.form.get('compania', '').strip()
    plan_datos = request.form.get('plan_datos', '').strip()

    if not nombre or not imei:
        flash("Nombre e IMEI son obligatorios.", "warning")
        return redirect(url_for('municipio.gps'))

    if GpsDispositivo.query.filter_by(imei=imei).first():
        flash("El IMEI ya está registrado.", "error")
        return redirect(url_for('municipio.gps'))

    nuevo = GpsDispositivo(
        nombre=nombre,
        imei=imei,
        team_id=team_id if team_id else None,
        telefono_chip=telefono_chip if telefono_chip else None,
        compania=compania if compania else None,
        plan_datos=plan_datos if plan_datos else None,
        municipio_id=municipio.id
    )
    db.session.add(nuevo)
    db.session.commit()

    flash(f"GPS '{nombre}' creado.", "success")
    return redirect(url_for('municipio.gps'))


@municipio_bp.route('/gps/<int:id>/editar', methods=['POST'])
def editar_gps_municipio(id):
    from app.models.gps_dispositivo import GpsDispositivo

    dispositivo = GpsDispositivo.query.get_or_404(id)

    dispositivo.nombre = request.form.get('nombre', dispositivo.nombre)
    dispositivo.telefono_chip = request.form.get('telefono_chip') or None
    dispositivo.compania = request.form.get('compania') or None
    dispositivo.plan_datos = request.form.get('plan_datos') or None
    team_id = request.form.get('team_id')
    dispositivo.team_id = int(team_id) if team_id else None

    db.session.commit()
    flash(f"GPS '{dispositivo.nombre}' actualizado.", "success")
    return redirect(url_for('municipio.gps'))


@municipio_bp.route('/gps/<int:id>/eliminar', methods=['POST'])
def eliminar_gps_municipio(id):
    from app.models.gps_dispositivo import GpsDispositivo

    dispositivo = GpsDispositivo.query.get_or_404(id)
    nombre = dispositivo.nombre
    db.session.delete(dispositivo)
    db.session.commit()

    flash(f"GPS '{nombre}' eliminado.", "warning")
    return redirect(url_for('municipio.gps'))
    
@municipio_bp.route('/calles')
def calles():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    localidades = Localidad.query.filter_by(municipio_id=municipio.id).all()
    calles = Calle.query.filter_by(municipio_id=municipio.id).all()

    return render_template(
        'municipio/calles.html',
        municipio=municipio,
        localidades=localidades,
        calles=calles
    )


@municipio_bp.route('/calles/crear', methods=['POST'])
def crear_calle_municipio():
    if not session.get('municipio_id'):
        flash("Debes iniciar sesión como municipio.", "warning")
        return redirect(url_for('auth.login'))

    municipio = MunicipioConfig.query.get(session['municipio_id'])

    nombre = request.form.get('nombre', '').strip()
    localidad_id = request.form.get('localidad_id', type=int)

    if not nombre or not localidad_id:
        flash("Nombre y localidad son obligatorios.", "warning")
        return redirect(url_for('municipio.calles'))

    nueva = Calle(
        nombre=nombre,
        localidad_id=localidad_id,
        municipio_id=municipio.id
    )
    db.session.add(nueva)
    db.session.commit()

    flash(f"Calle '{nombre}' creada.", "success")
    return redirect(url_for('municipio.calles'))
    
@municipio_bp.route('/mapa/<int:reporte_id>')
def mapa_reporte(reporte_id):
    reporte = Report.query.filter_by(id=reporte_id).first_or_404()
    asignacion = Assignment.query.filter_by(report_id=reporte.id).order_by(Assignment.timestamp.desc()).first()
    cuadrilla = asignacion.team.nombre if asignacion and asignacion.team else "Sin asignar"
    estado = asignacion.status.descripcion if asignacion and asignacion.status else "Sin estado"

    return render_template(
        'municipio/mapa_reporte.html',
        reporte=reporte,
        cuadrilla=cuadrilla,
        estado=estado,
        latitud=float(reporte.latitud),
        longitud=float(reporte.longitud)
    )

@municipio_bp.route('/test/<int:reporte_id>', methods=['POST'])
def test_notificaciones(reporte_id):
    from flask import session, flash

    if not session.get('municipio_id'):
        return redirect(url_for('auth.login'))

    reporte = Report.query.filter_by(
        id=reporte_id,
        municipio_id=session.get('municipio_id')
    ).first_or_404()

    from app.services.notification_service import notificar_director_nuevo_reporte

    try:
        asyncio.run(notificar_director_nuevo_reporte(
            reporte_id=reporte.id,
            telegram_id=reporte.telefono,
            tipo_reporte=reporte.tipo
        ))
        flash("Notificación de prueba enviada.", "success")
    except Exception as e:
        flash(f"Error: {str(e)[:100]}", "danger")

    return redirect(url_for('municipio.dashboard'))
    
@municipio_bp.route('/mapa/<int:reporte_id>/actualizar_ubicacion', methods=['POST'])
def actualizar_ubicacion(reporte_id):
    reporte = Report.query.filter_by(id=reporte_id, municipio_id=session.get('municipio_id')).first_or_404()
    reporte.latitud = float(request.form.get('latitud'))
    reporte.longitud = float(request.form.get('longitud'))
    db.session.commit()
    return jsonify({'success': True})
