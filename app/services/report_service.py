from app.models.report import Report
from app.extensions import db
from datetime import datetime

def obtener_reportes():
    return Report.query.order_by(Report.timestamp.desc()).all()

def obtener_reportes_filtrados(tipo=None, subtipo=None, localidad=None, team_id=None, status_id=None):
    query = Report.query

    if tipo:
        query = query.filter(Report.tipo == tipo)
    if subtipo:
        query = query.filter(Report.subtipo == subtipo)
    if localidad:
        query = query.filter(Report.localidad == localidad)

    if team_id or status_id:
        # Filtrar reports que tengan asignaciones con esos team/status
        from app.models.report import Assignment
        subquery = Assignment.query

        if team_id:
            subquery = subquery.filter(Assignment.team_id == int(team_id))
        if status_id:
            subquery = subquery.filter(Assignment.status_id == int(status_id))

        report_ids = [a.report_id for a in subquery.distinct(Assignment.report_id).all()]
        query = query.filter(Report.id.in_(report_ids))

    return query.order_by(Report.timestamp.desc()).all()


def duplicar_reporte(reporte_id):
    reporte_original = Report.query.get(reporte_id)
    if not reporte_original:
        return None

    nuevo = Report(
        telefono=reporte_original.telefono,
        reportante=reporte_original.reportante,
        tipo=reporte_original.tipo,
        subtipo=reporte_original.subtipo,
        calle=reporte_original.calle,
        numero=reporte_original.numero,
        localidad=reporte_original.localidad,
        entre_calles=reporte_original.entre_calles,
        descripcion_problema=reporte_original.descripcion_problema,
        evidencia=reporte_original.evidencia,
        timestamp=datetime.utcnow(),
        numero_cuenta=reporte_original.numero_cuenta
    )
    db.session.add(nuevo)
    db.session.commit()
    return nuevo.id


def obtener_tipos_unicos():
    tipos = Report.query.with_entities(Report.tipo).distinct().all()
    return [t[0] for t in tipos if t[0]]


def obtener_subtipos_unicos():
    subtipos = Report.query.with_entities(Report.subtipo).distinct().all()
    return [s[0] for s in subtipos if s[0]]


def obtener_localidades_unicas():
    localidades = Report.query.with_entities(Report.localidad).distinct().all()
    return [l[0] for l in localidades if l[0]]
