import os
import asyncio
import json
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import openai

# Получаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    print("ERROR: Задай TELEGRAM_TOKEN и OPENAI_API_KEY в переменных окружения!")
    exit(1)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

MEMORY_FILE = "memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

memory = load_memory()

async def ask_openai(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=prompt,
        max_tokens=500,
        temperature=0.7,
    )
    return response.choices[0].message.content

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я твой персональный ИИ-куратор. Спрашивай что угодно.")

@dp.message_handler(commands=["memory"])
async def cmd_memory(message: types.Message):
    user_id = str(message.from_user.id)
    user_memory = memory.get(user_id, "Память пуста.")
    await message.answer(f"Твоя память:\n{user_memory}")

@dp.message_handler()
async def echo_all(message: types.Message):
    user_id = str(message.from_user.id)
    user_history = memory.get(user_id, [])
    # Формируем контекст для OpenAI
    messages = [{"role": "system", "content": "Ты персональный куратор, помогаешь с жизнью: спорт, бизнес, психологическая поддержка."}]
    # Добавляем историю из памяти
    for item in user_history[-10:]:
        messages.append(item)
    # Добавляем последнее сообщение пользователя
    messages.append({"role": "user", "content": message.text})

    answer = await ask_openai(messages)

    # Сохраняем в память
    user_history.append({"role": "user", "content": message.text})
    user_history.append({"role": "assistant", "content": answer})
    memory[user_id] = user_history
    save_memory(memory)

    await message.answer(answer)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
