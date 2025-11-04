# Daily Sarcastic News Bot (aiogram + OpenAI Chat Completions)

A Telegram bot that posts one sarcastic news per day (11:00–14:59), using:
- aiogram v3 (long polling)
- OpenAI Chat Completions (gpt-4o-mini)
- Cities picked randomly from cities.json (no repeats)
- Items picked randomly from items.json (no repeats)
- Persistent history in bot_data/history.json

## Requirements

- Python 3.10+
- Telegram bot token
- OpenAI API key
- Files:
  - `cities.json` — array of objects with at least the `name` field:
    ```
    [
      { "name": "Углич", "district_id": 1, "region_id": 76, "coordinates": "57.5285873,38.2312432" },
      { "name": "Ярославль", "district_id": 1, "region_id": 76, "coordinates": "57.6525163,39.5843354" }
    ]
    ```
  - `items.json` — array of strings:
    ```
    [
      "ручка",
      "карандаш",
      "маркер"
    ]
    ```

## Environment

Create `.env`:
```
TELEGRAM_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
CHANNEL_ID=@your_channel # optional; leave empty to send to bot self chat
```


## Installation (local)
```
python -m venv .venv
source .venv/bin/activate
pip install aiogram openai
python main.py
```

## `requirements.txt`:
```text

aiogram==3.13.1
openai==1.54.3
```

## Docker

`Dockerfile` example:
```
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

Ensure data dir exists
RUN mkdir -p /app/bot_data

CMD ["python", "-u", "main.py"]
```


`docker-compose.yml` example:

```yaml

version: "3.8"

services:
  telegram-bot:
    build: .
    container_name: news_bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - /root/chto/data:/app/bot_data
    working_dir: /app

```

## Run:
```text
docker compose up -d --build
docker compose logs -f news_bot
```


## Commands
```text

- `/start` — short help
- `/news` — send a news immediately (still respects no-repeats)
- `/stats` — show usage stats and last send date
```


## Scheduling details

- The bot schedules exactly one message per day at a random time between 11:00 and 14:59.
- A guard file `bot_data/last_sent.txt` ensures only one send per day.
- If the bot restarts, it recomputes the next target time and still guarantees at most one send per day.

## Notes

- Prompts are in Russian by design (per project requirements).
- Logs: in Docker, using `-u` (unbuffered) and `PYTHONUNBUFFERED=1` ensures `print()` appears in `docker logs`.
- If all cities/items are exhausted, the bot resets the corresponding history list and continues.