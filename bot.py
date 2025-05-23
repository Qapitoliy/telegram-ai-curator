import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import aiohttp
import asyncio
import httpx

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

async def ask_groq(prompt: str) -> str:
    url = "https://api.groq.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    json_data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=json_data)
        resp_json = response.json()
        if 'choices' in resp_json and len(resp_json['choices']) > 0:
            return resp_json['choices'][0]['message']['content']
        else:
            logging.error(f"Ошибка в ответе Groq: {resp_json}")
            return "Извините, произошла ошибка при обработке вашего запроса."

@dp.message.register()
async def handle_message(message: types.Message):
    user_text = message.text
    response = await ask_groq(user_text)
    await message.answer(response)

async def on_startup(app):
    logging.info("Бот запущен")

async def on_shutdown(app):
    await bot.session.close()

async def handle_webhook(request):
    data = await request.json()
    update = types.Update.to_object(data)
    await dp.process_update(update)
    return web.Response(text="ok")

app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    web.run_app(app, port=port)
