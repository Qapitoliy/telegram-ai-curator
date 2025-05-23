import os
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # например: https://your-service.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 10000))

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Функция запроса к Groq API
async def ask_groq(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    json_data = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": "Ты — дружелюбный Telegram-бот с ИИ, помогай пользователю."},
            {"role": "user", "content": prompt}
        ]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=json_data) as response:
            result = await response.json()
            try:
                return result["choices"][0]["message"]["content"]
            except Exception as e:
                logging.error("Ошибка в ответе Groq: %s", result)
                return "Извините, произошла ошибка при обработке вашего запроса."

# Обработчик сообщений
async def handle_message(message: types.Message):
    user_text = message.text
    response = await ask_groq(user_text)
    await message.answer(response)

dp.message.register(handle_message)

# Настройка webhook
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
app.on_startup.append(lambda _: on_startup(bot))
app.on_shutdown.append(lambda _: on_shutdown(bot))

if __name__ == "__main__":
    setup_application(app, dp, bot=bot)
    web.run_app(app, port=PORT)
