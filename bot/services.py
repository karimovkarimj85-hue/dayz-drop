"""Логика магазина: заказы, остатки, ручная проверка оплаты, уведомления."""
import logging

from aiogram.types import BufferedInputFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import keyboards
import texts
from config import ADMIN_IDS
from db import Cart, Order, Product, Setting, User
from loader import bot

log = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "payment_details": "Реквизиты ещё не заданы — админ добавит их в настройках.",
    "currency": "₽",
    "delivery_options": "СДЭК\nПочта\nСамовывоз",
    "support_contact": "",
    "about": "DAYZ DROP — одежда, которую не встретишь на каждом.",
}

# Из какого статуса в какой можно перевести заказ
TRANSITIONS = {
    "awaiting_payment": {"checking", "paid", "cancelled"},
    "checking": {"paid", "awaiting_payment", "cancelled"},
    "paid": {"shipped", "done", "cancelled"},
    "shipped": {"done", "cancelled"},
    "done": set(),
    "cancelled": set(),
}


class ShopError(Exception):
    """Ошибка, текст которой можно показать пользователю."""


# ---------- настройки ----------

async def get_settings(session: AsyncSession) -> dict:
    rows = (await session.execute(select(Setting))).scalars().all()
    data = dict(DEFAULT_SETTINGS)
    data.update({r.key: r.value for r in rows})
    return data


async def save_settings(session: AsyncSession, values: dict) -> dict:
    for key in DEFAULT_SETTINGS:
        if key not in values:
            continue
        value = str(values[key] or "").strip()
        row = await session.get(Setting, key)
        if row:
            row.value = value
        else:
            session.add(Setting(key=key, value=value))
    await session.commit()
    return await get_settings(session)


def delivery_options(settings: dict) -> list[str]:
    return [x.strip() for x in settings["delivery_options"].splitlines() if x.strip()]


# ---------- пользователи ----------

async def upsert_user(session: AsyncSession, tg_user) -> None:
    user = await session.get(User, tg_user.id)
    if user:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
    else:
        session.add(User(id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name))
    await session.commit()


# ---------- корзина в боте ----------

async def get_cart(session: AsyncSession, user_id: int) -> list[dict]:
    cart = await session.get(Cart, user_id)
    return [dict(i) for i in cart.items] if cart else []


async def set_cart(session: AsyncSession, user_id: int, items: list[dict]) -> None:
    cart = await session.get(Cart, user_id)
    if cart:
        cart.items = list(items)
    else:
        session.add(Cart(user_id=user_id, items=list(items)))
    await session.commit()


async def cart_lines(session: AsyncSession, user_id: int) -> list[dict]:
    """Корзина с актуальными товарами: убирает пропавшее и подрезает количество под остаток."""
    items = await get_cart(session, user_id)
    lines, cleaned = [], []
    for item in items:
        product = await session.get(Product, item["product_id"])
        if not product or not product.is_active:
            continue
        entry = _size_entry(product.sizes, item["size"])
        if not entry or entry["stock"] <= 0:
            continue
        qty = min(item["qty"], entry["stock"])
        cleaned.append({"product_id": product.id, "size": item["size"], "qty": qty})
        lines.append({"product": product, "size": item["size"], "qty": qty, "stock": entry["stock"]})
    if cleaned != items:
        await set_cart(session, user_id, cleaned)
    return lines


async def active_products(session: AsyncSession) -> list[Product]:
    return list(
        (
            await session.execute(
                select(Product).where(Product.is_active.is_(True)).order_by(Product.sort, Product.id.desc())
            )
        ).scalars()
    )


# ---------- уведомления ----------

async def safe_send(chat_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception as exc:  # пользователь заблокировал бота и т.п. — заказ от этого ломаться не должен
        log.warning("send to %s failed: %s", chat_id, exc)


async def notify_admins(text: str, **kwargs) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send(admin_id, text, **kwargs)


# ---------- заказы ----------

def _size_entry(sizes: list, size: str) -> dict | None:
    return next((s for s in sizes if s["size"] == size), None)


async def create_order(session: AsyncSession, tg_user, data: dict) -> Order:
    settings = await get_settings(session)

    name = str(data.get("customer_name") or "").strip()[:200]
    phone = str(data.get("phone") or "").strip()[:50]
    delivery = str(data.get("delivery") or "").strip()[:100]
    address = str(data.get("address") or "").strip()[:1000]
    comment = str(data.get("comment") or "").strip()[:1000]
    if not name or not phone:
        raise ShopError("Укажи имя и телефон")
    if delivery not in delivery_options(settings):
        raise ShopError("Выбери способ доставки")
    if "самовывоз" not in delivery.lower() and not address:
        raise ShopError("Укажи адрес доставки")

    # Схлопываем одинаковые позиции (товар + размер)
    wanted: dict[tuple[int, str], int] = {}
    for item in data.get("items") or []:
        try:
            key = (int(item["product_id"]), str(item["size"]))
            qty = int(item["qty"])
        except (KeyError, TypeError, ValueError):
            raise ShopError("Некорректная корзина")
        if qty < 1:
            continue
        wanted[key] = wanted.get(key, 0) + qty
    if not wanted:
        raise ShopError("Корзина пуста")

    items, total = [], 0
    for (product_id, size), qty in wanted.items():
        product = await session.get(Product, product_id, with_for_update=True)
        if not product or not product.is_active:
            raise ShopError("Один из товаров больше недоступен — обнови корзину")
        sizes = [dict(s) for s in product.sizes]
        entry = _size_entry(sizes, size)
        if not entry:
            raise ShopError(f"Размера {size} у «{product.title}» больше нет")
        if entry["stock"] < qty:
            left = entry["stock"]
            raise ShopError(f"«{product.title}», размер {size}: осталось только {left} шт.")
        entry["stock"] -= qty
        product.sizes = sizes  # новый список, чтобы SQLAlchemy заметил изменение JSON
        items.append(
            {
                "product_id": product.id,
                "title": product.title,
                "size": size,
                "qty": qty,
                "price": product.price,
                "photo": product.photos[0] if product.photos else None,
            }
        )
        total += product.price * qty

    order = Order(
        user_id=tg_user.id,
        username=tg_user.username,
        customer_name=name,
        phone=phone,
        delivery=delivery,
        address=address,
        comment=comment,
        items=items,
        total=total,
    )
    session.add(order)
    await session.commit()

    await safe_send(order.user_id, texts.order_created(order, settings), reply_markup=keyboards.order_kb(order.id))
    await notify_admins(
        texts.admin_new_order(order, settings["currency"]), reply_markup=keyboards.admin_order_kb(order.id)
    )
    return order


async def _restore_stock(session: AsyncSession, order: Order) -> None:
    for item in order.items:
        product = await session.get(Product, item["product_id"], with_for_update=True)
        if not product:
            continue
        sizes = [dict(s) for s in product.sizes]
        entry = _size_entry(sizes, item["size"])
        if entry:
            entry["stock"] += item["qty"]
        else:
            sizes.append({"size": item["size"], "stock": item["qty"]})
        product.sizes = sizes


async def change_status(session: AsyncSession, order: Order, status: str, track: str | None = None) -> Order:
    if status not in TRANSITIONS:
        raise ShopError("Неизвестный статус")
    if status != order.status and status not in TRANSITIONS[order.status]:
        raise ShopError(
            f"Нельзя перевести заказ из «{texts.STATUS_LABELS[order.status]}» в «{texts.STATUS_LABELS[status]}»"
        )
    if status == "cancelled" and order.status != "cancelled":
        await _restore_stock(session, order)
    if track is not None:
        order.track = track.strip()[:100] or None
    changed = status != order.status
    order.status = status
    await session.commit()

    if changed or track is not None:
        settings = await get_settings(session)
        text = texts.status_update(order, settings["currency"])
        if text:
            await safe_send(order.user_id, text)
    return order


async def attach_receipt(
    session: AsyncSession,
    order: Order,
    *,
    file_id: str | None = None,
    content: bytes | None = None,
    filename: str = "receipt",
    kind: str = "photo",
) -> Order:
    """Пересылает чек всем админам с кнопками подтверждения и ставит заказ на проверку."""
    if order.status not in ("awaiting_payment", "checking"):
        raise ShopError("По этому заказу чек уже не нужен")

    settings = await get_settings(session)
    caption = texts.admin_receipt(order, settings["currency"])
    markup = keyboards.receipt_admin_kb(order.id)

    sent_file_id = file_id
    for admin_id in ADMIN_IDS:
        media = sent_file_id or BufferedInputFile(content, filename=filename)
        try:
            if kind == "photo":
                msg = await bot.send_photo(admin_id, media, caption=caption, reply_markup=markup)
                sent_file_id = msg.photo[-1].file_id
            else:
                msg = await bot.send_document(admin_id, media, caption=caption, reply_markup=markup)
                sent_file_id = msg.document.file_id
        except Exception as exc:
            log.warning("receipt to admin %s failed: %s", admin_id, exc)

    if not sent_file_id:
        raise ShopError("Не получилось отправить чек. Пришли его в чат с ботом")

    order.receipt_file_id = sent_file_id
    order.receipt_kind = kind
    order.status = "checking"
    await session.commit()
    await safe_send(order.user_id, texts.RECEIPT_RECEIVED.format(id=order.id))
    return order
