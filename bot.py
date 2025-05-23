import logging
import os
from aiogram import Bot, Dispatcher, types
from aiohttp import web
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)


# Генерация ответа через Groq
async def generate_response(message_text: str) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "mixtral-8x7b-32768",
        "messages": [
            {"role": "system", "content": "Ты персональный ИИ-куратор. Помогай пользователю с задачами, мотивацией, планами, бизнесом, психологической поддержкой и спортом."},
            {"role": "user", "content": message_text},
        ]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(GROQ_API_URL, headers=headers, json=payload) as resp:
            data = await resp.json()

            if "choices" not in data:
                logging.error(f"Ошибка в ответе Groq: {data}")
                return "⚠️ Не удалось получить ответ от ИИ."

            return data["choices"][0]["message"]["content"]


# Обработка входящих сообщений
@dp.message_handler()
async def handle_message(message: types.Message):
    response = await generate_response(message.text)
    await message.answer(response)


# Webhook обработчик
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

async def handle_webhook(request):
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return web.Response()

# Запуск aiohttp-сервера
def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

if __name__ == "__main__":
    main()
