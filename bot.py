import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from aiohttp import web
import openai

# Переменные окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # https://your-service-name.onrender.com
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH
PORT = int(os.getenv("PORT", 5000))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# /start команда
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я твой ИИ-куратор. Чем помочь?")

# Обработка всех сообщений с вызовом OpenAI GPT
@dp.message_handler()
async def handle_message(message: types.Message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": message.text}],
            max_tokens=300,
            temperature=0.7,
        )
        reply = response.choices[0].message['content']
    except Exception as e:
        reply = f"Ошибка при обработке запроса: {e}"
    await message.answer(reply)

# Вебхук обработчик
async def handle(request):
    update = await request.json()
    update_obj = types.Update.to_object(update)
    await dp.process_update(update_obj)
    return web.Response()

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle)

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=PORT,
    )
