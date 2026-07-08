from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, jsonify
from werkzeug.utils import secure_filename
from app import db
from app.models.report import Report, Assignment, Calle, Localidad
import os
import datetime
from uuid import uuid4
from app.services.whatsapp_bot import TIPOS_SUBTIPOS
from datetime import datetime, timedelta

captura_bp = Blueprint('captura', __name__)

@captura_bp.route('/captura/iniciar', methods=['GET', 'POST'])
def captura_inicio():
    if request.method == 'POST':
        # Tomamos los IDs ocultos de localidad y calle
        localidad_id = request.form.get('localidad_id')
        calle_id = request.form.get('calle_id')

        if not localidad_id or not calle_id:
            flash("Debes seleccionar una localidad y una calle válidas.", "warning")
            return redirect(url_for('captura.captura_inicio'))

        session['reporte_datos'] = {
            'reportante': request.form.get('reportante', ''),
            'telefono': request.form.get('telefono', ''),
            'localidad_id': int(localidad_id),
            'calle_id': int(calle_id),
            'numero': request.form.get('numero', ''),
            'entre_calles': request.form.get('entre_calles', '')
        }
        return redirect(url_for('captura.captura_paso2'))

    localidades = Localidad.query.order_by(Localidad.nombre).all()
    return render_template('captura/paso1_datos.html', localidades=localidades)


@captura_bp.route('/captura/paso2', methods=['GET', 'POST'])
def captura_paso2():
    if request.method == 'POST':
        reporte = session.get('reporte_datos', {})
        reporte['tipo'] = request.form.get('tipo', '')
        reporte['subtipo'] = request.form.get('subtipo', '')
        reporte['descripcion_problema'] = request.form.get('descripcion_problema', '')
        session['reporte_datos'] = reporte
        return redirect(url_for('captura.captura_paso3'))

    tipos = list(TIPOS_SUBTIPOS.keys())
    reporte = session.get('reporte_datos', {})
    tipo_seleccionado = reporte.get('tipo', '')
    subtipo_seleccionado = reporte.get('subtipo', '')
    subtipos = TIPOS_SUBTIPOS.get(tipo_seleccionado, [])

    return render_template(
        'captura/paso2_tipo_subtipo.html',
        tipos=tipos,
        subtipos=subtipos,
        tipo_seleccionado=tipo_seleccionado,
        subtipo_seleccionado=subtipo_seleccionado,
        TIPOS_SUBTIPOS=TIPOS_SUBTIPOS
    )


@captura_bp.route('/captura/paso3', methods=['GET', 'POST'])
def captura_paso3():
    UPLOAD_FOLDER = os.path.abspath(os.path.join(current_app.root_path, '..', 'uploads'))
    reporte = session.get('reporte_datos')
    if not reporte:
        flash("Primero llena los pasos anteriores.", "warning")
        return redirect(url_for('captura.captura_inicio'))

    if request.method == 'POST':
        localidad = Localidad.query.get(reporte['localidad_id'])
        calle = Calle.query.get(reporte['calle_id'])

        if not localidad or not calle or calle.localidad_id != localidad.id:
            flash("Localidad o calle inválida.", "danger")
            return redirect(url_for('captura.captura_inicio'))

        # Guardar evidencia temporal
        archivo = request.files.get('evidencia')
        temp_name = None
        if archivo and archivo.filename != '':
            filename = secure_filename(archivo.filename)
            ext = filename.rsplit('.', 1)[-1].lower()
            temp_name = f"temp_{uuid4().hex}.{ext}"
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            temp_path = os.path.join(UPLOAD_FOLDER, temp_name)
            archivo.save(temp_path)

        # Verificación de duplicados (últimos 30 minutos)
        ventana = datetime.utcnow() - timedelta(minutes=30)
        duplicado = Report.query.filter(
            Report.telefono == reporte.get('telefono'),
            Report.tipo == reporte.get('tipo'),
            Report.subtipo == reporte.get('subtipo'),
            Report.calle_id == calle.id,
            Report.numero == reporte.get('numero'),
            Report.localidad_id == localidad.id,
            Report.descripcion_problema == reporte.get('descripcion_problema'),
            Report.timestamp >= ventana
        ).first()

        if duplicado:
            flash(f"⚠️ Ya existe un reporte similar en los últimos 30 minutos (ID: {duplicado.id})", "warning")
            if temp_name:
                os.remove(temp_path)
            return redirect(url_for('captura.captura_inicio'))

        # Crear reporte real
        nuevo_reporte = Report(
            reportante=reporte.get('reportante'),
            telefono=reporte.get('telefono'),
            calle_id=calle.id,
            localidad_id=localidad.id,
            numero=reporte.get('numero'),
            entre_calles=reporte.get('entre_calles'),
            tipo=reporte.get('tipo'),
            subtipo=reporte.get('subtipo'),
            descripcion_problema=reporte.get('descripcion_problema'),
            evidencia=None,
            timestamp=datetime.utcnow()
        )
        db.session.add(nuevo_reporte)
        db.session.commit()  # Para obtener el ID

        # Crear asignación inicial
        asignacion = Assignment(
            report_id=nuevo_reporte.id,
            team_id=None,  # Sin asignar
            status_id=1    # id=1 -> "Sin asignar"
        )
        db.session.add(asignacion)
        db.session.commit()

        # Renombrar evidencia
        if temp_name:
            ext = temp_name.rsplit('.', 1)[-1]
            nuevo_nombre = f"reporte_{nuevo_reporte.id}.{ext}"
            nuevo_path = os.path.join(UPLOAD_FOLDER, nuevo_nombre)
            try:
                os.rename(temp_path, nuevo_path)
                nuevo_reporte.evidencia = nuevo_nombre
                db.session.commit()
            except Exception as e:
                print(f"⚠️ Error al renombrar evidencia: {e}")

        session.pop('reporte_datos', None)

        return render_template(
            'captura/paso3_confirmar_guardar.html',
            reporte=nuevo_reporte,
            mensaje=f"✅ Reporte guardado correctamente. Número de reporte: {nuevo_reporte.id}"
        )

    return render_template('captura/paso3_confirmar_guardar.html', reporte=reporte)


@captura_bp.route('/captura/subtipos/<tipo>')
def obtener_subtipos(tipo):
    subtipos = TIPOS_SUBTIPOS.get(tipo, [])
    return jsonify(subtipos)


# Autocompletado
@captura_bp.route('/captura/autocomplete/localidades')
def autocomplete_localidades():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    resultados = Localidad.query.filter(Localidad.nombre.ilike(f"%{q}%")).order_by(Localidad.nombre).all()
    return jsonify([{"id": loc.id, "nombre": loc.nombre} for loc in resultados])


@captura_bp.route('/captura/autocomplete/calles/<int:localidad_id>')
def autocomplete_calles(localidad_id):
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    resultados = Calle.query.filter(
        Calle.localidad_id == localidad_id,
        Calle.nombre.ilike(f"%{q}%")
    ).order_by(Calle.nombre).all()
    return jsonify([{"id": c.id, "nombre": c.nombre} for c in resultados])
