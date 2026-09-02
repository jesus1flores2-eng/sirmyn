"""
Blueprint para el Centro de Inteligencia Municipal
Totalmente independiente - No afecta rutas existentes
"""
from flask import Blueprint, render_template, jsonify, request, current_app, session, redirect, url_for
from flask_login import login_required, current_user
from app.models.report import Report, Localidad, Calle, Assignment
from app.models.status import Status
from app.models.team import Team
from app.extensions import db
from app.services.analitica_service import AnaliticaService
from datetime import datetime, timedelta
import json

inteligencia_bp = Blueprint('inteligencia', __name__)


def _tiene_acceso():
    """Verifica si el usuario actual puede ver inteligencia"""
    if current_user.is_authenticated:
        if current_user.is_admin() or getattr(current_user, 'role', None) == 'supervisor':
            return True

    if session.get('municipio_id'):
        return True

    return False


def _obtener_municipio_id():
    """Devuelve municipio_id si es municipio, None si es admin/supervisor"""
    return session.get('municipio_id', None)


@inteligencia_bp.route('/')
@inteligencia_bp.route('/dashboard')
def dashboard():
    """Dashboard principal de inteligencia"""
    if not _tiene_acceso():
        return redirect(url_for('auth.login'))

    dias = request.args.get('dias', 30, type=int)
    tipo = request.args.get('tipo', '')
    localidad_id = request.args.get('localidad_id', '', type=str)

    municipio_id = _obtener_municipio_id()

    analitica = AnaliticaService()

    tipos = db.session.query(Report.tipo).distinct().all()
    tipos = [t[0] for t in tipos if t[0]]

    if municipio_id:
        localidades = Localidad.query.filter_by(municipio_id=municipio_id).all()
    else:
        localidades = Localidad.query.all()

    metricas = analitica.metricas_generales(dias, tipo, localidad_id)

    return render_template(
        'inteligencia/dashboard.html',
        metricas=metricas,
        tipos=tipos,
        localidades=localidades,
        dias=dias,
        tipo_seleccionado=tipo,
        localidad_seleccionada=localidad_id
    )


@inteligencia_bp.route('/api/eficiencia-departamentos')
def api_eficiencia_departamentos():
    """API: Eficiencia por tipo/departamento"""
    try:
        dias = request.args.get('dias', 30, type=int)
        analitica = AnaliticaService()

        data = analitica.eficiencia_por_departamento(dias)

        departamentos = []
        atendidos_data = []
        no_atendidos_data = []
        eficiencia_data = []

        for depto, valores in data.items():
            departamentos.append(depto)
            atendidos_data.append(valores['atendidos'])
            no_atendidos_data.append(valores['pendientes'])
            eficiencia_data.append(valores['eficiencia'])

        return jsonify({
            'success': True,
            'departamentos': departamentos,
            'atendidos': atendidos_data,
            'no_atendidos': no_atendidos_data,
            'eficiencia': eficiencia_data,
            'raw_data': data
        })
    except Exception as e:
        current_app.logger.error(f"Error en api_eficiencia_departamentos: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@inteligencia_bp.route('/api/focos-rojos')
def api_focos_rojos():
    """API: Top 10 focos rojos"""
    try:
        dias = request.args.get('dias', 30, type=int)
        limite = request.args.get('limite', 10, type=int)
        tipo = request.args.get('tipo', '')

        analitica = AnaliticaService()
        data = analitica.focos_rojos(dias, limite, tipo)

        return jsonify({
            'success': True,
            'focos_rojos': data
        })
    except Exception as e:
        current_app.logger.error(f"Error en api_focos_rojos: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@inteligencia_bp.route('/api/tendencias-mensuales')
def api_tendencias_mensuales():
    """API: Tendencia últimos 6 meses"""
    try:
        analitica = AnaliticaService()
        data = analitica.tendencias_mensuales()
        return jsonify({'success': True, 'tendencias': data})
    except Exception as e:
        current_app.logger.error(f"Error en api_tendencias_mensuales: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@inteligencia_bp.route('/api/geolocalizacion')
def api_geolocalizacion():
    """API: Puntos geolocalizados para el mapa"""
    try:
        dias = request.args.get('dias', 30, type=int)
        tipo = request.args.get('tipo', '')
        estado = request.args.get('estado', '')

        analitica = AnaliticaService()
        resultado = analitica.obtener_puntos_mapa(dias, tipo)

        puntos = resultado['puntos']
        if estado:
            if estado == 'atendido':
                puntos = [p for p in puntos if p['estado'] == 'Atendido']
            elif estado == 'pendiente':
                puntos = [p for p in puntos if p['estado'] == 'Pendiente']

        return jsonify({
            'success': True,
            'puntos': puntos,
            'estadisticas': resultado['estadisticas'],
            'total': len(puntos)
        })
    except Exception as e:
        current_app.logger.error(f"Error en api_geolocalizacion: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@inteligencia_bp.route('/api/detalle-departamento/<string:tipo>')
def api_detalle_departamento(tipo):
    """API: Drill-down por departamento"""
    try:
        dias = request.args.get('dias', 30, type=int)
        analitica = AnaliticaService()

        detalle = analitica.detalle_por_departamento(tipo, dias)

        return jsonify({
            'success': True,
            'departamento': tipo,
            'detalle': detalle
        })
    except Exception as e:
        current_app.logger.error(f"Error en api_detalle_departamento: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@inteligencia_bp.route('/mapa-calor')
def mapa_calor():
    """Vista del mapa con base_mapa.html"""
    if not _tiene_acceso():
        return redirect(url_for('auth.login'))

    return render_template('inteligencia/mapa_final.html')


@inteligencia_bp.route('/reporte-detallado')
def reporte_detallado():
    if not _tiene_acceso():
        return redirect(url_for('auth.login'))

    analitica = AnaliticaService()
    dias = request.args.get('dias', 30, type=int)
    tipo = request.args.get('tipo', '')

    reportes = analitica.obtener_reportes_detallados(dias, tipo)

    tipos = db.session.query(Report.tipo).distinct().all()
    tipos_disponibles = [t[0] for t in tipos if t[0]]

    municipio_id = _obtener_municipio_id()
    if municipio_id:
        localidades = Localidad.query.filter_by(municipio_id=municipio_id).all()
    else:
        localidades = Localidad.query.all()

    return render_template('inteligencia/reporte_detallado.html',
                         reportes=reportes,
                         dias=dias,
                         tipo_seleccionado=tipo,
                         tipos_disponibles=tipos_disponibles,
                         localidades=localidades,
                         filtro_estado=request.args.get('estado', ''),
                         localidad_seleccionada=request.args.get('localidad_id', ''))


@inteligencia_bp.route('/api/mapa/departamentos')
def obtener_departamentos():
    """API para obtener estadísticas por departamento"""
    try:
        dias = request.args.get('dias', 30, type=int)

        service = AnaliticaService()
        departamentos = service.obtener_estadisticas_departamentos(dias=dias)

        return jsonify({
            'success': True,
            'departamentos': departamentos
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@inteligencia_bp.route('/api/gps/cuadrillas')
def api_gps_cuadrillas():
    """API: Ubicaciones GPS en tiempo real"""
    try:
        from app.models.gps_dispositivo import GpsDispositivo

        limite = datetime.utcnow() - timedelta(minutes=5)
        dispositivos = GpsDispositivo.query.filter(
            GpsDispositivo.ultima_actualizacion >= limite
        ).all()

        return jsonify({
            'success': True,
            'dispositivos': [{
                'id': d.id,
                'nombre': d.nombre,
                'imei': d.imei,
                'lat': d.ultima_latitud,
                'lng': d.ultima_longitud,
                'velocidad': d.ultima_velocidad,
                'cuadrilla': d.team.nombre if d.team else 'Sin asignar',
                'actualizado': d.ultima_actualizacion.strftime('%H:%M:%S') if d.ultima_actualizacion else None
            } for d in dispositivos if d.ultima_latitud and d.ultima_longitud]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
