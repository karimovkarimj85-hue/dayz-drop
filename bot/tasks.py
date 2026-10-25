"""Фоновые задачи: напоминание об оплате, автоотмена, вечерний отчёт с бэкапом, рассылки."""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram.types import BufferedInputFile
from sqlalchemy import select

import finance
import keyboards
import services
import texts
from config import ADMIN_IDS
from db import Order, Session, User, aware, now
from loader import bot

log = logging.getLogger(__name__)


async def check_unpaid() -> None:
    async with Session() as session:
        settings = await services.get_settings(session)
        remind_after = timedelta(hours=settings["remind_hours"])
        cancel_after = timedelta(hours=settings["cancel_hours"])
        orders = list((await session.execute(
            select(Order).where(Order.status == "awaiting_payment", Order.payment_method != "cash")
        )).scalars())
        for order in orders:
            age = now() - aware(order.created_at)
            if settings["cancel_hours"] and age >= cancel_after:
                await services.change_status(session, order, "cancelled", actor="Автоотмена")
                await services.notify_admins(texts.auto_cancelled_admin(order))
            elif settings["remind_hours"] and age >= remind_after and not order.reminded_at:
                order.reminded_at = now()
                await session.commit()
                left = max(1, int((cancel_after - age).total_seconds() // 3600)) if settings["cancel_hours"] else None
                await services.safe_send(order.user_id, texts.payment_reminder(order, settings["currency"], left),
                                         reply_markup=keyboards.order_kb(order.id))


async def daily_report() -> None:
    async with Session() as session:
        settings = await services.get_settings(session)
        local = datetime.now(services.LOCAL_TZ)
        today = local.strftime("%Y-%m-%d")
        if local.hour < settings["report_hour"] or settings["last_report_date"] == today:
            return
        await services.set_setting(session, "last_report_date", today)
        await session.commit()
        text = await finance.daily_report_text(session)
        backup, filename = await finance.backup_zip(session)
    for admin_id in ADMIN_IDS:
        await services.safe_send(admin_id, text)
        try:
            await bot.send_document(admin_id, BufferedInputFile(backup, filename=filename),
                                    caption="💾 Резервная копия базы за сегодня", disable_notification=True)
        except Exception as exc:
            log.warning("backup to %s failed: %s", admin_id, exc)


async def run_forever() -> None:
    while True:
        for job in (check_unpaid, daily_report):
            try:
                await job()
            except Exception:
                log.exception("background job %s failed", job.__name__)
        await asyncio.sleep(60)


# ---------- рассылка ----------

async def broadcast(admin_id: int, text: str, photo: str | None, audience: str, with_button: bool) -> None:
    """Отправляет сообщение всем пользователям бота (или только зарегистрированным) с паузами против лимитов."""
    async with Session() as session:
        query = select(User.id)
        if audience == "registered":
            query = query.where(User.registered_at.is_not(None))
        user_ids = [row[0] for row in (await session.execute(query)).all()]
    markup = keyboards.shop_open_kb() if with_button else None
    sent = 0
    for i, user_id in enumerate(user_ids):
        try:
            if photo:
                await bot.send_photo(user_id, photo, caption=text, reply_markup=markup)
            else:
                await bot.send_message(user_id, text, reply_markup=markup)
            sent += 1
        except Exception as exc:
            log.info("broadcast to %s skipped: %s", user_id, exc)
        if i % 20 == 19:
            await asyncio.sleep(1)  # Telegram разрешает ~30 сообщений в секунду
    await services.safe_send(admin_id, f"📣 Рассылка завершена: доставлено {sent} из {len(user_ids)}.")
