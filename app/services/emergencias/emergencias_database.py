import json
import logging
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger(__name__)

async def generar_folio_emergencia(db_session):
    """
    Genera un folio único para emergencias en formato E-YYYY-XXXXX
    """
    try:
        # Obtener el último folio de emergencia
        query = text("""
            SELECT folio_publico FROM emergencies 
            WHERE folio_publico LIKE 'E-%-%' 
            ORDER BY id DESC LIMIT 1
        """)
        
        result = await db_session.execute(query)
        last_folio = result.scalar()
        
        year = datetime.now().year
        
        if last_folio:
            try:
                # Extraer el número del último folio
                parts = last_folio.split('-')
                if len(parts) == 3 and parts[0] == 'E' and parts[1] == str(year):
                    last_num = int(parts[2])
                    new_num = last_num + 1
                else:
                    new_num = 1
            except:
                new_num = 1
        else:
            new_num = 1
        
        # Formatear con 5 dígitos
        folio = f"E-{year}-{new_num:05d}"
        return folio
        
    except Exception as e:
        logger.error(f"Error generando folio: {e}")
        # Folio de respaldo
        return f"E-{year}-{int(datetime.now().timestamp()) % 100000:05d}"

async def guardar_emergencia_en_db(datos_emergencia, db_session):
    """
    Guarda una emergencia en la base de datos principal.
    Ahora guarda en TRES tablas: reports, emergencies y asignaciones.
    """
    try:
        # Generar folio si no viene
        folio = datos_emergencia.get('folio_publico')
        if not folio:
            folio = await generar_folio_emergencia(db_session)
            datos_emergencia['folio_publico'] = folio
        
        # Determinar nivel de urgencia automáticamente
        nivel_urgencia = 1  # Siempre máximo para emergencias
        
        # PASO 1: GUARDAR EN REPORTS (para el dashboard)
        query_reports = text("""
            INSERT INTO reports (
                reportante, tipo, subtipo, entre_calles,
                descripcion_problema, timestamp, plataforma,
                latitud, longitud, localidad_id,
                es_emergencia, nivel_urgencia,
                telefono, numero, evidencia, numero_cuenta, calle_id
            ) VALUES (
                :reportante, :tipo, :subtipo, :direccion_aproximada,
                :descripcion, CURRENT_TIMESTAMP, :plataforma,
                :latitud, :longitud, :localidad_id,
                1, :nivel_urgencia,
                '', '', '', '', NULL
            )
        """)
        
        params_reports = {
            'reportante': datos_emergencia.get('reportante'),
            'tipo': datos_emergencia.get('tipo'),
            'subtipo': datos_emergencia.get('subtipo', ''),
            'direccion_aproximada': datos_emergencia.get('direccion_aproximada', ''),
            'descripcion': datos_emergencia.get('descripcion', ''),
            'plataforma': datos_emergencia.get('plataforma', 'telegram'),
            'latitud': datos_emergencia.get('latitud'),
            'longitud': datos_emergencia.get('longitud'),
            'localidad_id': datos_emergencia.get('localidad_id', 1),
            'nivel_urgencia': nivel_urgencia
        }
        
        # Ejecutar inserción en reports
        result = await db_session.execute(query_reports, params_reports)
        await db_session.commit()
        
        # Obtener el ID del reporte recién insertado
        report_id = result.lastrowid
        
        # PASO 2: GUARDAR EN EMERGENCIES (datos específicos)
        query_emergencies = text("""
            INSERT INTO emergencies (
                report_id, municipio_id, municipio_nombre, tipo, subtipo,
                latitud, longitud, direccion_aproximada,
                reportante, telegram_user_id, telegram_username,
                descripcion, nivel_urgencia, status, folio_publico,
                personas_heridas, personas_atrapadas, peligro_vida,
                unidades_asignadas, tiempo_respuesta_estimado,
                tiempo_respuesta_real, contacto_adicional,
                plataforma, timestamp_reporte
            ) VALUES (
                :report_id, :municipio_id, :municipio_nombre, :tipo, :subtipo,
                :latitud, :longitud, :direccion_aproximada,
                :reportante, :telegram_user_id, :telegram_username,
                :descripcion, :nivel_urgencia, :status, :folio_publico,
                :personas_heridas, :personas_atrapadas, :peligro_vida,
                :unidades_asignadas, :tiempo_respuesta_estimado,
                :tiempo_respuesta_real, :contacto_adicional,
                :plataforma, CURRENT_TIMESTAMP
            )
        """)
        
        # Determinar valores automáticamente basados en tipo de emergencia
        tipo_emergencia = datos_emergencia.get('tipo', '').lower()
        
        # Inferir campos según tipo
        personas_heridas = datos_emergencia.get('personas_heridas', False)
        personas_atrapadas = datos_emergencia.get('personas_atrapadas', False)
        peligro_vida = datos_emergencia.get('peligro_vida', False)
        
        # Si no se especifican, inferir del tipo
        if not datos_emergencia.get('personas_heridas'):
            if 'ambulancia' in tipo_emergencia or 'medic' in tipo_emergencia:
                personas_heridas = True
                
        if not datos_emergencia.get('peligro_vida'):
            if 'bomberos' in tipo_emergencia or 'incendio' in tipo_emergencia or 'fuego' in tipo_emergencia:
                peligro_vida = True
        
        params_emergencies = {
            'report_id': report_id,
            'municipio_id': datos_emergencia.get('municipio_id', 1),
            'municipio_nombre': datos_emergencia.get('municipio_nombre', 'Nombre de tu Municipio'),
            'tipo': tipo_emergencia,
            'subtipo': datos_emergencia.get('subtipo', ''),
            'latitud': datos_emergencia.get('latitud'),
            'longitud': datos_emergencia.get('longitud'),
            'direccion_aproximada': datos_emergencia.get('direccion_aproximada', ''),
            'reportante': datos_emergencia.get('reportante', ''),
            'telegram_user_id': datos_emergencia.get('telegram_user_id'),
            'telegram_username': datos_emergencia.get('telegram_username'),
            'descripcion': datos_emergencia.get('descripcion', ''),
            'nivel_urgencia': nivel_urgencia,
            'status': datos_emergencia.get('status', 'reportada'),
            'folio_publico': folio,
            'personas_heridas': personas_heridas,
            'personas_atrapadas': personas_atrapadas,
            'peligro_vida': peligro_vida,
            'unidades_asignadas': json.dumps(datos_emergencia.get('unidades_asignadas', [])),
            'tiempo_respuesta_estimado': datos_emergencia.get('tiempo_respuesta_estimado'),
            'tiempo_respuesta_real': datos_emergencia.get('tiempo_respuesta_real'),
            'contacto_adicional': datos_emergencia.get('contacto_adicional', ''),
            'plataforma': datos_emergencia.get('plataforma', 'telegram')
        }
        
        await db_session.execute(query_emergencies, params_emergencies)
        
        # PASO 3: CREAR ASIGNACIÓN INICIAL
        query_asignaciones = text("""
            INSERT INTO asignaciones (
                report_id, team_id, status_id, timestamp,
                materiales_utilizados, observaciones,
                evidencia_cuadrilla, motivo_reasignacion
            ) VALUES (
                :report_id, :team_id, :status_id, CURRENT_TIMESTAMP,
                '', 'Emergencia reportada. Pendiente de asignación por director.',
                '', ''
            )
        """)
        
        params_asignaciones = {
            'report_id': report_id,
            'team_id': 1,  # 1 = "Sin asignar" (ID de tu equipo "Sin asignar")
            'status_id': 14  # 14 = "Emergencia Reportada"
        }
        
        await db_session.execute(query_asignaciones, params_asignaciones)
        
        await db_session.commit()
        
        logger.info(f"✅ Emergencia guardada exitosamente. Report ID: {report_id}, Folio: {folio}")
        
        return {
            'success': True,
            'report_id': report_id,
            'folio_publico': folio,
            'message': 'Emergencia registrada correctamente'
        }
        
    except Exception as e:
        await db_session.rollback()
        logger.error(f"❌ Error guardando emergencia en BD: {e}")
        return {
            'success': False,
            'error': str(e)
        }