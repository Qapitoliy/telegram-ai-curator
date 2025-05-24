import os
import json
import logging
import aiohttp
import boto3
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

# Проверка обязательных переменных окружения
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

def load_memory():
    try:
        logging.info(f"Пытаемся загрузить {MEMORY_FILE} из бакета {BUCKET_NAME}...")
        s3.download_file(BUCKET_NAME, MEMORY_FILE, MEMORY_FILE)
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logging.info("Память успешно загружена.")
        return data
    except s3.exceptions.NoSuchKey:
        logging.warning("Файл памяти не найден в бакете, создаём новую память.")
        return {}
    except Exception as e:
        logging.warning(f"Не удалось загрузить память: {e}")
        return {}

def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        logging.info(f"Загружаем {MEMORY_FILE} в бакет {BUCKET_NAME}...")
        s3.upload_file(MEMORY_FILE, BUCKET_NAME, MEMORY_FILE)
        logging.info("Память успешно сохранена.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении памяти: {e}")

memory = load_memory()

async def ask_groq(user_id: str, user_text: str) -> str:
    history = memory.get(user_id, [])
    history.append({"role": "user", "content": user_text})

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

    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=json_data) as response:
            result = await response.json()
            try:
                reply = result["choices"][0]["message"]["content"]
                history.append({"role": "assistant", "content": reply})
                memory[user_id] = history
                save_memory(memory)
                return reply
            except Exception:
                logging.error(f"Ошибка в ответе Groq: {result}")
                return "Извините, произошла ошибка при обработке вашего запроса."

@dp.message_handler()
async def handle_message(message: types.Message):
    user_id = str(message.from_user.id)
    response = await ask_groq(user_id, message.text)
    await message.answer(response, parse_mode=ParseMode.HTML)

async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    setup_application(app, dp, bot=bot)
    web.run_app(app, port=PORT)
