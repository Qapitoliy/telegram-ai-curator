import os
import logging
import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Например: https://your-service.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 10000))
DB_PATH = "memory.db"

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Инициализация базы данных (память)
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS user_memory (
                user_id INTEGER PRIMARY KEY,
                context TEXT
            )"""
        )
        await db.commit()

# Функция получения контекста из памяти
async def get_user_context(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT context FROM user_memory WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else ""

# Функция сохранения контекста
async def save_user_context(user_id: int, context: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_memory (user_id, context) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET context=excluded.context",
            (user_id, context),
        )
        await db.commit()

# Функция запроса к Groq API с учётом контекста
async def ask_groq(user_id: int, prompt: str) -> str:
    context = await get_user_context(user_id)

    messages = [
        {"role": "system", "content": "Ты — дружелюбный Telegram-бот с ИИ, помогай пользователю."},
    ]

    if context:
        messages.append({"role": "assistant", "content": context})

    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    json_data = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages
    }

    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=json_data) as response:
            result = await response.json()
            try:
                answer = result["choices"][0]["message"]["content"]
                # Обновляем контекст памяти
                new_context = (context + "\n" + prompt + "\n" + answer).strip()
                await save_user_context(user_id, new_context)
                return answer
            except Exception as e:
                logging.error("Ошибка в ответе Groq: %s", result)
                return "Извините, произошла ошибка при обработке вашего запроса."

# Обработчик сообщений
@dp.message()
async def handle_message(message: types.Message):
    user_text = message.text
    response = await ask_groq(message.from_user.id, user_text)
    await message.answer(response)

# Настройка webhook
async def on_startup(bot: Bot):
    await init_db()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logging.info("Webhook удалён")

app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
app.on_startup.append(lambda _: on_startup(bot))
app.on_shutdown.append(lambda _: on_shutdown(bot))

if __name__ == "__main__":
    setup_application(app, dp, bot=bot)
    web.run_app(app, port=PORT)
