# app/utils/permisos.py - VERSIÓN CORREGIDA
from datetime import datetime

def calcular_permisos_usuario(usuario):
    """
    Calcula permisos automáticamente según nivel y área
    COMPATIBLE con el modelo User actual
    """
    if not usuario:
        return {}
    
    # Inicializar permisos por defecto
    permisos = {
        'puede_asignar': False,
        'puede_validar': False,
        'puede_ver_todas_areas': False,
        'puede_configurar': False,
        'notificaciones': 'solo_asignados'
    }
    
    # Si no tiene nivel, usar role como fallback
    nivel = usuario.nivel if hasattr(usuario, 'nivel') else usuario.role if hasattr(usuario, 'role') else 'cuadrilla'
    area = usuario.area if hasattr(usuario, 'area') else None
    rol_especifico = usuario.rol_especifico if hasattr(usuario, 'rol_especifico') else None
    
    # ===== PRESIDENCIA =====
    if nivel == 'presidente' or area == 'presidencia':
        permisos.update({
            'puede_asignar': False,  # Solo observa
            'puede_validar': False,
            'puede_ver_todas_areas': True,
            'puede_configurar': False,
            'notificaciones': 'solo_urgentes_y_resumenes'
        })
    
    # ===== ADMINISTRADOR SISTEMA =====
    elif nivel == 'administrador' or usuario.is_admin():
        permisos.update({
            'puede_asignar': False,
            'puede_validar': False,
            'puede_ver_todas_areas': True,
            'puede_configurar': True,  # Solo administrador configura
            'notificaciones': 'solo_configuracion'
        })
    
    # ===== AGUA POTABLE (estructura compleja) =====
    elif area == 'agua':
        if nivel == 'director' or usuario.es_director():
            permisos.update({
                'puede_asignar': True,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'todos_reportes_agua_drenaje'
            })
        
        elif rol_especifico == 'jefe_area_tecnica':
            permisos.update({
                'puede_asignar': True,  # Asigna a cuadrillas técnicas
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'reportes_tecnicos_agua'
            })
        
        elif rol_especifico == 'jefe_area_comercial':
            permisos.update({
                'puede_asignar': False,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'reportes_comerciales_agua'  # Multas, pagos
            })
        
        elif nivel == 'supervisor' or usuario.es_supervisor():
            permisos.update({
                'puede_asignar': False,
                'puede_validar': True,  # Valida reparaciones
                'puede_ver_todas_areas': False,
                'notificaciones': 'reportes_para_validar_agua'
            })
        
        elif rol_especifico in ['vactor', 'pipa']:
            permisos.update({
                'puede_asignar': False,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'solo_asignados_especialidad'
            })
        
        elif nivel == 'cuadrilla' or usuario.es_cuadrilla():
            permisos.update({
                'puede_asignar': False,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'solo_asignados'
            })
    
    # ===== DRENAJE (misma estructura que agua) =====
    elif area == 'drenaje':
        if nivel == 'director' or usuario.es_director():
            permisos.update({
                'puede_asignar': True,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'todos_reportes_drenaje'
            })
        elif nivel == 'supervisor' or usuario.es_supervisor():
            permisos.update({
                'puede_asignar': False,
                'puede_validar': True,
                'puede_ver_todas_areas': False,
                'notificaciones': 'reportes_drenaje_validar'
            })
        else:
            permisos.update({
                'puede_asignar': False,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'solo_asignados'
            })
    
    # ===== ÁREAS SIMPLES (Parques, Ecología, Aseo, etc.) =====
    elif area in ['parques', 'ecologia', 'aseo', 'alumbrado', 'obra', 'seguridad']:
        if nivel == 'director' or usuario.es_director():
            permisos.update({
                'puede_asignar': True,  # Asigna directo
                'puede_validar': True,  # Valida también
                'puede_ver_todas_areas': False,
                'notificaciones': 'todos_reportes_area'
            })
        
        elif nivel == 'cuadrilla' or usuario.es_cuadrilla():
            permisos.update({
                'puede_asignar': False,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'solo_asignados'
            })
    
    # ===== BOMBEROS =====
    elif area == 'bomberos':
        if nivel == 'director' or usuario.es_director():
            permisos.update({
                'puede_asignar': True,
                'puede_validar': True,
                'puede_ver_todas_areas': False,
                'notificaciones': 'todos_reportes_bomberos'
            })
        
        elif rol_especifico == 'camion_bombero':
            permisos.update({
                'puede_asignar': False,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'solo_emergencias_bomberos'
            })
        
        elif nivel == 'cuadrilla' or usuario.es_cuadrilla():
            permisos.update({
                'puede_asignar': False,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'solo_asignados_bomberos'
            })
    
    # ===== POR DEFECTO (si no coincide con nada) =====
    else:
        if nivel == 'director' or usuario.es_director():
            permisos.update({
                'puede_asignar': True,
                'puede_validar': True,
                'puede_ver_todas_areas': False,
                'notificaciones': 'todos_reportes_area'
            })
        elif nivel == 'supervisor' or usuario.es_supervisor():
            permisos.update({
                'puede_asignar': False,
                'puede_validar': True,
                'puede_ver_todas_areas': False,
                'notificaciones': 'reportes_para_validar'
            })
        else:
            # Cuadrilla o cualquier otro
            permisos.update({
                'puede_asignar': False,
                'puede_validar': False,
                'puede_ver_todas_areas': False,
                'notificaciones': 'solo_asignados'
            })
    
    return permisos


def obtener_roles_por_area(area):
    """Devuelve los roles disponibles para un área específica"""
    roles_por_area = {
        'agua': [
            ('director', 'Director de Agua'),
            ('jefe_area_tecnica', 'Jefe Área Técnica'),
            ('jefe_area_comercial', 'Jefe Área Comercial'),
            ('supervisor', 'Supervisor Operativo'),
            ('vactor', 'Operador Vactor'),
            ('pipa', 'Operador Pipa'),
            ('cuadrilla', 'Cuadrilla Técnica'),
            ('cuadrilla', 'Cuadrilla General')
        ],
        'drenaje': [
            ('director', 'Director de Drenaje'),
            ('supervisor', 'Supervisor Drenaje'),
            ('vactor', 'Operador Vactor'),
            ('cuadrilla', 'Cuadrilla Drenaje')
        ],
        'parques': [
            ('director', 'Director de Parques'),
            ('supervisor', 'Supervisor Parques'),
            ('cuadrilla', 'Cuadrilla Parques')
        ],
        'ecologia': [
            ('director', 'Director de Ecología'),
            ('supervisor', 'Supervisor Ecología'),
            ('cuadrilla', 'Cuadrilla Ecología')
        ],
        'aseo': [
            ('director', 'Director de Aseo'),
            ('supervisor', 'Supervisor Aseo'),
            ('cuadrilla', 'Cuadrilla Aseo')
        ],
        'alumbrado': [
            ('director', 'Director de Alumbrado'),
            ('supervisor', 'Supervisor Alumbrado'),
            ('cuadrilla', 'Cuadrilla Alumbrado')
        ],
        'obra': [
            ('director', 'Director de Obras'),
            ('supervisor', 'Supervisor Obras'),
            ('cuadrilla', 'Cuadrilla Obras')
        ],
        'seguridad': [
            ('director', 'Director de Seguridad'),
            ('supervisor', 'Supervisor Seguridad'),
            ('cuadrilla', 'Cuadrilla Seguridad')
        ],
        'bomberos': [
            ('director', 'Director de Bomberos'),
            ('supervisor', 'Supervisor Bomberos'),
            ('camion_bombero', 'Camión Bombero'),
            ('cuadrilla', 'Bombero')
        ],
        'presidencia': [
            ('presidente', 'Presidente Municipal'),
            ('administrador', 'Administrador Sistema')
        ]
    }
    
    return roles_por_area.get(area, [('cuadrilla', 'Personal')])


def puede_asignar_reporte(usuario, reporte):
    """Verifica si un usuario puede asignar un reporte específico"""
    if not usuario:
        return False
    
    # Usar el permiso calculado
    permisos = calcular_permisos_usuario(usuario)
    if not permisos.get('puede_asignar', False):
        return False
    
    # Verificar área
    if usuario.area and reporte.tipo:
        # Mapeo de tipo de reporte a área
        tipo_a_area = {
            'Agua potable': 'agua',
            'Drenaje': 'drenaje',
            'Aseo público': 'aseo',
            'Alumbrado público': 'alumbrado',
            'Parques y jardines': 'parques',
            'Ecología': 'ecologia',
            'Seguridad pública': 'seguridad',
            'Obras públicas': 'obra',
            'Bomberos': 'bomberos'
        }
        
        area_reporte = tipo_a_area.get(reporte.tipo)
        if area_reporte and area_reporte != usuario.area:
            return False
    
    # Verificaciones adicionales por rol específico (Agua)
    if usuario.area == 'agua' and usuario.rol_especifico == 'jefe_area_tecnica':
        # Jefe técnico solo asigna reportes técnicos de agua
        subtipos_tecnicos = ['Fuga en línea principal', 'Toma tapada', 'Válvula dañada', 
                            'Línea tapada', 'Socavón por fuga', 'Reparación de empedrado']
        return reporte.subtipo in subtipos_tecnicos
    
    # Verificaciones adicionales por rol específico (Jefe comercial)
    if usuario.area == 'agua' and usuario.rol_especifico == 'jefe_area_comercial':
        # Jefe comercial NO asigna (solo ve reportes comerciales)
        return False
    
    return True