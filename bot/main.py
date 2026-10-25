import asyncio
import hashlib
import logging

from aiohttp import ClientSession, web
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import api_admin
import tasks
from api import cors_middleware, routes
from config import BASE_URL, BOT_TOKEN, DISABLE_BOT, PORT, WEBAPP_URL
from db import init_db
import admin_bot
import shop_bot
from handlers import misc_router, router
from loader import bot, dp

log = logging.getLogger("dayzdrop")

WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:32]


async def setup_bot() -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="catalog", description="Каталог"),
            BotCommand(command="cart", description="Корзина"),
            BotCommand(command="orders", description="Мои заказы"),
            BotCommand(command="profile", description="Профиль и баллы"),
            BotCommand(command="support", description="Написать в поддержку"),
            BotCommand(command="help", description="Как сделать заказ"),
        ]
    )
    if WEBAPP_URL:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Магазин", web_app=WebAppInfo(url=WEBAPP_URL))
        )


async def keep_awake() -> None:
    """Бесплатный Render засыпает через 15 минут без запросов — пингуем сами себя."""
    async with ClientSession() as http:
        while True:
            await asyncio.sleep(600)
            try:
                await http.get(f"{BASE_URL}/health")
            except Exception as exc:
                log.warning("keep-awake ping failed: %s", exc)


def build_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware], client_max_size=20 * 1024 * 1024)
    app.add_routes(routes)
    app.add_routes(api_admin.routes)
    return app


def run_webhook() -> None:
    app = build_app()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    async def on_startup(_: web.Application) -> None:
        await init_db()
        await setup_bot()
        await bot.set_webhook(
            f"{BASE_URL}{WEBHOOK_PATH}",
            secret_token=WEBHOOK_SECRET,
            allowed_updates=dp.resolve_used_update_types(),
        )
        app["keep_awake"] = asyncio.create_task(keep_awake())
        app["tasks"] = asyncio.create_task(tasks.run_forever())
        log.info("webhook mode: %s", BASE_URL)

    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=PORT)


async def run_local() -> None:
    await init_db()
    runner = web.AppRunner(build_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("API on http://localhost:%s", PORT)
    if DISABLE_BOT:
        await asyncio.Event().wait()
    await setup_bot()
    asyncio.create_task(tasks.run_forever())
    await bot.delete_webhook()
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Порядок важен: команды → админка → магазин → чеки и «не понял»
    dp.include_routers(router, admin_bot.router, shop_bot.router, misc_router)
    if BASE_URL:
        run_webhook()
    else:
        asyncio.run(run_local())
