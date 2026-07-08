#!/usr/bin/env python3
import os
import sys
import asyncio
from dotenv import load_dotenv
from app.telegram.bot import build_telegram_app

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    print("❌ No se encontró TELEGRAM_TOKEN en .env")
    sys.exit(1)

async def main():
    print("🤖 BOT SIRMYN (PROCESO INDEPENDIENTE)")
    from telegram import Bot
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("🧹 Webhook eliminado")
    bot_app = build_telegram_app(TOKEN)
    print("🔄 Iniciando polling...")
    await bot_app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
