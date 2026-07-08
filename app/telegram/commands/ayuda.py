from telegram import Update
from telegram.ext import ContextTypes

async def ayuda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = (
        "🤖 *Comandos disponibles:*\n\n"
        "*/start* - Iniciar un nuevo reporte\n"
        "*/estado* - Ver estado del último reporte\n"
        "*/ayuda* - Mostrar esta ayuda\n"
        "*/cancelar* - Cancelar operación actual\n\n"
        "*Flujo de reporte:*\n"
        "1. Nombre del reportante\n"
        "2. Seleccionar dependencia\n"
        "3. Si es Agua/Drenaje: Número de cuenta (opcional)\n"
        "4. Tipo específico de problema\n"
        "5. Localidad y calle\n"
        "6. Descripción del problema\n"
        "7. Evidencia (opcional)\n"
        "8. Confirmación"
    )
    await update.message.reply_text(mensaje, parse_mode="Markdown")
