# app/telegram/dicts.py
TIPOS_DEPENDENCIAS = {
    "1": "Agua potable",
    "2": "Drenaje",
    "3": "Aseo público",
    "4": "Alumbrado público", 
    "5": "Parques y jardines",
    "6": "Ecología",
    "7": "Seguridad pública",
    "8": "Obras públicas",
    "9": "Bomberos"
}

SUBTIPOS_AGUA = {
    "1": "Fuga en línea principal",
    "2": "Incorporación de servicio",
    "3": "Toma tapada",
    "4": "Fuga en toma particular",
    "5": "Válvula dañada",
    "6": "Solicitud de pipa",
    "7": "Poca presión",
    "8": "Reconexión de servicio"
}

SUBTIPOS_DRENAJE = {
    "1": "Drenaje tapado",
    "2": "Incorporación de drenaje",
    "3": "Tubo dañado/roto",
    "4": "Cambio de tapa de registro",
    "5": "Desazolve"
}

SUBTIPOS_ASEO_PUBLICO = {
    "1": "Recolección de basura",
    "2": "Limpieza de terreno baldío",
    "3": "No paso el camion",
    "4": "Retiro de escombros"
}

SUBTIPOS_ALUMBRADO_PUBLICO = {
    "1": "Lámpara quemada",
    "2": "Poste dañado",
    "3": "Cable suelto/pelado",
    "4": "Falta de iluminación"
}

SUBTIPOS_PARQUES_JARDINES = {
    "1": "Poda de árboles",
    "2": "Limpieza de área verde",
    "3": "Riego de plantas",
    "4": "Mantenimiento de juegos"
}

SUBTIPOS_ECOLOGIA = {
    "1": "Residuos peligrosos",
    "2": "Contaminación de agua",
    "3": "Quema de basura",
    "4": "Tala ilegal"
}

SUBTIPOS_SEGURIDAD_PUBLICA = {
    "1": "Vandalismo/grafiti",
    "2": "Robo",
    "3": "Accidente vial",
    "4": "Alteración del orden"
}

SUBTIPOS_OBRAS_PUBLICAS = {
    "1": "Calle dañada/baches",
    "2": "Banqueta dañada",
    "3": "Instalación de topes",
    "4": "Señalización vial"
}

SUBTIPOS_BOMBEROS = {
    "1": "Incendio estructural",
    "2": "Incendio forestal/vegetación",
    "3": "Fuga de gas",
    "4": "Rescate vehicular"
}
