import os
import json
import logging
import aiohttp
import boto3
import asyncio
from botocore.exceptions import ClientError
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 10000))

BUCKET_NAME = os.getenv("BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
YC_ENDPOINT = os.getenv("YC_ENDPOINT")

logging.basicConfig(level=logging.INFO)

required_env = {
    "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
    "GROQ_API_KEY": GROQ_API_KEY,
    "WEBHOOK_HOST": WEBHOOK_HOST,
    "BUCKET_NAME": BUCKET_NAME,
    "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "YC_ENDPOINT": YC_ENDPOINT,
}

for k, v in required_env.items():
    if v is None:
        logging.error(f"Переменная окружения {k} не установлена!")
        exit(1)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

s3 = boto3.client(
    's3',
    endpoint_url=YC_ENDPOINT,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

MEMORY_FILE = "user_memory.json"
MAX_HISTORY_LEN = 50  # Максимальное количество сообщений в истории пользователя

def load_memory():
    try:
        logging.info(f"Пытаемся загрузить {MEMORY_FILE} из бакета {BUCKET_NAME}...")
        s3.download_file(BUCKET_NAME, MEMORY_FILE, MEMORY_FILE)
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logging.info("Память успешно загружена.")
        return data
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            logging.warning("Файл памяти не найден в бакете, создаём новую память.")
            return {}
        else:
            logging.warning(f"Ошибка загрузки памяти: {e}")
            return {}
    except Exception as e:
        logging.warning(f"Ошибка загрузки памяти: {e}")
        return {}

memory = load_memory()

async def save_memory_async(data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info(f"Загружаем {MEMORY_FILE} в бакет {BUCKET_NAME}...")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, s3.upload_file, MEMORY_FILE, BUCKET_NAME, MEMORY_FILE)
        logging.info("Память успешно сохранена.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении памяти: {e}")

# Глобальная переменная для aiohttp-сессии
session: aiohttp.ClientSession | None = None

async def get_session() -> aiohttp.ClientSession:
    global session
    if session is None or session.closed:
        logging.info("Инициализация новой aiohttp.ClientSession...")
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return session

async def ask_groq(user_id: str, user_text: str) -> str:
    session = await get_session()

    history = memory.get(user_id, [])
    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_HISTORY_LEN:
        history = history[-MAX_HISTORY_LEN:]

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    json_data = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": "Ты — дружелюбный Telegram-бот с ИИ, запоминающий общение с пользователем."}
        ] + history[-10:]
    }

    try:
        async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=json_data) as response:
            if response.status != 200:
                text = await response.text()
                logging.error(f"Ошибка API Groq {response.status}: {text}")
                return "Ошибка сервиса, попробуйте позже."

            result = await response.json()
            reply = result["choices"][0]["message"]["content"]
            history.append({"role": "assistant", "content": reply})
            memory[user_id] = history
            asyncio.create_task(save_memory_async(memory))
            return reply
    except Exception as e:
        logging.error(f"Ошибка при запросе к Groq API: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса."

@dp.message()
async def handle_message(message: types.Message):
    user_id = str(message.from_user.id)
    try:
        response = await ask_groq(user_id, message.text)
        await message.answer(response, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Ошибка в обработчике сообщений: {e}")
        await message.answer("Произошла ошибка при обработке вашего сообщения. Попробуйте позже.")

async def on_startup(app):
    global session
    if session is None or session.closed:
        logging.info("Создаём aiohttp.ClientSession на старте...")
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    logging.info("Устанавливаем webhook...")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    global session
    logging.info("Удаляем webhook...")
    await bot.delete_webhook()
    if session and not session.closed:
        logging.info("Закрываем aiohttp.ClientSession...")
        await session.close()
        session = None

app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    setup_application(app, dp, bot=bot)
    web.run_app(app, port=PORT)
