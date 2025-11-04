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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")  # e.g., "@your_channel" or leave empty for bot self chat

# Paths and files
DATA_DIR = Path("bot_data")
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.json"
LAST_SENT_FILE = DATA_DIR / "last_sent.txt"
CITIES_FILE = Path("cities.json")   # array of objects: [{ "name": "Углич", ...}, ...]
ITEMS_FILE = Path("items.json")     # array of strings: ["ручка", "карандаш", "маркер"]

# OpenAI Chat Completions client
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
dp = Dispatcher()

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
    prompt = f"""Пожалуйста, сгенерируй короткую саркастическую новость (3–4 предложения) в стиле udaff.com о забавном медицинском случае в России.

Требования:
- Город: {city}
- Предмет: {item}
- Опиши, как житель этого города засунул предмет в задницу.
- Локацию придумай каждый раз заново и впиши естественно в текст (без списков).
- Специалиста также придумай заново и впиши естественно в текст (без списков).
- Исход случайный: успешно (75%) или неудачно (25%).
- С вероятностью 30% добавь короткую смешную цитату в кавычках.
- Начни с заголовка в формате: 🚑 {city}: [краткое описание].

Пиши остроумно и кратко. Каждый элемент делай уникальным при каждом запуске."""
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=500,
        )
        text = resp.choices[0].message.content.strip()
        return text
    except Exception as e:
        # Fallback to a minimal message on API error
        print(f"[NEWS ERROR] {e}")
        return f"🚑 {city}: Местный житель попал в больницу после неудачного эксперимента с предметом «{item}»."

# ===================== Sending and scheduling =====================

async def send_daily_news(bot: Bot, cities_list: list, items_list: list):
    """Send exactly one message per day; skip if already sent today."""
    if was_sent_today():
        print(f"[SEND] Already sent today")
        return
    city = await pick_city(cities_list)
    item = await pick_item(items_list)
    text = await generate_news_chat(city, item)
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
        text = await generate_news_chat(city, item)
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
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    # Validate data availability early
    cities_list = load_cities_list()
    items_list = load_items_list()
    if not cities_list:
        raise RuntimeError("cities.json is empty or missing")
    if not items_list:
        raise RuntimeError("items.json is empty or missing")

    bot = Bot(token=TELEGRAM_TOKEN)

    # Background scheduler task
    scheduler_task = asyncio.create_task(schedule_daily_news(bot, cities_list, items_list))
    try:
        print("🚀 Bot started (Chat Completions, gpt-4o-mini)")
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    # For Docker logs, consider running Python in unbuffered mode or set PYTHONUNBUFFERED=1
    asyncio.run(main())
