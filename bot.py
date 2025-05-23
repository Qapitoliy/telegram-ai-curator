import os
import logging
import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
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
logger = logging.getLogger(__name__)

# Инициализация бота с исправлением предупреждения по parse_mode
bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

DB_PATH = "memory.db"

# Инициализация базы данных для постоянной памяти
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id INTEGER PRIMARY KEY,
                history TEXT
            )
        """)
        await db.commit()

async def get_user_memory(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT history FROM user_memory WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else ""

async def update_user_memory(user_id: int, new_text: str):
    old_memory = await get_user_memory(user_id)
    # Добавляем новую реплику к истории, ограничим длину (например, 3000 символов)
    updated_memory = (old_memory + "\n" + new_text).strip()
    if len(updated_memory) > 3000:
        updated_memory = updated_memory[-3000:]  # Оставляем последние 3000 символов
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_memory(user_id, history) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET history=excluded.history",
            (user_id, updated_memory)
        )
        await db.commit()

# Функция запроса к Groq API с учетом памяти
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
                logger.error("Ошибка в ответе Groq: %s", result)
                return "Извините, произошла ошибка при обработке вашего запроса."

# Обработчик сообщений с памятью
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text
    
    history = await get_user_memory(user_id)
    prompt = history + "\nПользователь: " + user_text + "\nБот:"
    
    response = await ask_groq(prompt)
    
    # Обновляем память: добавляем вопрос и ответ
    await update_user_memory(user_id, f"Пользователь: {user_text}\nБот: {response}")
    
    await message.answer(response)

dp.message.register(handle_message)

# Настройка webhook
async def on_startup(bot: Bot):
    await init_db()
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Webhook удалён и сессия закрыта")

app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
app.on_startup.append(lambda _: on_startup(bot))
app.on_shutdown.append(lambda _: on_shutdown(bot))

if __name__ == "__main__":
    setup_application(app, dp, bot=bot)
    web.run_app(app, port=PORT)
