import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiohttp import ClientSession

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

API_URL = "https://api.groq.com/v1/completions"

async def query_groq(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "prompt": prompt,
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 1,
        "n": 1,
        "stop": None,
    }

    async with ClientSession() as session:
        async with session.post(API_URL, json=payload, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["choices"][0]["text"].strip()
            else:
                error_text = await resp.text()
                logging.error(f"Ошибка в ответе Groq: {error_text}")
                return "Извините, произошла ошибка при обработке вашего запроса."

@dp.message_handler()
async def handle_message(message: types.Message):
    user_text = message.text
    logging.info(f"Запрос пользователя: {user_text}")
    response_text = await query_groq(user_text)
    await message.answer(response_text)

async def on_startup(dp):
    logging.info("Бот запущен")

if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, on_startup=on_startup)
