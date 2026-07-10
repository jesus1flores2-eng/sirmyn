"""
Lista de materiales para solicitud de camión
"""

# Lista principal de materiales
MATERIALES = [
    "Arena de río",
    "Jal",
    "Grava",
    "Cemento",
    "Tubería PVC",
    "Tierra",
    "Piedra",
    "Cal",
    "Bloques",
    "Varilla",
    "Alambre",
    "Madera",
    "Otro"
]

# Materiales por categoría (opcional, para futuro)
MATERIALES_POR_CATEGORIA = {
    "Áridos": ["Arena de río", "Jal", "Grava", "Tierra", "Piedra"],
    "Construcción": ["Cemento", "Cal", "Bloques", "Varilla", "Alambre"],
    "Tubería": ["Tubería PVC"],
    "Otros": ["Madera", "Otro"]
}

def obtener_materiales():
    """Devuelve la lista de materiales"""
    return MATERIALES

def obtener_materiales_para_teclado(columnas: int = 2):
    """
    Devuelve los materiales formateados para teclado inline
    """
    materiales = obtener_materiales()
    keyboard = []
    for i in range(0, len(materiales), columnas):
        fila = []
        for material in materiales[i:i+columnas]:
            # Crear callback con el material (reemplazar espacios por _)
            callback_data = f"material_camion_{material.replace(' ', '_')}"
            fila.append(material)
        keyboard.append(fila)
    return keyboard
