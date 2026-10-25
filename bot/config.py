import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}

# Адрес мини-аппа на GitHub Pages, например https://user.github.io/dayz-drop/
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

# Локально — файл SQLite, на сервере — строка подключения Neon Postgres
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///dayzdrop.db")

# Публичный адрес этого сервера. На Render подставляется сам (RENDER_EXTERNAL_URL).
# Если задан — бот работает через вебхук, иначе через polling (локальный запуск).
BASE_URL = (os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")

PORT = int(os.getenv("PORT", "8080"))

# Для локальной проверки API без запуска самого бота
DISABLE_BOT = os.getenv("DISABLE_BOT") == "1"
