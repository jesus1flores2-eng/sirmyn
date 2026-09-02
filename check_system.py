"""
Script de diagnóstico SIRMYN - Versión 3.0
Auto-detecta modelos y tablas correctamente
Ejecutar: python check_system.py
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

print("=" * 60)
print("🔍 DIAGNÓSTICO SIRMYN - VERSIÓN 3.0")
print("=" * 60)
print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Importar la app
try:
    from app import create_app, db
    print("\n✅ App importada correctamente")
except Exception as e:
    print(f"\n❌ Error importando app: {e}")
    sys.exit(1)

# Crear app
try:
    app = create_app()
    print("✅ App creada con factory pattern")
except Exception as e:
    print(f"❌ Error creando app: {e}")
    sys.exit(1)

# ============ FUNCIONES DE VERIFICACIÓN ============

def get_table_names():
    """Obtener nombres de tablas de la base de datos"""
    try:
        with app.app_context():
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            return tables
    except Exception as e:
        print(f"❌ Error obteniendo tablas: {e}")
        return []

def get_model_class(table_name):
    """Intentar obtener la clase del modelo para una tabla"""
    try:
        # Intentar diferentes convenciones de nombres
        possible_names = [
            table_name.capitalize(),  # usuarios -> Usuarios
            table_name[:-1].capitalize() if table_name.endswith('s') else table_name.capitalize(),  # usuarios -> Usuario
            table_name,  # nombre tal cual
            table_name.upper(),  # USUARIOS
        ]
        
        # Buscar en app.models
        import app.models as models_package
        
        # Obtener todas las clases del paquete
        for name in dir(models_package):
            obj = getattr(models_package, name)
            if isinstance(obj, type) and hasattr(obj, '__table__'):
                if obj.__table__.name == table_name:
                    return obj
        
        # Si no encontramos, intentar con db.Model
        for name in possible_names:
            if hasattr(models_package, name):
                obj = getattr(models_package, name)
                if isinstance(obj, type) and hasattr(obj, '__table__'):
                    if obj.__table__.name == table_name:
                        return obj
        
        return None
    except Exception as e:
        print(f"⚠️  Error buscando modelo para {table_name}: {e}")
        return None

def execute_raw_query(query, params=None):
    """Ejecutar query SQL directamente"""
    try:
        with app.app_context():
            result = db.session.execute(query, params or {})
            return result.fetchall()
    except Exception as e:
        print(f"❌ Error en query: {e}")
        return []

def verify_bot_tokens():
    """Pendiente 1: Verificar bot_tokens de municipios"""
    print("\n" + "=" * 60)
    print("🤖 PENDIENTE 1: VERIFICANDO BOT TOKENS")
    print("=" * 60)
    
    # Buscar tablas relacionadas con municipios
    tables = get_table_names()
    municipio_tables = [t for t in tables if 'municipio' in t.lower()]
    
    if not municipio_tables:
        print("❌ No se encontró tabla de municipios")
        return False
    
    print(f"📊 Tablas de municipios encontradas: {municipio_tables}")
    
    # Usar la primera tabla de municipios
    municipio_table = municipio_tables[0]
    
    # Query para obtener tokens
    from sqlalchemy import text
    query = text(f"""
        SELECT id, nombre, bot_token, 
               LENGTH(bot_token) as token_length 
        FROM {municipio_table} 
        ORDER BY nombre
    """)
    
    results = execute_raw_query(query)
    
    if not results:
        print("⚠️  No hay municipios registrados")
        return True
    
    con_token = 0
    sin_token = 0
    
    for row in results:
        id_muni, nombre, token, token_length = row
        
        if token and token_length > 30:
            print(f"✅ {nombre} (ID:{id_muni}): Token OK ({token_length} caracteres)")
            print(f"   Inicio: {token[:20]}...")
            con_token += 1
        elif token:
            print(f"⚠️  {nombre} (ID:{id_muni}): Token corto ({token_length} caracteres)")
            con_token += 1
        else:
            print(f"❌ {nombre} (ID:{id_muni}): SIN TOKEN")
            sin_token += 1
    
    print(f"\n📊 Resumen: {con_token} con token, {sin_token} sin token")
    
    if sin_token > 0:
        print("⚠️  Municipios que necesitan token:")
        for row in results:
            id_muni, nombre, token, token_length = row
            if not token:
                print(f"   - {nombre} (ID:{id_muni})")
    
    return sin_token == 0

def verify_bots_configuration():
    """Pendiente 2: Verificar configuración de bots"""
    print("\n" + "=" * 60)
    print("🔧 PENDIENTE 2: CONFIGURACIÓN DE BOTS")
    print("=" * 60)
    
    webhook_url = os.getenv('WEBHOOK_URL') or os.getenv('RENDER_EXTERNAL_URL')
    
    if webhook_url:
        print(f"✅ Webhook URL: {webhook_url}")
    else:
        print("⚠️  No hay WEBHOOK_URL configurada")
        print("   Para ngrok: configura WEBHOOK_URL con tu URL de ngrok")
        print("   Para Render: se configurará automáticamente")
    
    # Verificar tokens de municipios
    tables = get_table_names()
    municipio_tables = [t for t in tables if 'municipio' in t.lower()]
    
    if municipio_tables:
        from sqlalchemy import text
        query = text(f"""
            SELECT nombre, bot_token 
            FROM {municipio_tables[0]} 
            WHERE bot_token IS NOT NULL
        """)
        
        results = execute_raw_query(query)
        
        for nombre, token in results:
            # Verificar formato del token
            token_parts = token.split(':')
            if len(token_parts) == 2:
                print(f"✅ {nombre}: Token con formato correcto")
            else:
                print(f"⚠️  {nombre}: Token con formato inusual")
    
    return True

def verify_report_history():
    """Pendiente 3: Verificar historial de reportes"""
    print("\n" + "=" * 60)
    print("📝 PENDIENTE 3: HISTORIAL DE REPORTES")
    print("=" * 60)
    
    tables = get_table_names()
    
    # Buscar tablas de reportes e historial
    reporte_tables = [t for t in tables if 'report' in t.lower() or 'reporte' in t.lower()]
    historial_tables = [t for t in tables if 'historial' in t.lower() or 'history' in t.lower()]
    
    print(f"📊 Tablas de reportes: {reporte_tables}")
    print(f"📊 Tablas de historial: {historial_tables}")
    
    if not reporte_tables:
        print("❌ No se encontró tabla de reportes")
        return False
    
    # Usar la tabla principal de reportes
    reporte_table = reporte_tables[0]
    historial_table = historial_tables[0] if historial_tables else None
    
    from sqlalchemy import text
    
    # Obtener últimos 5 reportes
    query = text(f"""
        SELECT id, tipo_reporte, fecha_creacion 
        FROM {reporte_table} 
        ORDER BY fecha_creacion DESC 
        LIMIT 5
    """)
    
    reportes = execute_raw_query(query)
    
    if not reportes:
        print("⚠️  No hay reportes para verificar")
        return True
    
    reportes_ok = 0
    reportes_fallidos = 0
    
    for rep_id, tipo, fecha in reportes:
        print(f"\n📋 Reporte #{rep_id} - {tipo}")
        
        if historial_table:
            # Buscar historial del reporte
            query_hist = text(f"""
                SELECT observacion, fecha_creacion 
                FROM {historial_table} 
                WHERE reporte_id = :rep_id 
                ORDER BY fecha_creacion 
                LIMIT 1
            """)
            
            historial = execute_raw_query(query_hist, {"rep_id": rep_id})
            
            if historial:
                primera_obs = historial[0][0] if historial[0][0] else ""
                
                if "Reporte creado" in primera_obs or "ciudadano" in primera_obs.lower():
                    print(f"   ✅ Observación inicial correcta")
                    print(f"   '{primera_obs}'")
                    reportes_ok += 1
                else:
                    print(f"   ❌ Observación inicial incorrecta")
                    print(f"   '{primera_obs}'")
                    reportes_fallidos += 1
            else:
                print(f"   ❌ Sin historial")
                reportes_fallidos += 1
        else:
            print(f"   ⚠️  No se encontró tabla de historial")
            reportes_fallidos += 1
    
    print(f"\n📊 Resumen: {reportes_ok} OK, {reportes_fallidos} con problemas")
    return reportes_fallidos == 0

def verify_notifications_links():
    """Pendiente 4: Verificar enlaces en notificaciones"""
    print("\n" + "=" * 60)
    print("🔗 PENDIENTE 4: ENLACES EN NOTIFICACIONES")
    print("=" * 60)
    
    tables = get_table_names()
    reporte_tables = [t for t in tables if 'report' in t.lower() or 'reporte' in t.lower()]
    
    if not reporte_tables:
        print("❌ No se encontró tabla de reportes")
        return False
    
    reporte_table = reporte_tables[0]
    
    from sqlalchemy import text
    
    # Buscar reportes con evidencia
    query_evidencia = text(f"""
        SELECT id, evidencia 
        FROM {reporte_table} 
        WHERE evidencia IS NOT NULL AND evidencia != '' 
        LIMIT 3
    """)
    
    reportes_evidencia = execute_raw_query(query_evidencia)
    
    if reportes_evidencia:
        print("📎 Reportes con evidencia:")
        for rep_id, evidencia in reportes_evidencia:
            if evidencia.startswith('http'):
                print(f"✅ Reporte #{rep_id}: URL válida")
            else:
                print(f"⚠️  Reporte #{rep_id}: Evidencia no es URL")
                print(f"   Valor: {evidencia[:50]}")
    else:
        print("ℹ️  No hay reportes con evidencia")
    
    # Buscar reportes con coordenadas
    query_coords = text(f"""
        SELECT id, latitud, longitud 
        FROM {reporte_table} 
        WHERE latitud IS NOT NULL AND longitud IS NOT NULL 
        LIMIT 3
    """)
    
    reportes_coords = execute_raw_query(query_coords)
    
    if reportes_coords:
        print("\n🗺️  Reportes con mapa:")
        for rep_id, lat, lon in reportes_coords:
            map_url = f"https://maps.google.com/?q={lat},{lon}"
            print(f"✅ Reporte #{rep_id}: {map_url}")
    else:
        print("\nℹ️  No hay reportes con coordenadas")
    
    return True

def verify_map_editing():
    """Pendiente 5: Verificar edición de mapa"""
    print("\n" + "=" * 60)
    print("🗺️  PENDIENTE 5: EDICIÓN DE MAPA")
    print("=" * 60)
    
    # Buscar templates con mapas
    templates_found = []
    
    # Buscar en diferentes ubicaciones
    template_dirs = ['app/templates', 'templates']
    
    for template_dir in template_dirs:
        if os.path.exists(template_dir):
            for root, dirs, files in os.walk(template_dir):
                for file in files:
                    if file.endswith('.html'):
                        filepath = os.path.join(root, file)
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                            if any(lib in content.lower() for lib in ['leaflet', 'mapbox', 'google.maps', 'openlayers']):
                                templates_found.append(filepath)
                                
                                # Verificar si hay edición
                                editable = any(term in content.lower() for term in ['editable', 'draggable', 'onclick'])
                                if editable:
                                    print(f"✅ {filepath}: Mapa con edición")
                                else:
                                    print(f"⚠️  {filepath}: Mapa sin edición aparente")
    
    if not templates_found:
        print("⚠️  No se encontraron templates con mapas")
        print("   Buscar Leaflet/Mapbox en los templates HTML")
    else:
        print(f"\n📊 Total de templates con mapas: {len(templates_found)}")
    
    return True

def verify_user_import_export():
    """Pendiente 6: Verificar import/export de usuarios"""
    print("\n" + "=" * 60)
    print("👥 PENDIENTE 6: IMPORT/EXPORT DE USUARIOS")
    print("=" * 60)
    
    tables = get_table_names()
    
    # Buscar tabla de usuarios
    user_tables = [t for t in tables if 'user' in t.lower() or 'usuario' in t.lower()]
    
    if not user_tables:
        print("❌ No se encontró tabla de usuarios")
        return False
    
    user_table = user_tables[0]
    print(f"📊 Tabla de usuarios: {user_table}")
    
    from sqlalchemy import text
    
    # Contar usuarios
    query_count = text(f"SELECT COUNT(*) FROM {user_table}")
    result = execute_raw_query(query_count)
    
    if result:
        total_usuarios = result[0][0]
        print(f"✅ Total usuarios: {total_usuarios}")
    
    # Usuarios por municipio
    municipio_tables = [t for t in tables if 'municipio' in t.lower()]
    
    if municipio_tables:
        query_muni = text(f"""
            SELECT m.nombre, COUNT(u.id) 
            FROM {municipio_tables[0]} m 
            LEFT JOIN {user_table} u ON u.municipio_id = m.id 
            GROUP BY m.id, m.nombre 
            ORDER BY m.nombre
        """)
        
        result_muni = execute_raw_query(query_muni)
        
        for nombre, num_usuarios in result_muni:
            print(f"   {nombre}: {num_usuarios} usuarios")
    
    # Verificar funciones de import/export
    import_export_files = []
    for root, dirs, files in os.walk('app'):
        for file in files:
            if file.endswith('.py') and 'check_system' not in file:
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if ('import' in content.lower() and 'export' in content.lower() and
                        ('csv' in content.lower() or 'excel' in content.lower() or 'xlsx' in content.lower())):
                        import_export_files.append(filepath)
    
    if import_export_files:
        print("\n✅ Funciones de import/export encontradas:")
        for filepath in import_export_files:
            print(f"   📄 {filepath}")
    else:
        print("\n⚠️  No se encontraron funciones de import/export")
    
    return True

def verify_municipio_isolation():
    """Pendiente 7: Verificar aislamiento de datos"""
    print("\n" + "=" * 60)
    print("🔒 PENDIENTE 7: AISLAMIENTO DE DATOS")
    print("=" * 60)
    
    tables = get_table_names()
    
    municipio_tables = [t for t in tables if 'municipio' in t.lower()]
    reporte_tables = [t for t in tables if 'report' in t.lower() or 'reporte' in t.lower()]
    user_tables = [t for t in tables if 'user' in t.lower() or 'usuario' in t.lower()]
    
    if not municipio_tables or not reporte_tables:
        print("❌ No se encontraron tablas necesarias")
        return False
    
    municipio_table = municipio_tables[0]
    reporte_table = reporte_tables[0]
    user_table = user_tables[0] if user_tables else None
    
    from sqlalchemy import text
    
    # Reportes por municipio
    query = text(f"""
        SELECT m.nombre, 
               COUNT(r.id) as num_reportes
        FROM {municipio_table} m 
        LEFT JOIN {reporte_table} r ON r.municipio_id = m.id 
        GROUP BY m.id, m.nombre 
        ORDER BY m.nombre
    """)
    
    results = execute_raw_query(query)
    
    total_asignados = 0
    print("📊 Reportes por municipio:")
    for nombre, num_reportes in results:
        print(f"✅ {nombre}: {num_reportes} reportes")
        total_asignados += num_reportes
    
    # Reportes sin municipio
    query_huerfanos = text(f"SELECT COUNT(*) FROM {reporte_table} WHERE municipio_id IS NULL")
    result_huerfanos = execute_raw_query(query_huerfanos)
    
    huerfanos = result_huerfanos[0][0] if result_huerfanos else 0
    
    # Total reportes
    query_total = text(f"SELECT COUNT(*) FROM {reporte_table}")
    result_total = execute_raw_query(query_total)
    
    total_reportes = result_total[0][0] if result_total else 0
    
    print(f"\n📊 Resumen:")
    print(f"   Total reportes: {total_reportes}")
    print(f"   Asignados: {total_asignados}")
    print(f"   Sin asignar: {huerfanos}")
    
    if huerfanos > 0:
        print(f"⚠️  {huerfanos} reportes sin municipio")
        
        # Mostrar reportes sin municipio
        query_huerfanos_detalle = text(f"""
            SELECT id, tipo_reporte 
            FROM {reporte_table} 
            WHERE municipio_id IS NULL 
            LIMIT 5
        """)
        
        huerfanos_detalle = execute_raw_query(query_huerfanos_detalle)
        
        for rep_id, tipo in huerfanos_detalle:
            print(f"   - Reporte #{rep_id}: {tipo}")
        
        return False
    else:
        print("✅ Todos los reportes están asignados")
        return True

def verify_render_deployment():
    """Pendiente 8: Verificar configuración Render"""
    print("\n" + "=" * 60)
    print("🚀 PENDIENTE 8: CONFIGURACIÓN RENDER")
    print("=" * 60)
    
    # Archivos necesarios
    print("\n📁 Archivos necesarios:")
    required_files = {
        'requirements.txt': 'Dependencias Python',
        'render.yaml': 'Configuración Render',
        'Procfile': 'Comando de inicio',
        '.env': 'Variables de entorno'
    }
    
    for file, desc in required_files.items():
        if os.path.exists(file):
            size = os.path.getsize(file)
            print(f"✅ {file}: Presente ({size} bytes) - {desc}")
        else:
            print(f"⚠️  {file}: No encontrado - {desc}")
    
    # Verificar requirements.txt
    print("\n📦 Dependencias en requirements.txt:")
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            requirements = f.read().lower()
        
        required_packages = [
            'flask', 'sqlalchemy', 'telegram', 'supabase', 
            'psycopg2', 'gunicorn', 'python-dotenv', 'pillow'
        ]
        
        for package in required_packages:
            if package in requirements:
                print(f"✅ {package}")
            else:
                print(f"⚠️  {package}: NO encontrado")
    
    # Verificar variables de entorno
    print("\n🔐 Variables de entorno:")
    required_env = [
        'DATABASE_URL', 'SECRET_KEY', 'TELEGRAM_BOT_TOKEN',
        'SUPABASE_URL', 'SUPABASE_KEY'
    ]
    
    for env_var in required_env:
        value = os.getenv(env_var)
        if value:
            if any(sensitive in env_var.upper() for sensitive in ['TOKEN', 'KEY', 'SECRET', 'PASSWORD']):
                print(f"✅ {env_var}: Configurada (oculta por seguridad)")
            else:
                print(f"✅ {env_var}: {value[:30]}...")
        else:
            print(f"⚠️  {env_var}: No configurada")
    
    # Verificar render.yaml
    print("\n🔧 Configuración Render:")
    if os.path.exists('render.yaml'):
        with open('render.yaml', 'r') as f:
            render_config = f.read()
            
            if 'startCommand' in render_config or 'start' in render_config:
                print("✅ Comando de inicio configurado")
            else:
                print("⚠️  No se encontró comando de inicio")
            
            if 'python' in render_config:
                print("✅ Runtime Python configurado")
            else:
                print("⚠️  Runtime Python no especificado")
    else:
        print("❌ render.yaml no encontrado")
    
    return True

# ============ EJECUTAR VERIFICACIONES ============
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🚀 INICIANDO VERIFICACIONES...")
    print("=" * 60)
    
    # Obtener tablas primero
    tables = get_table_names()
    print(f"\n📊 Tablas en la base de datos:")
    for table in tables:
        print(f"   - {table}")
    
    # Ejecutar verificaciones
    resultados = {
        "1. Bot Tokens": verify_bot_tokens(),
        "2. Configuración Bots": verify_bots_configuration(),
        "3. Historial de Reportes": verify_report_history(),
        "4. Enlaces en Notificaciones": verify_notifications_links(),
        "5. Edición de Mapa": verify_map_editing(),
        "6. Import/Export Usuarios": verify_user_import_export(),
        "7. Aislamiento de Datos": verify_municipio_isolation(),
        "8. Configuración Render": verify_render_deployment()
    }
    
    # Mostrar resumen final
    print("\n" + "=" * 60)
    print("📋 RESUMEN FINAL")
    print("=" * 60)
    
    ok = 0
    warnings = 0
    
    for nombre, resultado in resultados.items():
        if resultado:
            print(f"✅ {nombre}: OK")
            ok += 1
        else:
            print(f"⚠️  {nombre}: Requiere atención")
            warnings += 1
    
    print(f"\n📊 Resultados: {ok} OK, {warnings} requieren atención")
    
    if warnings == 0:
        print("\n🎉 ¡Sistema listo para producción!")
    else:
        print("\n📝 Acciones necesarias:")
        if not resultados["1. Bot Tokens"]:
            print("   ❌ Configurar tokens faltantes en municipios")
        if not resultados["3. Historial de Reportes"]:
            print("   ❌ Corregir observación inicial en historial")
        if not resultados["7. Aislamiento de Datos"]:
            print("   ❌ Asignar municipio a reportes huérfanos")
        print("   ⚠️  Completar configuración de Render")
        print("   ⚠️  Probar bots de Chapala y Jocotepec")
    
    print("\n✅ Diagnóstico completado")
