import os
import logging
import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, types

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

async def query_groq_api(prompt: str) -> str:
    url = "https://api.groq.com/v1/engines/text/generate"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    json_data = {
        "model": GROQ_MODEL,
        "prompt": prompt,
        "max_tokens": 512
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=json_data) as resp:
            if resp.status != 200:
                text = await resp.text()
                logging.error(f"Groq API error: {resp.status} - {text}")
                return "Извините, произошла ошибка при обработке вашего запроса."
            data = await resp.json()
            try:
                return data['choices'][0]['text'].strip()
            except Exception as e:
                logging.error(f"Ошибка парсинга ответа Groq: {e}")
                return "Извините, произошла ошибка при обработке вашего запроса."

@dp.message()
async def handle_message(message: types.Message):
    user_text = message.text
    logging.info(f"Получено сообщение: {user_text}")
    response = await query_groq_api(user_text)
    await message.answer(response)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
