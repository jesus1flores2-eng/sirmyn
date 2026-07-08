"""
Blueprint para el Centro de Inteligencia Municipal
Totalmente independiente - No afecta rutas existentes
"""
from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from app.models.report import Report, Localidad, Calle, Assignment
from app.models.status import Status
from app.models.team import Team
from app.extensions import db
from app.services.analitica_service import AnaliticaService
from datetime import datetime, timedelta
import json

inteligencia_bp = Blueprint('inteligencia', __name__)

@inteligencia_bp.route('/')
@inteligencia_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal de inteligencia"""
    # Control de acceso
    if current_user.role not in ['admin', 'supervisor']:
        return "Acceso no autorizado", 403
    
    # Obtener parámetros de filtro
    dias = request.args.get('dias', 30, type=int)
    tipo = request.args.get('tipo', '')
    localidad_id = request.args.get('localidad_id', '', type=str)
    
    # Inicializar servicio
    analitica = AnaliticaService()
    
    # Obtener datos para filtros
    tipos = db.session.query(Report.tipo).distinct().all()
    tipos = [t[0] for t in tipos if t[0]]
    
    localidades = Localidad.query.all()
    
    # Obtener métricas
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
@login_required
def api_eficiencia_departamentos():
    """API: Eficiencia por tipo/departamento"""
    try:
        dias = request.args.get('dias', 30, type=int)
        analitica = AnaliticaService()
        
        data = analitica.eficiencia_por_departamento(dias)
        
        # Preparar datos para Chart.js
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
@login_required
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
@login_required
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
@login_required
def api_geolocalizacion():
    """API: Puntos geolocalizados para el mapa"""
    try:
        dias = request.args.get('dias', 30, type=int)
        tipo = request.args.get('tipo', '')
        estado = request.args.get('estado', '')
        
        analitica = AnaliticaService()
        resultado = analitica.obtener_puntos_mapa(dias, tipo)
        
        # Filtrar por estado si se especifica
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
@login_required
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
@login_required
def mapa_calor():
    """Vista del mapa con base_mapa.html"""
    if current_user.role not in ['admin', 'supervisor']:
        return "Acceso no autorizado", 403
    
    return render_template('inteligencia/mapa_final.html')

@inteligencia_bp.route('/reporte-detallado')
@login_required
def reporte_detallado():
    if current_user.role not in ['admin', 'supervisor']:
        return "Acceso no autorizado", 403
    
    analitica = AnaliticaService()
    dias = request.args.get('dias', 30, type=int)
    tipo = request.args.get('tipo', '')
    
    reportes = analitica.obtener_reportes_detallados(dias, tipo)
    
    # Obtener tipos para filtros
    tipos = db.session.query(Report.tipo).distinct().all()
    tipos_disponibles = [t[0] for t in tipos if t[0]]
    
    # Obtener localidades para filtros
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
@login_required
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