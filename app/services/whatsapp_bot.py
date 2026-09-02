# app/services/whatsapp_bot.py

import os
import re
import uuid
import unicodedata
import difflib
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

from app.extensions import db
from app.models.report import Report, Assignment, Localidad, Calle
from app.models.team import Team
from app.models.status import Status
from app.models.user import User

load_dotenv()

TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
OPERADOR_NUMERO = os.getenv("OPERADOR_NUMERO")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "instance/uploads")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Estado en memoria (session-server)
estados = {}
ULTIMA_INTERACCION = {}
ULTIMO_MENSAJE = {}

FRASES_FINALIZACION = ["gracias", "muchas gracias"]

# Config de sugerencias
SUG_LIMIT = 6        # cuántas sugerencias mostrar
SUG_MIN_RATIO = 0.6  # umbral mínimo de similitud (0..1)

# ---------------------------
# Utilidades
# ---------------------------

def normalizar_numero(mensaje):
    return "".join(re.findall(r"\d+", mensaje))

def get_saludo():
    h = datetime.now().hour
    return "Buenos días" if h < 12 else "Buenas tardes" if h < 19 else "Buenas noches"

def limpiar_estado(telefono):
    estados.pop(telefono, None)
    ULTIMA_INTERACCION.pop(telefono, None)
    ULTIMO_MENSAJE.pop(telefono, None)

def _normalize_text(s: str) -> str:
    """Quita acentos, símbolos, espacios extra y pasa a minúsculas."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9\s]", " ", s).lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _rank_suggestions(input_text: str, candidates: list[tuple[int, str]], top=SUG_LIMIT, min_ratio=SUG_MIN_RATIO):
    """
    candidates: lista [(id, nombre), ...]
    Retorna lista de dicts: [{"id": ..., "nombre": ..., "score": 0..1}, ...]
    """
    q = _normalize_text(input_text)
    scored = []
    for cid, name in candidates:
        nname = _normalize_text(name)
        if not nname:
            continue
        score = difflib.SequenceMatcher(a=q, b=nname).ratio()
        if score >= min_ratio:
            scored.append({"id": cid, "nombre": name, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top]

def _msg_sugerencias(titulo: str, sugerencias: list[dict]) -> str:
    if not sugerencias:
        return f"No encontré coincidencias claras. Escribe de nuevo el {titulo} (al menos 3 letras) o responde 'cancelar'."
    cuerpo = "\n".join([f"{i+1}. {s['nombre']}" for i, s in enumerate(sugerencias)])
    return f"¿Te refieres a estas opciones de {titulo}?\n{cuerpo}\n\nResponde con el número (1-{len(sugerencias)}) o escribe otra vez."

def manejar_escalamiento(telefono, mensaje):
    try:
        twilio_client.messages.create(
            from_=TWILIO_PHONE_NUMBER,
            to=OPERADOR_NUMERO,
            body=f"📣 Usuario {telefono} solicitó ayuda:\n{mensaje}"
        )
    except Exception as e:
        print(f"⚠️ Error enviando a operador: {e}")
    return f"🤖 Un asesor te atenderá pronto.\n📞 Contacto: {OPERADOR_NUMERO.replace('whatsapp:', '')}"

# ---------------------------
# Lógica principal del bot
# ---------------------------

def manejar_mensaje_whatsapp(telefono, mensaje, media_url, media_type=""):
    now = datetime.now()
    resp = MessagingResponse()
    msg = resp.message()

    estado = estados.get(telefono, {"paso": "inicio"})
    paso = estado["paso"]
    mensaje_lower = mensaje.lower().strip()

    # Finalizaciones cortas
    if any(frase in mensaje_lower for frase in FRASES_FINALIZACION):
        msg.body("🤖 En SAMAPA estamos para servirle. ¡Gracias a usted!")
        limpiar_estado(telefono)
        return str(resp)

    # Evitar procesamiento duplicado del mismo mensaje/paso
    if ULTIMO_MENSAJE.get(telefono) == {"mensaje": mensaje, "paso": paso}:
        return str(resp)

    # Expiración de sesión 3 minutos
    if telefono in ULTIMA_INTERACCION and now - ULTIMA_INTERACCION[telefono] > timedelta(minutes=3):
        limpiar_estado(telefono)
        estados[telefono] = {"paso": "inicio"}
        msg.body("⏰ Tu sesión ha expirado. Empecemos de nuevo.")
        return str(resp)

    # Escalamiento a humano
    if any(p in mensaje_lower for p in ["ayuda", "humano", "operador"]):
        msg.body(manejar_escalamiento(telefono, mensaje))
        limpiar_estado(telefono)
        return str(resp)

    ULTIMA_INTERACCION[telefono] = now

    # Buscar último reporte del usuario (para comandos rápidos)
    reporte = Report.query.filter_by(telefono=telefono).order_by(Report.timestamp.desc()).first()
    asignacion = None
    if reporte:
        asignacion = Assignment.query.filter_by(report_id=reporte.id).order_by(Assignment.timestamp.desc()).first()

    # Comandos sobre el último reporte
    if reporte:
        if mensaje_lower == "estado":
            if asignacion and asignacion.status:
                msg.body(f"El estado actual de tu reporte #{reporte.id} es: {asignacion.status.descripcion}.")
            else:
                msg.body("Tu reporte no tiene estado asignado aún.")
            return str(resp)

        if mensaje_lower == "cuadrilla":
            if asignacion and asignacion.team:
                msg.body(f"La cuadrilla asignada a tu reporte #{reporte.id} es: {asignacion.team.nombre}.")
            else:
                msg.body("Tu reporte no tiene cuadrilla asignada aún.")
            return str(resp)

        if mensaje_lower.startswith("actualizar estado "):
            nuevo_estado_desc = mensaje_lower.replace("actualizar estado ", "").strip()
            nuevo_estado = Status.query.filter(Status.descripcion.ilike(f"%{nuevo_estado_desc}%")).first()
            if nuevo_estado:
                nueva_asignacion = Assignment(
                    report_id=reporte.id,
                    team_id=asignacion.team_id if asignacion else None,
                    status_id=nuevo_estado.id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(nueva_asignacion)
                db.session.commit()
                msg.body(f"Estado actualizado a '{nuevo_estado.descripcion}' para tu reporte #{reporte.id}.")
            else:
                msg.body("No se encontró el estado indicado. Por favor intenta con otro estado válido.")
            return str(resp)

        if mensaje_lower.startswith("asignar cuadrilla "):
            nueva_cuadrilla_nombre = mensaje_lower.replace("asignar cuadrilla ", "").strip()
            nueva_cuadrilla = Team.query.filter(Team.nombre.ilike(f"%{nueva_cuadrilla_nombre}%")).first()
            if nueva_cuadrilla:
                nueva_asignacion = Assignment(
                    report_id=reporte.id,
                    team_id=nueva_cuadrilla.id,
                    status_id=asignacion.status_id if asignacion else None,
                    timestamp=datetime.utcnow()
                )
                db.session.add(nueva_asignacion)
                db.session.commit()
                msg.body(f"Cuadrilla asignada a '{nueva_cuadrilla.nombre}' para tu reporte #{reporte.id}.")
            else:
                msg.body("No se encontró la cuadrilla indicada. Por favor intenta con otro nombre válido.")
            return str(resp)

    # ---------------------------
    # Flujo de creación de reporte
    # ---------------------------

    if paso == "inicio":
        msg.body(f"{get_saludo()}, te invitamos a leer el aviso de privacidad de los datos publicos en el siguiente enlace https://samapa.imembrillos.gob.mx/aviso-de-privacidad/, ¿con quién tengo el gusto?")
        estado["paso"] = "nombre"

    elif paso == "nombre":
        estado["reportante"] = mensaje.title()
        msg.body("¿Tienes número de cuenta de agua? Si no tienes, escribe 'no'.")
        estado["paso"] = "cuenta"

    elif paso == "cuenta":
        estado["numero_cuenta"] = mensaje if mensaje_lower != "no" else None
        msg.body("¿Qué deseas reportar?\n1️⃣ Reporte de Agua\n2️⃣ Reporte de Drenaje\n3️⃣ Checar un reporte\n4️⃣ Desperdicio de Agua")
        estado["paso"] = "tipo"

    elif paso == "tipo":
        opcion = mensaje_lower
        if opcion in ["1", "agua"]:
            estado["tipo"] = "Agua"
            msg.body(
                "Selecciona el tipo de reporte de agua:\n"
                "1️⃣ FUGA DE AGUA EN LÍNEA PRINCIPAL\n2️⃣ INCORPORACIÓN DE AGUA\n3️⃣ TOMA TAPADA\n4️⃣ FUGA DE AGUA PARTICULAR\n"
                "5️⃣ VÁLVULA LÍNEA PRINCIPAL\n6️⃣ PIPA DE AGUA\n7️⃣ POCA PRESIÓN DE AGUA\n8️⃣ RECONEXIÓN\n9️⃣ CORTE DE TOMA\n10️⃣ DESPERDICIO DE AGUA\n"
                "11️⃣ LÍNEA DE AGUA TAPADA\n12️⃣ INSTALACIÓN DE MEDIDOR\n13️⃣ REVISAR TOMA DE AGUA\n14️⃣ CAMBIO DE MEDIDOR\n15️⃣ SOCAVÓN\n16️⃣ EMPEDRADO"
            )
            estado["paso"] = "subtipo_agua"

        elif opcion in ["2", "drenaje"]:
            estado["tipo"] = "Drenaje"
            msg.body(
                "Selecciona el tipo de reporte de drenaje:\n"
                "1️⃣ DRENAJE TAPADO\n2️⃣ INCORPORACIÓN DE DRENAJE\n3️⃣ DRENAJE DAÑADO\n4️⃣ CAMBIAR TAPA DE REGISTRO\n"
                "5️⃣ DESAZOLVE\n6️⃣ SERVICIO DE VACTOR\n7️⃣ SOCAVÓN\n8️⃣ EMPEDRADO"
            )
            estado["paso"] = "subtipo_drenaje"

        elif opcion in ["3", "checar", "reporte"]:
            msg.body("Ingresa el número de reporte:")
            estado["paso"] = "consulta_id"

        elif opcion in ["4", "desperdicio"]:
            estado["tipo"] = "Desperdicio de Agua"
            estado["subtipo"] = ""
            # 🔁 nuevo flujo: localidad primero
            msg.body("📍 Escribe la *localidad/colonia* (o las primeras letras).")
            estado["paso"] = "localidad"
        else:
            msg.body("❌ Opción inválida. Escribe 1, 2, 3 o 4.")

    elif paso in ["subtipo_agua", "subtipo_drenaje"]:
        opciones = {
            "subtipo_agua": {
                "1": "FUGA DE AGUA EN LÍNEA PRINCIPAL", "2": "INCORPORACIÓN DE AGUA", "3": "TOMA TAPADA", "4": "FUGA DE AGUA PARTICULAR",
                "5": "VÁLVULA LÍNEA PRINCIPAL", "6": "PIPA DE AGUA", "7": "POCA PRESIÓN DE AGUA", "8": "RECONEXIÓN", "9": "CORTE DE TOMA",
                "10": "DESPERDICIO DE AGUA", "11": "LÍNEA DE AGUA TAPADA", "12": "INSTALACIÓN DE MEDIDOR", "13": "REVISAR TOMA DE AGUA",
                "14": "CAMBIO DE MEDIDOR", "15": "SOCAVÓN", "16": "EMPEDRADO"
            },
            "subtipo_drenaje": {
                "1": "DRENAJE TAPADO", "2": "INCORPORACIÓN DE DRENAJE", "3": "DRENAJE DAÑADO", "4": "CAMBIAR TAPA DE REGISTRO",
                "5": "DESAZOLVE", "6": "SERVICIO DE VACTOR", "7": "SOCAVÓN", "8": "EMPEDRADO"
            }
        }
        sub = normalizar_numero(mensaje)
        tipo_sub = opciones[paso]
        estado["subtipo"] = tipo_sub.get(sub, None)
        if not estado["subtipo"]:
            msg.body("❌ Subtipo no reconocido. Por favor selecciona una opción válida del menú.")
            return str(resp)

        # 🔁 nuevo flujo: pedir localidad primero
        msg.body("📍 Escribe la *localidad/colonia* (o las primeras letras).")
        estado["paso"] = "localidad"

    # ---------------------------
    # Localidad (con sugerencias)
    # ---------------------------
    elif paso == "localidad":
        entrada = mensaje.strip()
        if entrada.lower() == "cancelar":
            msg.body("Operación cancelada. Si deseas iniciar un reporte nuevo, escribe cualquier mensaje.")
            limpiar_estado(telefono)
            return str(resp)

        # ¿coincidencia exacta?
        loc = Localidad.query.filter(Localidad.nombre.ilike(entrada)).first()
        if not loc:
            # Buscar sugerencias
            candidatos = [(l.id, l.nombre) for l in Localidad.query.all()]
            sugerencias = _rank_suggestions(entrada, candidatos)
            estado["sugerencias_localidad"] = sugerencias
            if sugerencias and _normalize_text(entrada) in [_normalize_text(s["nombre"]) for s in sugerencias[:1]]:
                # si la mejor coincide casi exacto, tomarla
                loc = Localidad.query.get(sugerencias[0]["id"])

        if loc:
            estado["localidad_id"] = loc.id
            estado["localidad_nombre"] = loc.nombre
            msg.body(f"✅ Localidad: {loc.nombre}\n\nAhora escribe la *calle* (o las primeras letras).")
            estado["paso"] = "calle"
        else:
            msg.body(_msg_sugerencias("localidad", estado.get("sugerencias_localidad", [])))
            estado["paso"] = "localidad_sugerencias"

    elif paso == "localidad_sugerencias":
        if mensaje_lower == "cancelar":
            msg.body("Operación cancelada. Si deseas iniciar un reporte nuevo, escribe cualquier mensaje.")
            limpiar_estado(telefono)
            return str(resp)

        sug = estado.get("sugerencias_localidad", [])
        num = normalizar_numero(mensaje)
        loc = None
        if num and num.isdigit():
            idx = int(num) - 1
            if 0 <= idx < len(sug):
                loc = Localidad.query.get(sug[idx]["id"])
        if not loc:
            # volver a intentar con texto libre
            entrada = mensaje.strip()
            loc = Localidad.query.filter(Localidad.nombre.ilike(entrada)).first()
        if loc:
            estado["localidad_id"] = loc.id
            estado["localidad_nombre"] = loc.nombre
            msg.body(f"✅ Localidad: {loc.nombre}\n\nAhora escribe la *calle* (o las primeras letras).")
            estado["paso"] = "calle"
        else:
            msg.body("No pude identificar la localidad. Escribe nuevamente (o 'cancelar').")

    # ------------------------
    # Calle (con sugerencias)
    # ------------------------
    elif paso == "calle":
        entrada = mensaje.strip()
        if entrada.lower() == "cancelar":
            msg.body("Operación cancelada. Si deseas iniciar un reporte nuevo, escribe cualquier mensaje.")
            limpiar_estado(telefono)
            return str(resp)

        loc_id = estado.get("localidad_id")
        if not loc_id:
            msg.body("Primero selecciona una localidad. Escribe la *localidad/colonia*.")
            estado["paso"] = "localidad"
            return str(resp)

        # ¿coincidencia exacta dentro de la localidad?
        calle = Calle.query.filter_by(localidad_id=loc_id).filter(Calle.nombre.ilike(entrada)).first()
        if not calle:
            # sugerencias dentro de esa localidad
            candidatos = [(c.id, c.nombre) for c in Calle.query.filter_by(localidad_id=loc_id).all()]
            sugerencias = _rank_suggestions(entrada, candidatos)
            estado["sugerencias_calle"] = sugerencias
            if sugerencias and _normalize_text(entrada) in [_normalize_text(s["nombre"]) for s in sugerencias[:1]]:
                calle = Calle.query.get(sugerencias[0]["id"])

        if calle:
            estado["calle_id"] = calle.id
            estado["calle_nombre"] = calle.nombre
            msg.body(f"✅ Calle: {calle.nombre}\n\nAhora, ¿cuál es el *número exterior*?")
            estado["paso"] = "numero"
        else:
            msg.body(_msg_sugerencias("calle", estado.get("sugerencias_calle", [])))
            estado["paso"] = "calle_sugerencias"

    elif paso == "calle_sugerencias":
        if mensaje_lower == "cancelar":
            msg.body("Operación cancelada. Si deseas iniciar un reporte nuevo, escribe cualquier mensaje.")
            limpiar_estado(telefono)
            return str(resp)

        sug = estado.get("sugerencias_calle", [])
        num = normalizar_numero(mensaje)
        calle = None
        if num and num.isdigit():
            idx = int(num) - 1
            if 0 <= idx < len(sug):
                calle = Calle.query.get(sug[idx]["id"])
        if not calle:
            entrada = mensaje.strip()
            loc_id = estado.get("localidad_id")
            calle = Calle.query.filter_by(localidad_id=loc_id).filter(Calle.nombre.ilike(entrada)).first()
        if calle:
            estado["calle_id"] = calle.id
            estado["calle_nombre"] = calle.nombre
            msg.body(f"✅ Calle: {calle.nombre}\n\nAhora, ¿cuál es el *número exterior*?")
            estado["paso"] = "numero"
        else:
            msg.body("No pude identificar la calle. Escribe nuevamente (o 'cancelar').")

    # ------------------------
    # Número + duplicados
    # ------------------------
    elif paso == "numero":
        estado["numero"] = mensaje.strip()
        # Verificar duplicado (mismo calle_id + numero + localidad_id)
        loc_id = estado.get("localidad_id")
        calle_id = estado.get("calle_id")
        num = estado.get("numero")

        existente = Report.query.filter_by(
            localidad_id=loc_id,
            calle_id=calle_id,
            numero=num
        ).order_by(Report.timestamp.desc()).first()

        if existente:
            # Tomar estado actual si lo hay
            asign = Assignment.query.filter_by(report_id=existente.id).order_by(Assignment.timestamp.desc()).first()
            est_txt = asign.status.descripcion if (asign and asign.status) else "Sin estatus"
            fecha = existente.timestamp.strftime("%d/%m/%Y %H:%M") if existente.timestamp else "N/D"
            msg.body(
                f"⚠️ Ya existe un reporte reciente en esa dirección:\n"
                f"• Folio: #{existente.id}\n"
                f"• Estatus: {est_txt}\n"
                f"• Fecha: {fecha}\n\n"
                f"¿Deseas *continuar* de todos modos o *cancelar*?"
            )
            estado["posible_duplicado_id"] = existente.id
            estado["paso"] = "duplicado_confirmacion"
        else:
            msg.body("Entre qué calles está:")
            estado["paso"] = "entre_calles"

    elif paso == "duplicado_confirmacion":
        if mensaje_lower in ["continuar", "si", "sí", "seguir"]:
            msg.body("Entre qué calles está:")
            estado["paso"] = "entre_calles"
        else:
            msg.body("Reporte cancelado para evitar duplicados. Si deseas iniciar otro, escribe cualquier mensaje.")
            limpiar_estado(telefono)
            return str(resp)

    elif paso == "entre_calles":
        estado["entre_calles"] = mensaje
        msg.body("Describeme un poco el problema:")
        estado["paso"] = "descripcion"

    elif paso == "descripcion":
        estado["descripcion_problema"] = mensaje
        msg.body("📸 ¿Envía una foto/video (máx 15MB) o escribe 'no' para omitir?")
        estado["paso"] = "evidencia"

    elif paso == "evidencia":
        if media_url and media_type and media_type.startswith(("image/", "video/")):
            try:
                response = requests.get(
                    media_url,
                    auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                    timeout=10
                )

                if response.status_code != 200:
                    msg.body("❌ No se pudo descargar la evidencia. Intenta nuevamente.")
                    return str(resp)

                if len(response.content) > 15 * 1024 * 1024:
                    msg.body("⚠️ El archivo es muy grande. Envíalo de nuevo en menor calidad (máx 15MB).")
                    return str(resp)

                extension = media_type.split("/")[-1].lower()
                if extension not in ["jpg", "jpeg", "png", "mp4", "mov"]:
                    msg.body("❌ Solo se permiten fotos (JPG, PNG) o videos (MP4, MOV).")
                    return str(resp)

                filename = secure_filename(f"tmp_{telefono}_{uuid.uuid4().hex}.{extension}")
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                save_path = os.path.join(UPLOAD_FOLDER, filename)
                with open(save_path, "wb") as f:
                    f.write(response.content)

                estado["evidencia_filename"] = filename
                estado["evidencia"] = filename

            except requests.exceptions.Timeout:
                msg.body("⚠️ La descarga del archivo tardó demasiado. Intenta con una imagen o video más ligero.")
                return str(resp)

            except Exception as e:
                print(f"❌ Error al guardar evidencia: {e}")
                msg.body("❌ No se pudo guardar la evidencia. Intenta nuevamente.")
                return str(resp)

        elif mensaje_lower == "no":
            estado["evidencia"] = None
        else:
            msg.body("Si tienes problemas para adjuntar, escribe 'no' para continuar sin evidencia.")
            return str(resp)

        # Resumen usando nombres
        resumen = (
            f"📋 Por favor confirma tu reporte:\n\n"
            f"👤 Nombre: {estado['reportante']}\n"
            f"📱 Teléfono: {telefono}\n"
            f"💧 Tipo: {estado['tipo']} - {estado.get('subtipo','')}\n"
            f"📍 Dirección: {estado.get('calle_nombre','(calle?)')} #{estado.get('numero','')}, {estado.get('localidad_nombre','(localidad?)')}\n"
            f"🚧 Entre calles: {estado.get('entre_calles','')}\n"
            f"📝 Descripción: {estado.get('descripcion_problema','')}\n"
            f"💳 Cuenta: {estado.get('numero_cuenta') or 'No proporcionada'}\n"
            f"📎 Evidencia: {'Adjunta' if 'evidencia_filename' in estado else 'No proporcionada'}"
        )
        msg.body(resumen + "\n\n¿Está correcto el reporte? Responde 'sí' o 'no'")
        estado["paso"] = "confirmacion"

    elif paso == "confirmacion":
        if mensaje_lower in ["sí", "si"]:
            nuevo_reporte = Report(
                telefono=telefono,
                reportante=estado["reportante"],
                tipo=estado["tipo"],
                subtipo=estado.get("subtipo", ""),
                numero=estado["numero"],
                entre_calles=estado["entre_calles"],
                descripcion_problema=estado["descripcion_problema"],
                evidencia=estado.get("evidencia", None),
                numero_cuenta=estado["numero_cuenta"],
                timestamp=datetime.utcnow(),
                calle_id=estado["calle_id"],
                localidad_id=estado["localidad_id"]
            )
            db.session.add(nuevo_reporte)
            db.session.commit()

            # Renombrar evidencia con id de reporte
            if "evidencia_filename" in estado:
                extension = estado["evidencia_filename"].split(".")[-1]
                nuevo_nombre = f"reporte_{nuevo_reporte.id}.{extension}"
                origen = os.path.join(UPLOAD_FOLDER, estado["evidencia_filename"])
                destino = os.path.join(UPLOAD_FOLDER, nuevo_nombre)
                try:
                    os.rename(origen, destino)
                    nuevo_reporte.evidencia = nuevo_nombre
                    db.session.commit()
                except Exception as e:
                    print(f"⚠️ Error al renombrar evidencia: {e}")

            # Asignación inicial
            asignacion_inicial = Assignment(
                report_id=nuevo_reporte.id,
                team_id=Team.query.filter_by(nombre="Sin asignar").first().id if Team.query.filter_by(nombre="Sin asignar").first() else None,
                status_id=Status.query.filter_by(descripcion="Sin Asignar").first().id if Status.query.filter_by(descripcion="Sin Asignar").first() else 1,
                timestamp=datetime.utcnow()
            )
            db.session.add(asignacion_inicial)
            db.session.commit()

            msg.body(f"✅ ¡Gracias {estado['reportante']}!\nTu Número de reporte es: {nuevo_reporte.id}")
        else:
            msg.body("❌ Reporte cancelado. Si deseas volver a intentarlo, escribe cualquier mensaje.")
        limpiar_estado(telefono)
        return str(resp)

    elif paso == "consulta_id":
        estado["reporte_id_consulta"] = mensaje.strip()
        msg.body("🔐 Para verificar tu identidad, escribe el nombre de quien levantó el reporte.")
        estado["paso"] = "verificar_reportante"

    elif paso == "verificar_reportante":
        reporte_id = estado.get("reporte_id_consulta")
        nombre = mensaje.strip().lower()
        rep = Report.query.filter_by(id=reporte_id).first()

        if rep:
            if (rep.reportante or "").strip().lower() == nombre:
                asignacion_reporte = Assignment.query.filter_by(report_id=rep.id).order_by(Assignment.timestamp.desc()).first()
                if asignacion_reporte:
                    estado_desc = asignacion_reporte.status.descripcion if asignacion_reporte.status else "Sin estatus"
                    cuadrilla = asignacion_reporte.team.nombre if asignacion_reporte.team else "Sin cuadrilla asignada"
                    observaciones = asignacion_reporte.observaciones or "Sin observaciones"

                    usuario = User.query.filter_by(team_id=asignacion_reporte.team_id).first()
                    nombre_usuario = usuario.nombre if usuario else "Sin usuario asignado"

                    # Mostrar calle/localidad desde catálogos
                    calle = Calle.query.get(rep.calle_id)
                    loc = Localidad.query.get(rep.localidad_id)

                    msg.body(
                        f"📋 *Estado del Reporte #{rep.id}*\n"
                        f"📍 Dirección: {calle.nombre if calle else 'N/D'} #{rep.numero}, {loc.nombre if loc else 'N/D'}\n"
                        f"👤 Reportante: {rep.reportante}\n"
                        f"🛠 Cuadrilla: {cuadrilla}\n"
                        f"👷 Atendiendo: {nombre_usuario}\n"
                        f"📌 Estatus: {estado_desc}\n"
                        f"📝 Observaciones: {observaciones}"
                    )
                else:
                    msg.body(f"⚠️ Tu reporte #{rep.id} aún no ha sido asignado a ninguna cuadrilla.")
            else:
                msg.body("❌ El nombre no coincide con quien levantó el reporte.")
        else:
            msg.body("❌ No se encontró el folio.")
        limpiar_estado(telefono)

    # Guardar estado y anti-duplicado de mensaje
    estados[telefono] = estado
    ULTIMO_MENSAJE[telefono] = {"mensaje": mensaje, "paso": paso}
    return str(resp)


def init_bot(app=None):
    print("🤖 Bot de WhatsApp inicializado")
    if app:
        from flask import request

        @app.route("/webhook", methods=["POST"])
        def whatsapp_webhook():
            try:
                telefono_raw = request.values.get("From", "")
                telefono = normalizar_numero(telefono_raw)
                mensaje = request.values.get("Body", "")
                media_url = request.values.get("MediaUrl0", "")
                media_type = request.values.get("MediaContentType0", "")
                respuesta = manejar_mensaje_whatsapp(telefono, mensaje, media_url, media_type)
                return respuesta
            except Exception as e:
                print(f"❌ Error en webhook: {e}")
                return str(MessagingResponse().message("Ocurrió un error. Intenta más tarde."))


# Catálogo de tipos/subtipos
TIPOS_SUBTIPOS = {
    "Agua": [
        "FUGA DE AGUA EN LÍNEA PRINCIPAL", "INCORPORACIÓN DE AGUA", "TOMA TAPADA",
        "FUGA DE AGUA PARTICULAR", "VÁLVULA LÍNEA PRINCIPAL", "PIPA DE AGUA",
        "POCA PRESIÓN DE AGUA", "RECONEXIÓN", "CORTE DE TOMA", "DESPERDICIO DE AGUA",
        "LÍNEA DE AGUA TAPADA", "INSTALACIÓN DE MEDIDOR", "REVISAR TOMA DE AGUA",
        "CAMBIO DE MEDIDOR", "SOCAVÓN", "EMPEDRADO"
    ],
    "Drenaje": [
        "DRENAJE TAPADO", "INCORPORACIÓN DE DRENAJE", "DRENAJE DAÑADO",
        "CAMBIAR TAPA DE REGISTRO", "DESAZOLVE", "SERVICIO DE VACTOR",
        "SOCAVÓN", "EMPEDRADO"
    ],
    "Desperdicio de Agua": [
        "TIRANDO AGUA", "ALBERCA", "OTRO"
    ]
}

# ---------------------------
# Función para enviar WhatsApp desde cualquier parte del sistema
# ---------------------------
def send_whatsapp_message(to, body):
    """
    Envía un mensaje de WhatsApp usando Twilio.
    
    to: número de destino en formato '52155XXXXXXX'
    body: texto del mensaje
    """
    try:
        message = twilio_client.messages.create(
            from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
            to=f"whatsapp:{to}",
            body=body
        )
        return message.sid
    except Exception as e:
        print(f"❌ Error enviando WhatsApp: {e}")
        return None
