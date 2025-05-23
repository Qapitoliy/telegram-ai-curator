import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
import aiohttp

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # https://your-app.onrender.com
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Функция вызова Groq API
async def ask_ai(question: str) -> str:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    if not GROQ_API_KEY:
        return "Ошибка: не задан ключ GROQ_API_KEY"

    url = "https://api.groq.com/v1/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.3-70b-versatile",
        "prompt": question,
        "max_tokens": 150,
        "temperature": 0.7,
        "top_p": 1,
        "stop_sequences": ["\n"]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status != 200:
                return f"Ошибка API Groq: {resp.status}"
            res = await resp.json()
            try:
                # В Groq ответ обычно в res['choices'][0]['text']
                return res['choices'][0]['text'].strip()
            except (KeyError, IndexError):
                return "Ошибка в ответе Groq API"

@dp.message()
async def handle_message(message: types.Message):
    question = message.text
    await message.answer("Думаю...")
    answer = await ask_ai(question)
    await message.answer(answer)

async def handle_update(request: web.Request):
    try:
        data = await request.json()
        update = Update(**data)
        await dp.process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        logging.exception("Ошибка при обработке update")
        return web.Response(status=500, text=str(e))

async def on_startup(app: web.Application):
    logging.info("Setting webhook")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app: web.Application):
    logging.info("Deleting webhook")
    await bot.delete_webhook()
    await bot.session.close()

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_update)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    web.run_app(app, port=port)
