import os
import json
import logging
import aiohttp
import aioboto3
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# === Настройки логирования ===
logging.basicConfig(level=logging.INFO)

# === Загрузка переменных окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # Изменили имя
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 10000))

BUCKET_NAME = os.getenv("BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
YC_ENDPOINT = os.getenv("YC_ENDPOINT")

# Проверка обязательных переменных
required_env = {
    "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
    "OPENROUTER_API_KEY": OPENROUTER_API_KEY,  # Теперь здесь
    "WEBHOOK_HOST": WEBHOOK_HOST,
    "BUCKET_NAME": BUCKET_NAME,
    "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "YC_ENDPOINT": YC_ENDPOINT,
}

for k, v in required_env.items():
    if not v:
        logging.error(f"Переменная окружения {k} не установлена!")
        exit(1)

# === Инициализация бота и диспетчера ===
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# === Асинхронный клиент S3 ===
session_s3 = aioboto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

MEMORY_FILE = "user_memory.json"
MAX_HISTORY_LEN = 50
HISTORY_TO_MODEL = 10  # Сколько последних сообщений отправлять модели

memory = {}
memory_lock = asyncio.Lock()
memory_queue = asyncio.Queue()

async def load_memory():
    global memory
    try:
        async with session_s3.client("s3", endpoint_url=YC_ENDPOINT) as s3:
            response = await s3.get_object(Bucket=BUCKET_NAME, Key=MEMORY_FILE)
            async with response["Body"] as stream:
                data = await stream.read()
                memory = json.loads(data.decode("utf-8"))
        logging.info("Память успешно загружена.")
    except Exception as e:
        logging.warning(f"Ошибка загрузки памяти: {e}, создаём новую.")
        memory = {}

async def save_memory_worker():
    while True:
        data = await memory_queue.get()
        try:
            async with session_s3.client("s3", endpoint_url=YC_ENDPOINT) as s3:
                await s3.put_object(
                    Bucket=BUCKET_NAME,
                    Key=MEMORY_FILE,
                    Body=json.dumps(data, ensure_ascii=False, indent=2),
                    ContentType="application/json"
                )
            logging.info("Память успешно сохранена в S3.")
        except Exception as e:
            logging.error(f"Ошибка при сохранении памяти: {e}")
        finally:
            memory_queue.task_done()

def schedule_save():
    asyncio.create_task(memory_queue.put(memory.copy()))

# === HTTP-сессия для OpenRouter ===
session_http = None

async def get_session():
    global session_http
    if session_http is None or session_http.closed:
        session_http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return session_http

# === Логика OpenRouter ===
async def ask_openrouter(user_id: str, user_text: str) -> str:
    session = await get_session()

    async with memory_lock:
        history = memory.get(user_id, [])
        history.append({"role": "user", "content": user_text})
        if len(history) > MAX_HISTORY_LEN:
            history = history[-MAX_HISTORY_LEN:]
        memory[user_id] = list(history)  # поверхностная копия

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": WEBHOOK_HOST or "https://your-app-url.com ",
        "X-Title": "Telegram AI Bot",
        "Content-Type": "application/json"
    }

    json_data = {
        "model": "mistralai/mistral-7b-instruct:free",  # Бесплатная модель
        "messages": [
            {"role": "system", "content": "Ты — дружелюбный Telegram-бот с ИИ, запоминающий общение с пользователем."}
        ] + history[-HISTORY_TO_MODEL:]
    }

    try:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions ",
            headers=headers,
            json=json_data
        ) as response:
            if response.status != 200:
                text = await response.text()
                logging.error(f"Ошибка API OpenRouter {response.status}: {text}")
                return "Ошибка сервиса, попробуйте позже."

            result = await response.json()
            reply = result["choices"][0]["message"]["content"]

        async with memory_lock:
            history.append({"role": "assistant", "content": reply})
            memory[user_id] = list(history)
        schedule_save()

        return reply

    except Exception as e:
        logging.error(f"Ошибка при запросе к OpenRouter: {e}")
        return "Произошла ошибка при обработке вашего запроса."

# === Обработчик сообщений ===
@dp.message()
async def handle_message(message: types.Message):
    user_id = str(message.from_user.id)
    if not message.text:
        await message.answer("Поддерживаются только текстовые сообщения.")
        return

    try:
        response = await ask_openrouter(user_id, message.text)
        await message.answer(response, parse_mode=ParseMode.NONE)  # Отключаем HTML
    except Exception as e:
        logging.error(f"Ошибка в обработчике сообщений: {e}")
        await message.answer("Произошла ошибка при обработке вашего сообщения. Попробуйте позже.")

# === Webhook setup ===
async def on_startup(app):
    await load_memory()
    asyncio.create_task(save_memory_worker())
    logging.info("Устанавливаем webhook...")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    logging.info("Удаляем webhook...")
    await bot.delete_webhook()
    if session_http and not session_http.closed:
        await session_http.close()
    await memory_queue.join()

# === Health check для Render ===
async def health_check(request):
    return web.Response(text="OK")

# === Создание и настройка приложения ===
app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

# Добавим маршрут /health для проверки Render
app.router.add_get("/health", health_check)

# === Точка входа ===
if __name__ == "__main__":
    setup_application(app, dp, bot=bot)
    web.run_app(app, host='0.0.0.0', port=PORT)
