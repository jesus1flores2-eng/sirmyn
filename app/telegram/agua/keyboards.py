from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.telegram.common.keyboards import crear_teclado_subtipos

# Subti pos de Agua
SUBTIPOS_AGUA = {
    "1": "💧 Fuga en línea principal",
    "2": "🔧 Incorporación de servicio",
    "3": "🚱 Toma tapada",
    "4": "💦 Fuga en toma particular",
    "5": "🔩 Válvula dañada",
    "6": "🚛 Solicitud de pipa",
    "7": "📉 Poca presión",
    "8": "🔄 Reconexión de servicio"
}

SUBTIPOS_DRENAJE = {
    "1": "🚽 Drenaje tapado",
    "2": "🔧 Incorporación de drenaje",
    "3": "💥 Tubo dañado/roto",
    "4": "🔩 Cambio de tapa de registro",
    "5": "🧹 Desazolve"
}

def teclado_subtipos_agua():
    return crear_teclado_subtipos(SUBTIPOS_AGUA)

def teclado_subtipos_drenaje():
    return crear_teclado_subtipos(SUBTIPOS_DRENAJE)
