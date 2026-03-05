import os
import asyncio
import random
import datetime
import json
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import AsyncOpenAI


# ===================== Configuration =====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")

# Paths and files
DATA_DIR = Path("bot_data")
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.json"
LAST_SENT_FILE = DATA_DIR / "last_sent.txt"
CITIES_FILE = Path("cities.json")
ITEMS_FILE = Path("items.json")

# OpenRouter client with OpenAI SDK
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "X-Title": "@chto_dostali_bot",
    }
)
dp = Dispatcher()

# Варианты для рандомизации (константы, не выбранные значения)
TONES = [
    "злой сарказм", "чёрный юмор", "наивное удивление", "журналистская серьёзность", 
    "панибратство", "в стиле udaff.com", "занудство профессора", "пафосный героизм",
    "слёзная мелодрама", "детская непосредственность", "военная отчётность", 
    "репортаж с места событий", "зависть соседа", "гордость матери",
    "обида бывшей", "восторг блогера", "крик о помощи", "философская ипостась",
    "голос свыше", "шёпот сумасшедшего", "инструкция из ГОСТа",
    "рецензия кинокритика", "отчёт прокуратуры", "дневник подростка",
    "романтический эпос", "агрессивный маркетинг", "научная фантастика",
    "сказка на ночь", "объявление в подъезде", "пересказ пьяного друга"
]

RETRY_DELAYS = [1, 5, 10, 15, 20, 25, 30]


# ===================== Storage / utilities =====================

def load_history() -> dict:
    """Load history of used items and cities from disk."""
    if not HISTORY_FILE.exists():
        return {"items": [], "cities": []}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_history(history: dict):
    """Persist history to disk."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_last_sent_date() -> str:
    """Load last send date (YYYY-MM-DD) from disk."""
    if not LAST_SENT_FILE.exists():
        return ""
    return LAST_SENT_FILE.read_text(encoding="utf-8").strip()

def save_last_sent_date(date_str: str):
    """Persist last send date to disk."""
    LAST_SENT_FILE.write_text(date_str, encoding="utf-8")

def was_sent_today() -> bool:
    """Return True if a news message was already sent today."""
    return load_last_sent_date() == datetime.date.today().isoformat()

def load_cities_list() -> list:
    """Load cities array from cities.json. Supports both [{...}] and {"cities":[...]} formats."""
    if not CITIES_FILE.exists():
        raise RuntimeError(f"File {CITIES_FILE} not found")
    with open(CITIES_FILE, "r", encoding="utf-8") as f:
        cities = json.load(f)
    if isinstance(cities, dict) and "cities" in cities:
        cities = cities["cities"]
    if not isinstance(cities, list):
        raise RuntimeError("cities.json must be an array of objects with a 'name' field")
    for c in cities:
        if "name" not in c:
            raise RuntimeError("Each city object must contain the 'name' field")
    return cities

def load_items_list() -> list:
    """Load items array from items.json. Must be an array of strings."""
    if not ITEMS_FILE.exists():
        raise RuntimeError(f"File {ITEMS_FILE} not found")
    with open(ITEMS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise RuntimeError('items.json must be an array of strings, e.g.: ["ручка", "карандаш"]')
    return data


# ===================== Unique selection (no repeats) =====================

async def pick_city(cities_list: list) -> str:
    """Pick a non-repeating city from the provided list; reset history if exhausted."""
    history = load_history()
    used = set(map(str.lower, history.get("cities", [])))
    pool = [c for c in cities_list if c.get("name", "").lower() not in used]
    if not pool:
        # All cities used — reset city history
        history["cities"] = []
        save_history(history)
        pool = cities_list
    chosen = random.choice(pool)["name"]
    history["cities"].append(chosen)
    save_history(history)
    print(f"[CITY] {chosen}")
    return chosen

async def pick_item(items_list: list) -> str:
    """Pick a non-repeating item from the provided list; reset history if exhausted."""
    history = load_history()
    used = set(map(str.lower, history.get("items", [])))
    pool = [i for i in items_list if i.lower() not in used]
    if not pool:
        # All items used — reset item history
        history["items"] = []
        save_history(history)
        pool = items_list
    chosen = random.choice(pool)
    history["items"].append(chosen)
    save_history(history)
    print(f"[ITEM] {chosen}")
    return chosen


# ===================== News generation (Chat Completions) =====================

async def generate_news_chat(city: str, item: str) -> str:
    """Generate a sarcastic short news text using OpenAI Chat Completions (prompt in Russian)."""
    
    # 🔥 РАНДОМИЗАЦИЯ ПРОИСХОДИТ ЗДЕСЬ, ПРИ КАЖДОМ ВЫЗОВЕ
    chosen_tone = random.choice(TONES)

    
    prompt = f"""Пожалуйста, сгенерируй короткую саркастическую новость (3–4 предложения) в стиле {chosen_tone} о забавном медицинском случае в России.

        Требования:
        - Город: {city}
        - Предмет: {item}
        - Опиши, как житель этого города засунул этот {item} в задницу.
        - Локацию придумай каждый раз заново и впиши естественно в текст (без списков).
        - "Специалиста" (друга, копа, врача или случайного спасателя) придумай заново и впиши естественно в текст (без списков) — пусть будет колоритный тип вроде "дядя Вася из соседнего подъезда" или "проктолог с TikTok".
        - Исход случайный: успешно (75%) или 'эпик фейл' (25%).
        - С вероятностью 30% добавь короткую смешную цитату в кавычках от героя или "специалиста"
        - Начни с заголовка в формате: 🚑 {city}: [краткое описание].

        Пиши остроумно, с сарказмом и лёгким матом. Каждый элемент делай уникальным при каждом запуске. 
        Добавь абсурда и самоиронии, чтоб было ржачно, но не переигрывай.
        Обязательно используй эти параметры, но не упоминай их явно в тексте."""
    
    print(f"[DEBUG] Requesting news for {city} / {item}...")
    
    resp = await client.chat.completions.create(
        model="arcee-ai/trinity-large-preview:free",
        # model="tngtech/deepseek-r1t2-chimera",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=2000,
    )
    
    finish_reason = resp.choices[0].finish_reason
    content = resp.choices[0].message.content
    content = (content or "").strip()
    
    print(f"[DEBUG] Finish reason: {finish_reason}")
    print(f"[DEBUG] Length: {len(content)} chars")
    
    if finish_reason == "length":
        content += "\n\n(текст оборван по лимиту токенов)"
        
    return content


async def generate_news_with_retries(city: str, item: str) -> tuple[str, bool]:
    """
    Генерирует новость с повторными попытками при ошибках.
    Возвращает кортеж (текст, успех).
    """
    last_error = None
    
    for attempt, delay_minutes in enumerate(RETRY_DELAYS):
        try:
            print(f"[RETRY] Попытка {attempt + 1}/{len(RETRY_DELAYS)} для {city}/{item}")
            result = await generate_news_chat(city, item)
            print(f"[RETRY] Успех на попытке {attempt + 1}")
            return result, True
            
        except Exception as e:
            last_error = e
            print(f"[RETRY ERROR] Попытка {attempt + 1} не удалась: {e}")
            
            if attempt < len(RETRY_DELAYS) - 1:
                delay_seconds = delay_minutes * 60
                print(f"[RETRY] Ожидание {delay_minutes} минут перед следующей попыткой...")
                await asyncio.sleep(delay_seconds)
    
    print(f"[RETRY] Все попытки исчерпаны. Последняя ошибка: {last_error}")
    return str(last_error), False


# ===================== Sending and scheduling =====================
async def notify_admin(bot: Bot, message: str):
    if not ADMIN_ID:
        print(f"[ADMIN NOTIFY] ADMIN_ID не установлен, сообщение: {message}")
        return
    
    try:
        await bot.send_message(ADMIN_ID, message)
        print(f"[ADMIN NOTIFY] Уведомление отправлено админу")
    except Exception as e:
        print(f"[ADMIN NOTIFY ERROR] Не удалось отправить уведомление админу: {e}")


async def send_daily_news(bot: Bot, cities_list: list, items_list: list):
    """Send exactly one message per day; skip if already sent today."""
    if was_sent_today():
        print(f"[SEND] Already sent today")
        return
    city = await pick_city(cities_list)
    item = await pick_item(items_list)
    
    text, success = await generate_news_with_retries(city, item)    
    if not success:
        error_message = (
            f"⚠️ <b>Ошибка генерации новости</b>\n\n"
            f"Город: {city}\n"
            f"Предмет: {item}\n"
            f"Все {len(RETRY_DELAYS)} попытки исчерпаны.\n"
            f"Последняя ошибка: {text}\n\n"
            f"Новость в канал не отправлена."
        )
        await notify_admin(bot, error_message)
        print(f"[SEND] ❌ Генерация не удалась, админ уведомлён")
        return
    
    target = CHANNEL_ID or (await bot.get_me()).id
    await bot.send_message(target, text)
    save_last_sent_date(datetime.date.today().isoformat())
    print(f"[SEND] ✅ {datetime.datetime.now()}")

async def schedule_daily_news(bot: Bot, cities_list: list, items_list: list):
    """Schedule sending at a random time between 11:00 and 14:59 once per day."""
    while True:
        now = datetime.datetime.now()
        today = now.date()
        if was_sent_today():
            # Plan for the next day
            tomorrow = today + datetime.timedelta(days=1)
            hour = random.randint(11, 14)
            minute = random.randint(0, 59)
            target_time = datetime.datetime.combine(tomorrow, datetime.time(hour, minute))
        else:
            # Plan for today if still within window; else plan for tomorrow
            hour = random.randint(11, 14)
            minute = random.randint(0, 59)
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now or now.hour >= 15:
                tomorrow = today + datetime.timedelta(days=1)
                hour = random.randint(11, 14)
                minute = random.randint(0, 59)
                target_time = datetime.datetime.combine(tomorrow, datetime.time(hour, minute))
        wait_seconds = (target_time - now).total_seconds()
        print(f"[SCHEDULER] Next run: {target_time} (in {wait_seconds/3600:.2f} h)")
        await asyncio.sleep(wait_seconds)
        if not was_sent_today():
            await send_daily_news(bot, cities_list, items_list)


# ===================== Bot commands =====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Start command: basic help text."""
    await message.answer(
        "🤖 Бот публикует ежедневные новости.\n"
        "/news — отправить новость сейчас\n"
        "/stats — статистика"
    )

@dp.message(Command("news"))
async def cmd_news(message: types.Message):
    """Generate and send a news message immediately."""
    try:
        cities_list = load_cities_list()
        items_list = load_items_list()
        city = await pick_city(cities_list)
        item = await pick_item(items_list)
        text, success = await generate_news_with_retries(city, item)
        
        if not success:
            await message.answer(f"❌ Не удалось сгенерировать новость после {len(RETRY_DELAYS)} попыток. Ошибка: {text}")
            return
            
        await message.answer(text)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Show usage statistics for cities/items and last send date."""
    h = load_history()
    await message.answer(
        f"📊 Города использованы: {len(h.get('cities', []))}\n"
        f"📦 Предметы использованы: {len(h.get('items', []))}\n"
        f"📅 Последняя отправка: {load_last_sent_date() or 'никогда'}\n"
        f"✅ Сегодня: {'да' if was_sent_today() else 'нет'}"
    )


# ===================== main =====================

async def main():
    """Entrypoint: validate config, start scheduler and polling."""
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set")
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    cities_list = load_cities_list()
    items_list = load_items_list()
    if not cities_list:
        raise RuntimeError("cities.json is empty or missing")
    if not items_list:
        raise RuntimeError("items.json is empty or missing")

    bot = Bot(token=TELEGRAM_TOKEN)

    scheduler_task = asyncio.create_task(schedule_daily_news(bot, cities_list, items_list))
    try:
        print("🚀 Bot started (OpenRouter)")
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())