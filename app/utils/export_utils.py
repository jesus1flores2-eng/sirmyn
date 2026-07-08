import pandas as pd
import tempfile

def exportar_excel(reportes):
    data = []
    for r in reportes:
        data.append({
            'ID': r.id,
            'Teléfono': r.telefono,
            'Reportante': r.reportante,
            'Tipo': r.tipo,
            'Subtipo': r.subtipo,
            'Calle': r.calle,
            'Número': r.numero,
            'Localidad': r.localidad,
            'Entre calles': r.entre_calles,
            'Descripción': r.descripcion_problema,
            'Número cuenta': r.numero_cuenta,
            'Estado': r.status.descripcion if r.status else '',
            'Cuadrilla': r.team.nombre if r.team else '',
            'Fecha': r.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })

    df = pd.DataFrame(data)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    df.to_excel(temp_file.name, index=False)
    return temp_file.name
