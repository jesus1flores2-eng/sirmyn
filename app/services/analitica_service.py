"""
Servicio de análisis para inteligencia municipal
VERSIÓN FINAL - Compatible con estructura real de base de datos
"""
from app.models.report import Report
from app.models.status import Status
from app.models.team import Team
from app.models.report import Report, Localidad, Calle, Assignment
from app.extensions import db
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import func, and_, or_, case
import pandas as pd

class AnaliticaService:
    """Servicio principal de análisis de datos - COMPATIBLE CON TU DB"""
    
    def __init__(self):
        self.session = db.session
        self.FINALIZADO_STATUS_ID = 4  # ID de "Finalizado" según tu DB
    
    def _obtener_fecha_limite(self, dias):
        """Calcula fecha límite basada en días"""
        return datetime.utcnow() - timedelta(days=dias)
    
    def _obtener_ultima_asignacion_subquery(self):
        """Subquery para obtener la última asignación de cada reporte"""
        # Subquery para obtener la última asignación por reporte
        subquery = self.session.query(
            Assignment.report_id,
            func.max(Assignment.timestamp).label('max_timestamp')
        ).group_by(Assignment.report_id).subquery()
        
        return subquery
    
    def _obtener_status_actual_subquery(self):
        """Subquery para obtener el status actual de cada reporte"""
        subquery = self._obtener_ultima_asignacion_subquery()
        
        # Unir con Assignment para obtener el status_id actual
        status_subquery = self.session.query(
            Assignment.report_id,
            Assignment.status_id
        ).join(
            subquery,
            and_(
                Assignment.report_id == subquery.c.report_id,
                Assignment.timestamp == subquery.c.max_timestamp
            )
        ).subquery()
        
        return status_subquery
    
    def _obtener_cuadrilla_actual_subquery(self):
        """Subquery para obtener la cuadrilla actual de cada reporte"""
        subquery = self._obtener_ultima_asignacion_subquery()
        
        # Unir con Assignment para obtener el team_id actual
        cuadrilla_subquery = self.session.query(
            Assignment.report_id,
            Assignment.team_id
        ).join(
            subquery,
            and_(
                Assignment.report_id == subquery.c.report_id,
                Assignment.timestamp == subquery.c.max_timestamp
            )
        ).subquery()
        
        return cuadrilla_subquery
    
    def metricas_generales(self, dias=30, tipo='', localidad_id=''):
        """Obtiene métricas generales del sistema"""
        fecha_limite = self._obtener_fecha_limite(dias)
        
        # Subquery para status actual
        status_subquery = self._obtener_status_actual_subquery()
        
        # Construir filtros base
        filtros = [Report.timestamp >= fecha_limite]
        
        if tipo:
            filtros.append(Report.tipo == tipo)
        
        if localidad_id and localidad_id.isdigit():
            filtros.append(Report.localidad_id == int(localidad_id))
        
        # Consulta corregida con join a status actual
        query = self.session.query(
            func.count(Report.id).label('total'),
            func.sum(
                case((status_subquery.c.status_id == self.FINALIZADO_STATUS_ID, 1), else_=0)
            ).label('atendidos'),
            func.sum(
                case((status_subquery.c.status_id != self.FINALIZADO_STATUS_ID, 1), else_=0)
            ).label('no_atendidos')
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(*filtros)
        
        resultado = query.first()
        
        total = resultado.total or 0
        atendidos = resultado.atendidos or 0
        no_atendidos = resultado.no_atendidos or 0
        
        # Calcular eficiencia
        eficiencia = 0
        if total > 0:
            eficiencia = round((atendidos / total) * 100, 1)
        
        # Obtener tipos únicos para filtros
        tipos_query = self.session.query(Report.tipo).distinct().filter(
            Report.tipo.isnot(None)
        ).all()
        tipos = [t[0] for t in tipos_query if t[0]]
        
        return {
            'total_reportes': total,
            'atendidos': atendidos,
            'no_atendidos': no_atendidos,
            'eficiencia_general': eficiencia,
            'tipos_disponibles': tipos,
            'periodo_dias': dias
        }
    
    # 🎨 PALETA DE COLORES POR DEPARTAMENTO
    COLORES_DEPARTAMENTOS = {
        'Agua potable': '#3498db',  # Azul
        'Drenaje': '#2980b9',       # Azul oscuro
        'Aseo público': '#f39c12',  # Naranja
        'Alumbrado público': '#f1c40f',  # Amarillo
        'Parques y jardines': '#27ae60',  # Verde
        'Ecología': '#2ecc71',      # Verde claro
        'Seguridad pública': '#2c3e50',  # Gris oscuro
        'Obras públicas': '#e74c3c',  # Rojo
        'Bomberos': '#c0392b',      # Rojo oscuro
        'default': '#95a5a6'        # Gris por defecto
    }
    
    # 🏷️ ICONOS POR DEPARTAMENTO (opcional)
    ICONOS_DEPARTAMENTOS = {
        'Agua potable': '💧',
        'Drenaje': '🚰',
        'Aseo público': '🗑️',
        'Alumbrado público': '💡',
        'Parques y jardines': '🌳',
        'Ecología': '🌍',
        'Seguridad pública': '👮',
        'Obras públicas': '🏗️',
        'Bomberos': '🚒'
    }
    
    def eficiencia_por_departamento(self, dias=30):
        """Calcula eficiencia por tipo/departamento"""
        fecha_limite = self._obtener_fecha_limite(dias)
        status_subquery = self._obtener_status_actual_subquery()
        
        # Consulta optimizada con SQLAlchemy
        resultados = self.session.query(
            Report.tipo,
            func.count(Report.id).label('total'),
            func.sum(
                case((status_subquery.c.status_id == self.FINALIZADO_STATUS_ID, 1), else_=0)
            ).label('atendidos')
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(
            Report.timestamp >= fecha_limite,
            Report.tipo.isnot(None),
            Report.tipo != ''
        ).group_by(Report.tipo).all()
        
        data = {}
        for tipo, total, atendidos in resultados:
            atendidos = atendidos or 0
            pendientes = total - atendidos
            
            # Calcular eficiencia
            eficiencia = 0
            if total > 0:
                eficiencia = round((atendidos / total) * 100, 1)
            
            # Determinar nivel de alerta
            alerta = 'success'
            if eficiencia < 30:
                alerta = 'danger'
            elif eficiencia < 60:
                alerta = 'warning'
            elif eficiencia < 80:
                alerta = 'info'
            
            data[tipo] = {
                'total': total,
                'atendidos': atendidos,
                'pendientes': pendientes,
                'eficiencia': eficiencia,
                'alerta': alerta
            }
        
        return data
    
    def focos_rojos(self, dias=30, limite=10, tipo=''):
        """Identifica los focos rojos principales"""
        fecha_limite = self._obtener_fecha_limite(dias)
        status_subquery = self._obtener_status_actual_subquery()
        
        # Construir consulta base
        filtros = [
            Report.timestamp >= fecha_limite,
            status_subquery.c.status_id != self.FINALIZADO_STATUS_ID,  # Solo no atendidos
            Report.localidad_id.isnot(None),
            Report.calle_id.isnot(None)
        ]
        
        if tipo:
            filtros.append(Report.tipo == tipo)
        
        query = self.session.query(
            Localidad.nombre.label('localidad'),
            Calle.nombre.label('calle'),
            Report.tipo,
            func.count(Report.id).label('cantidad')
        ).join(
            Localidad, Report.localidad_id == Localidad.id
        ).join(
            Calle, Report.calle_id == Calle.id
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(*filtros).group_by(
            Report.localidad_id, Report.calle_id, Report.tipo
        ).order_by(
            func.count(Report.id).desc()
        ).limit(limite)
        
        resultados = query.all()
        
        focos = []
        for localidad, calle, tipo_reporte, cantidad in resultados:
            # Calcular gravedad
            if cantidad >= 20:
                gravedad = 'critica'
            elif cantidad >= 10:
                gravedad = 'alta'
            elif cantidad >= 5:
                gravedad = 'media'
            else:
                gravedad = 'baja'
            
            # Sugerir acción basada en tipo
            accion = self._sugerir_accion(tipo_reporte, cantidad)
            
            focos.append({
                'localidad': localidad,
                'calle': calle,
                'tipo': tipo_reporte,
                'reportes_pendientes': cantidad,
                'gravedad': gravedad,
                'accion_sugerida': accion,
                'ubicacion': f"{calle}, {localidad}"
            })
        
        return focos
    
    def _sugerir_accion(self, tipo, cantidad):
        """Sugiere acción basada en tipo y cantidad de reportes"""
        sugerencias = {
            'Agua Potable': {
                'critica': 'Renovar tubería principal',
                'alta': 'Reparación urgente de fuga',
                'media': 'Mantenimiento preventivo',
                'baja': 'Revisión programada'
            },
            'Alumbrado Público': {
                'critica': 'Renovar red eléctrica completa',
                'alta': 'Instalar nuevas luminarias',
                'media': 'Reparar postes dañados',
                'baja': 'Cambiar focos'
            },
            'Drenaje': {
                'critica': 'Cambio de tuberías',
                'alta': 'Limpieza profunda',
                'media': 'Destapar coladeras',
                'baja': 'Mantenimiento rutinario'
            },
            'Seguridad Pública': {
                'critica': 'Instalar comando policial',
                'alta': 'Aumentar patrullaje',
                'media': 'Colocar cámaras',
                'baja': 'Revisar alumbrado'
            }
        }
        
        # Determinar nivel
        if cantidad >= 20:
            nivel = 'critica'
        elif cantidad >= 10:
            nivel = 'alta'
        elif cantidad >= 5:
            nivel = 'media'
        else:
            nivel = 'baja'
        
        # Obtener sugerencia
        if tipo in sugerencias:
            return sugerencias[tipo][nivel]
        
        return f'Revisión de {tipo} ({nivel} prioridad)'
    
    def tendencias_mensuales(self, meses=6):
        """Obtiene tendencia de los últimos meses"""
        fecha_inicio = datetime.utcnow() - timedelta(days=meses*30)
        status_subquery = self._obtener_status_actual_subquery()
        
        # Consulta por mes
        query = self.session.query(
            func.strftime('%Y-%m', Report.timestamp).label('mes'),
            func.count(Report.id).label('total'),
            func.sum(
                case((status_subquery.c.status_id == self.FINALIZADO_STATUS_ID, 1), else_=0)
            ).label('atendidos')
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(
            Report.timestamp >= fecha_inicio
        ).group_by(
            func.strftime('%Y-%m', Report.timestamp)
        ).order_by('mes')
        
        tendencias = []
        for mes, total, atendidos in query.all():
            atendidos = atendidos or 0
            eficiencia = round((atendidos / total * 100), 1) if total > 0 else 0
            
            tendencias.append({
                'mes': mes,
                'total': total,
                'atendidos': atendidos,
                'eficiencia': eficiencia
            })
        
        return tendencias
    
    def detalle_por_departamento(self, tipo, dias=30):
        """Drill-down detallado por departamento"""
        fecha_limite = self._obtener_fecha_limite(dias)
        status_subquery = self._obtener_status_actual_subquery()
        
        # Obtener subtipos
        subtipos = self.session.query(
            Report.subtipo,
            func.count(Report.id).label('total'),
            func.sum(
                case((status_subquery.c.status_id == self.FINALIZADO_STATUS_ID, 1), else_=0)
            ).label('atendidos')
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(
            Report.tipo == tipo,
            Report.timestamp >= fecha_limite,
            Report.subtipo.isnot(None)
        ).group_by(Report.subtipo).all()
        
        # Obtener localidades
        localidades = self.session.query(
            Localidad.nombre,
            func.count(Report.id).label('total'),
            func.sum(
                case((status_subquery.c.status_id == self.FINALIZADO_STATUS_ID, 1), else_=0)
            ).label('atendidos')
        ).join(Report, Report.localidad_id == Localidad.id).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(
            Report.tipo == tipo,
            Report.timestamp >= fecha_limite
        ).group_by(Localidad.nombre).all()
        
        # Obtener calles con más reportes (solo pendientes)
        calles_pendientes = self.session.query(
            Calle.nombre,
            Localidad.nombre.label('localidad'),
            func.count(Report.id).label('total')
        ).join(Report, Report.calle_id == Calle.id).join(
            Localidad, Report.localidad_id == Localidad.id
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(
            Report.tipo == tipo,
            Report.timestamp >= fecha_limite,
            status_subquery.c.status_id != self.FINALIZADO_STATUS_ID  # Solo pendientes
        ).group_by(Calle.nombre, Localidad.nombre).order_by(
            func.count(Report.id).desc()
        ).limit(5).all()
        
        # Calcular tiempo promedio de atención (solo para finalizados)
        tiempo_promedio = self.session.query(
            func.avg(
                func.julianday(Assignment.timestamp) -
                func.julianday(Report.timestamp)
            )
        ).join(
            Assignment, Assignment.report_id == Report.id
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(
            Report.tipo == tipo,
            Report.timestamp >= fecha_limite,
            status_subquery.c.status_id == self.FINALIZADO_STATUS_ID
        ).scalar() or 0
        
        return {
            'subtipos': [
                {
                    'nombre': subtipo,
                    'total': total,
                    'atendidos': atendidos or 0,
                    'pendientes': total - (atendidos or 0)
                }
                for subtipo, total, atendidos in subtipos
            ],
            'localidades': [
                {
                    'nombre': localidad,
                    'total': total,
                    'atendidos': atendidos or 0
                }
                for localidad, total, atendidos in localidades
            ],
            'calles_criticas': [
                {
                    'calle': calle,
                    'localidad': localidad,
                    'reportes_pendientes': total
                }
                for calle, localidad, total in calles_pendientes
            ],
            'tiempo_promedio_atencion': round(tiempo_promedio * 24, 1),  # Convertir a horas
            'total_por_mes': self._obtener_total_por_mes(tipo, fecha_limite)
        }
    
    def _obtener_total_por_mes(self, tipo, fecha_limite):
        """Obtiene total de reportes por mes"""
        query = self.session.query(
            func.strftime('%Y-%m', Report.timestamp).label('mes'),
            func.count(Report.id).label('total')
        ).filter(
            Report.tipo == tipo,
            Report.timestamp >= fecha_limite
        ).group_by(
            func.strftime('%Y-%m', Report.timestamp)
        ).order_by('mes')
        
        return [{'mes': mes, 'total': total} for mes, total in query.all()]
    
    def obtener_reportes_detallados(self, dias=30, tipo=''):
        """Obtiene reportes para vista detallada"""
        fecha_limite = self._obtener_fecha_limite(dias)
        status_subquery = self._obtener_status_actual_subquery()
        cuadrilla_subquery = self._obtener_cuadrilla_actual_subquery()
        
        filtros = [Report.timestamp >= fecha_limite]
        
        if tipo:
            filtros.append(Report.tipo == tipo)
        
        query = self.session.query(
            Report.id,
            Report.timestamp,
            Report.tipo,
            Report.subtipo,
            Report.reportante,
            Report.telefono,
            Report.descripcion_problema,
            status_subquery.c.status_id,
            Localidad.nombre.label('localidad'),
            Calle.nombre.label('calle'),
            Report.numero,
            Team.nombre.label('cuadrilla')
        ).outerjoin(
            Localidad, Report.localidad_id == Localidad.id
        ).outerjoin(
            Calle, Report.calle_id == Calle.id
        ).outerjoin(
            status_subquery, Report.id == status_subquery.c.report_id
        ).outerjoin(
            cuadrilla_subquery, Report.id == cuadrilla_subquery.c.report_id
        ).outerjoin(
            Team, cuadrilla_subquery.c.team_id == Team.id
        ).filter(*filtros).order_by(
            Report.timestamp.desc()
        ).limit(100)
        
        reportes = []
        for row in query.all():
            reportes.append({
                'id': row.id,
                'fecha': row.timestamp.strftime('%Y-%m-%d %H:%M'),
                'tipo': row.tipo,
                'subtipo': row.subtipo,
                'reportante': row.reportante,
                'telefono': row.telefono,
                'descripcion': row.descripcion_problema[:100] + '...' if row.descripcion_problema and len(row.descripcion_problema) > 100 else row.descripcion_problema,
                'estado': 'Atendido' if row.status_id == self.FINALIZADO_STATUS_ID else 'Pendiente',
                'ubicacion': f"{row.calle or ''} {row.numero or ''}, {row.localidad or ''}",
                'cuadrilla': row.cuadrilla or 'Sin asignar'
            })
        
        return reportes
    
    def obtener_puntos_mapa(self, dias=30, tipo='', agrupar_por_departamento=False):
        """Obtiene puntos geolocalizados para el mapa"""
        fecha_limite = self._obtener_fecha_limite(dias)
        status_subquery = self._obtener_status_actual_subquery()
        
        filtros = [Report.timestamp >= fecha_limite]
        
        if tipo:
            filtros.append(Report.tipo == tipo)
        
        # Solo reportes con coordenadas
        filtros.append(Report.latitud.isnot(None))
        filtros.append(Report.longitud.isnot(None))
        
        # Consulta base con estado actual
        query = self.session.query(
            Report.id,
            Report.tipo,
            Report.subtipo,
            Report.latitud,
            Report.longitud,
            Report.timestamp,
            Localidad.nombre.label('localidad'),
            Calle.nombre.label('calle'),
            Report.numero,
            status_subquery.c.status_id
        ).join(
            Localidad, Report.localidad_id == Localidad.id
        ).join(
            Calle, Report.calle_id == Calle.id
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(*filtros)
        
        resultados = query.all()
        
        puntos = []
        for row in resultados:
            puntos.append({
                'id': row.id,
                'tipo': row.tipo,
                'subtipo': row.subtipo,
                'coordenadas': {
                    'lat': float(row.latitud) if row.latitud else 0,
                    'lng': float(row.longitud) if row.longitud else 0
                },
                'localidad': row.localidad,
                'calle': f"{row.calle} {row.numero}" if row.numero else row.calle,
                'estado': 'Atendido' if row.status_id == self.FINALIZADO_STATUS_ID else 'Pendiente',
                'fecha': row.timestamp.strftime('%Y-%m-%d')
            })
        
        # Estadísticas
        tipos_count = {}
        for punto in puntos:
            tipo = punto['tipo']
            tipos_count[tipo] = tipos_count.get(tipo, 0) + 1
        
        return {
            'puntos': puntos,
            'estadisticas': {
                'total': len(puntos),
                'tipos_distribucion': tipos_count,
                'atendidos': sum(1 for p in puntos if p['estado'] == 'Atendido'),
                'pendientes': sum(1 for p in puntos if p['estado'] == 'Pendiente')
            }
        }
    
    def obtener_estadisticas_departamentos(self, dias=30):
        """Obtiene estadísticas por departamento para el mapa"""
        fecha_limite = self._obtener_fecha_limite(dias)
        status_subquery = self._obtener_status_actual_subquery()
        
        query = self.session.query(
            Report.tipo,
            func.count(Report.id).label('total'),
            func.sum(
                case((status_subquery.c.status_id == self.FINALIZADO_STATUS_ID, 1), else_=0)
            ).label('atendidos')
        ).join(
            status_subquery, Report.id == status_subquery.c.report_id
        ).filter(
            Report.timestamp >= fecha_limite
        ).group_by(
            Report.tipo
        ).order_by(
            func.count(Report.id).desc()
        )
        
        departamentos = []
        for tipo, total, atendidos in query.all():
            atendidos = atendidos or 0
            pendientes = total - atendidos
            eficiencia = round((atendidos / total * 100), 1) if total > 0 else 0
            
            departamentos.append({
                'nombre': tipo,
                'total': total,
                'atendidos': atendidos,
                'pendientes': pendientes,
                'eficiencia': eficiencia,
                'color': self.COLORES_DEPARTAMENTOS.get(tipo, self.COLORES_DEPARTAMENTOS['default'])
            })
        
        return departamentos