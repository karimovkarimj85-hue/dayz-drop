"""Логика магазина: заказы, оплата (карта/наличные), доставка, склад, уведомления."""
import json
import logging
import re
from datetime import timedelta, timezone

from aiogram.types import BufferedInputFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import keyboards
import texts
from config import ADMIN_IDS
from db import Cart, Coupon, Order, Product, Setting, StockMovement, Subscription, User, now
from loader import bot

log = logging.getLogger(__name__)

LOCAL_TZ = timezone(timedelta(hours=5))  # Ташкент, без перехода на летнее время

DEFAULT_DELIVERY = [
    {"id": "pickup", "name": "Самовывоз", "price": 0, "free_from": 0, "cash": True, "address": False,
     "note": "Ташкент — точный адрес пришлём в чат"},
    {"id": "courier", "name": "Курьер по Ташкенту", "price": 25000, "free_from": 500000, "cash": True, "address": True,
     "note": "1–2 дня"},
    {"id": "region", "name": "Доставка по Узбекистану", "price": 35000, "free_from": 0, "cash": False, "address": True,
     "note": "BTS / почта, 2–5 дней"},
]

DEFAULT_SETTINGS = {
    "currency": "сум",
    "about": "DAYZ DROP — одежда, которую не встретишь на каждом.",
    # [{"label": "Uzcard · Карим", "number": "8600 …", "holder": "Карим К.", "bank": "Kapitalbank", "active": true}]
    "cards": [],
    "delivery_methods": DEFAULT_DELIVERY,
    "remind_hours": 1,  # через сколько часов напомнить об оплате
    "cancel_hours": 24,  # через сколько часов снять неоплаченный заказ
    "low_stock": 1,  # при каком остатке размера предупреждать админов
    "report_hour": 21,  # во сколько (по Ташкенту) присылать отчёт и бэкап
    "loyalty_enabled": True,
    "earn_percent": 5,  # сколько процентов от суммы заказа возвращается баллами
    "welcome_points": 10000,  # бонус за регистрацию
    # служебные
    "card_rr": 0,
    "last_report_date": "",
    "payment_details": "",  # старый формат реквизитов, переносится в cards
}
JSON_KEYS = {"cards", "delivery_methods", "remind_hours", "cancel_hours", "low_stock", "report_hour",
             "loyalty_enabled", "earn_percent", "welcome_points", "card_rr"}
EDITABLE_KEYS = {"currency", "about", "cards", "delivery_methods", "remind_hours", "cancel_hours", "low_stock",
                 "report_hour", "loyalty_enabled", "earn_percent", "welcome_points"}

# Из какого статуса в какой можно перевести заказ
TRANSITIONS = {
    "awaiting_payment": {"checking", "paid", "cancelled"},
    "checking": {"paid", "awaiting_payment", "cancelled"},
    "confirmed": {"paid", "shipped", "done", "cancelled"},  # наличные: оплата при получении
    "paid": {"shipped", "done", "cancelled"},
    "shipped": {"done", "cancelled"},
    "done": set(),
    "cancelled": set(),
}


class ShopError(Exception):
    """Ошибка, текст которой можно показать пользователю."""


def to_int(value, default: int = 0, minimum: int | None = 0) -> int:
    try:
        number = int(str(value).replace(" ", "").replace(" ", ""))
    except (TypeError, ValueError):
        return default
    return max(minimum, number) if minimum is not None else number


# ---------- настройки ----------

def _clean_cards(raw) -> list[dict]:
    cards = []
    for c in raw if isinstance(raw, list) else []:
        number = re.sub(r"[^\d ]", "", str(c.get("number") or "")).strip()[:30]
        label = str(c.get("label") or "").strip()[:60]
        if not (number or c.get("details")):
            continue
        cards.append({
            "label": label or f"Карта {len(cards) + 1}",
            "number": number,
            "holder": str(c.get("holder") or "").strip()[:80],
            "bank": str(c.get("bank") or "").strip()[:60],
            "details": str(c.get("details") or "").strip()[:500],
            "active": bool(c.get("active", True)),
        })
    return cards


def _clean_delivery(raw) -> list[dict]:
    methods, seen = [], set()
    for m in raw if isinstance(raw, list) else []:
        name = str(m.get("name") or "").strip()[:80]
        if not name:
            continue
        slug = str(m.get("id") or "").strip()[:30] or re.sub(r"\W+", "-", name.lower()).strip("-")[:30] or "d"
        while slug in seen:
            slug += "1"
        seen.add(slug)
        methods.append({
            "id": slug,
            "name": name,
            "price": to_int(m.get("price")),
            "free_from": to_int(m.get("free_from")),
            "cash": bool(m.get("cash")),
            "address": bool(m.get("address", True)),
            "note": str(m.get("note") or "").strip()[:200],
        })
    return methods


async def get_settings(session: AsyncSession) -> dict:
    rows = {r.key: r.value for r in (await session.execute(select(Setting))).scalars()}
    data = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key not in rows:
            data[key] = default
        elif key in JSON_KEYS:
            try:
                data[key] = json.loads(rows[key])
            except (TypeError, ValueError):
                data[key] = default
        else:
            data[key] = rows[key]
    # Старые реквизиты одной строкой → первая карта
    legacy = (data.get("payment_details") or "").strip()
    if not data["cards"] and legacy and "не заданы" not in legacy:
        data["cards"] = [{"label": "Карта", "number": "", "holder": "", "bank": "", "details": legacy, "active": True}]
    if not data["delivery_methods"]:
        data["delivery_methods"] = DEFAULT_DELIVERY
    if data.get("currency") in ("₽", "", None):
        data["currency"] = "сум"
    return data


async def set_setting(session: AsyncSession, key: str, value) -> None:
    stored = json.dumps(value, ensure_ascii=False) if key in JSON_KEYS else str(value)
    row = await session.get(Setting, key)
    if row:
        row.value = stored
    else:
        session.add(Setting(key=key, value=stored))


async def save_settings(session: AsyncSession, values: dict) -> dict:
    for key, value in values.items():
        if key not in EDITABLE_KEYS:
            continue
        if key == "cards":
            value = _clean_cards(value)
        elif key == "delivery_methods":
            value = _clean_delivery(value)
            if not value:
                raise ShopError("Нужен хотя бы один способ доставки")
        elif key == "loyalty_enabled":
            value = bool(value)
        elif key in JSON_KEYS:
            value = to_int(value, DEFAULT_SETTINGS[key])
        else:
            value = str(value or "").strip()[:2000]
        await set_setting(session, key, value)
    await session.commit()
    return await get_settings(session)


def delivery_methods(settings: dict) -> list[dict]:
    return settings["delivery_methods"]


def find_delivery(settings: dict, ref) -> dict | None:
    ref = str(ref or "")
    return next((m for m in settings["delivery_methods"] if m["id"] == ref or m["name"] == ref), None)


def active_cards(settings: dict) -> list[dict]:
    return [c for c in settings["cards"] if c.get("active", True)]


def card_text(card: dict) -> str:
    if card.get("details"):
        return card["details"]
    lines = [card.get("number", "")]
    if card.get("holder"):
        lines.append(card["holder"])
    if card.get("bank"):
        lines.append(card["bank"])
    return "\n".join(l for l in lines if l)


def delivery_cost(method: dict, subtotal: int) -> int:
    if method["free_from"] and subtotal >= method["free_from"]:
        return 0
    return method["price"]


# ---------- пользователи ----------

async def upsert_user(session: AsyncSession, tg_user) -> User:
    user = await session.get(User, tg_user.id)
    if user:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
    else:
        user = User(id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name, points=0)
        session.add(user)
    await session.commit()
    return user


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
        if not product or not product.is_active or product.badge == "soon":
            continue
        entry = size_entry(product.sizes, item["size"])
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

async def safe_send(chat_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception as exc:  # пользователь заблокировал бота и т.п. — заказ от этого ломаться не должен
        log.warning("send to %s failed: %s", chat_id, exc)
        return False


async def notify_admins(text: str, **kwargs) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send(admin_id, text, **kwargs)


def add_history(order: Order, text: str, who: str | None = None) -> None:
    order.history = [*(order.history or []), {"at": now().isoformat(), "who": who, "text": text}]


# ---------- расчёт заказа ----------

def size_entry(sizes: list, size: str) -> dict | None:
    return next((s for s in sizes if s["size"] == size), None)


async def avg_cost(session: AsyncSession, product_id: int) -> int | None:
    """Средняя цена закупки товара по всем приходам с указанной ценой."""
    total, units = (
        await session.execute(
            select(func.sum(StockMovement.delta * StockMovement.cost), func.sum(StockMovement.delta)).where(
                StockMovement.product_id == product_id,
                StockMovement.kind == "receipt",
                StockMovement.cost.is_not(None),
            )
        )
    ).one()
    return int(total // units) if total and units else None


def _merge_items(raw) -> dict[tuple[int, str], int]:
    wanted: dict[tuple[int, str], int] = {}
    for item in raw or []:
        try:
            key = (int(item["product_id"]), str(item["size"]))
            qty = int(item["qty"])
        except (KeyError, TypeError, ValueError):
            raise ShopError("Некорректная корзина")
        if qty > 0:
            wanted[key] = wanted.get(key, 0) + qty
    if not wanted:
        raise ShopError("Корзина пуста")
    return wanted


async def quote(session: AsyncSession, user_id: int, data: dict, *, lock: bool = False, strict: bool = False) -> dict:
    """Считает заказ: товары, доставка, скидка по купону, итог и доступные способы оплаты.

    strict=False — для предпросмотра: ошибка купона не роняет расчёт, а возвращается полем.
    """
    from loyalty import check_coupon  # здесь, чтобы не было циклического импорта

    settings = await get_settings(session)
    lines, subtotal = [], 0
    for (product_id, size), qty in _merge_items(data.get("items")).items():
        product = await session.get(Product, product_id, with_for_update=lock)
        if not product or not product.is_active or product.badge == "soon":
            raise ShopError("Один из товаров больше недоступен — обнови корзину")
        entry = size_entry(product.sizes, size)
        if not entry:
            raise ShopError(f"Размера {size} у «{product.title}» больше нет")
        if entry["stock"] < qty:
            raise ShopError(f"«{product.title}», размер {size}: осталось только {entry['stock']} шт.")
        lines.append({"product": product, "size": size, "qty": qty})
        subtotal += product.price * qty

    methods = delivery_methods(settings)
    method = find_delivery(settings, data.get("delivery")) or (None if strict else methods[0])
    if not method:
        raise ShopError("Выбери способ доставки")
    delivery_price = delivery_cost(method, subtotal)

    user = await session.get(User, user_id)
    cards = active_cards(settings)
    cash_allowed = method["cash"] and not (user and user.no_cash)
    payments = {"card": bool(cards), "cash": cash_allowed}
    payment = data.get("payment") or ("card" if cards else "cash")
    if strict:
        if payment not in payments:
            raise ShopError("Выбери способ оплаты")
        if payment == "card" and not cards:
            raise ShopError("Оплата картой временно недоступна — выбери наличные или напиши в поддержку")
        if payment == "cash" and not method["cash"]:
            raise ShopError(f"Для «{method['name']}» доступна только предоплата картой")
        if payment == "cash" and user and user.no_cash:
            raise ShopError("Для тебя доступна только предоплата картой")

    coupon, discount, coupon_error = None, 0, None
    code = str(data.get("coupon") or "").strip()
    if code:
        try:
            coupon, discount = await check_coupon(session, code, user_id, lines, subtotal)
        except ShopError as exc:
            if strict:
                raise
            coupon_error = str(exc)

    base = subtotal - discount
    earn = 0
    if settings["loyalty_enabled"]:
        earn = base * settings["earn_percent"] // 100
    return {
        "lines": lines,
        "subtotal": subtotal,
        "discount": discount,
        "coupon": coupon,
        "coupon_error": coupon_error,
        "delivery": method,
        "delivery_price": delivery_price,
        "payment": payment,
        "payments": payments,
        "total": base + delivery_price,
        "earn_points": earn,
        "registered": bool(user and user.registered_at),
        "settings": settings,
    }


def quote_json(q: dict) -> dict:
    return {
        "subtotal": q["subtotal"],
        "discount": q["discount"],
        "coupon": q["coupon"].code if q["coupon"] else None,
        "coupon_title": q["coupon"].title if q["coupon"] else None,
        "coupon_error": q["coupon_error"],
        "delivery": q["delivery"]["id"],
        "delivery_price": q["delivery_price"],
        "payment": q["payment"],
        "payments": q["payments"],
        "total": q["total"],
        "earn_points": q["earn_points"],
        "registered": q["registered"],
    }


async def _pick_card(session: AsyncSession, settings: dict) -> dict:
    """Карты чередуются по кругу — выручка сама делится между админами."""
    cards = active_cards(settings)
    index = settings["card_rr"] % len(cards)
    await set_setting(session, "card_rr", settings["card_rr"] + 1)
    return cards[index]


async def create_order(session: AsyncSession, tg_user, data: dict) -> Order:
    name = str(data.get("customer_name") or "").strip()[:200]
    phone = str(data.get("phone") or "").strip()[:50]
    address = str(data.get("address") or "").strip()[:1000]
    comment = str(data.get("comment") or "").strip()[:1000]
    if not name or not phone:
        raise ShopError("Укажи имя и телефон")

    q = await quote(session, tg_user.id, data, lock=True, strict=True)
    settings, method = q["settings"], q["delivery"]
    if method["address"] and not address:
        raise ShopError("Укажи адрес доставки")

    items = []
    for line in q["lines"]:
        product, size, qty = line["product"], line["size"], line["qty"]
        sizes = [dict(s) for s in product.sizes]
        entry = size_entry(sizes, size)
        before = entry["stock"]
        entry["stock"] -= qty
        product.sizes = sizes  # новый список, чтобы SQLAlchemy заметил изменение JSON
        line["before"], line["after"] = before, entry["stock"]
        items.append({
            "product_id": product.id,
            "title": product.title,
            "size": size,
            "qty": qty,
            "price": product.price,
            "cost": await avg_cost(session, product.id),
            "photo": product.photos[0] if product.photos else None,
        })

    cash = q["payment"] == "cash"
    card = None if cash else await _pick_card(session, settings)
    order = Order(
        user_id=tg_user.id,
        username=tg_user.username,
        customer_name=name,
        phone=phone,
        delivery=method["name"],
        delivery_id=method["id"],
        address=address if method["address"] else "",
        comment=comment,
        items=items,
        subtotal=q["subtotal"],
        delivery_price=q["delivery_price"],
        discount=q["discount"],
        coupon_code=q["coupon"].code if q["coupon"] else None,
        total=q["total"],
        payment_method=q["payment"],
        card_label=card["label"] if card else None,
        card_details=card_text(card) if card else None,
        status="confirmed" if cash else "awaiting_payment",
        points_awarded=0,
    )
    add_history(order, "Заказ оформлен" + (" · наличные при получении" if cash else f" · карта «{card['label']}»"))
    session.add(order)
    if q["coupon"]:
        q["coupon"].used_count += 1
    user = await session.get(User, tg_user.id)
    if user and not user.phone:
        user.phone = phone
    await session.flush()  # нужен номер заказа для журнала склада
    for line in q["lines"]:
        log_movement(session, line["product"], line["size"], -line["qty"], "sale", note=f"Заказ #{order.id}")
    await session.commit()

    await safe_send(order.user_id, texts.order_created(order, settings), reply_markup=keyboards.order_kb(order.id))
    await notify_admins(texts.admin_new_order(order, settings["currency"]), reply_markup=keyboards.admin_order_kb(order.id))
    for line in q["lines"]:
        await low_stock_alert(line["product"], line["size"], line["before"], line["after"], settings)
    return order


# ---------- статусы ----------

async def _restore_stock(session: AsyncSession, order: Order) -> None:
    for item in order.items:
        product = await session.get(Product, item["product_id"], with_for_update=True)
        if not product:
            continue
        sizes = [dict(s) for s in product.sizes]
        entry = size_entry(sizes, item["size"])
        if entry:
            entry["stock"] += item["qty"]
        else:
            sizes.append({"size": item["size"], "stock": item["qty"]})
        product.sizes = sizes
        log_movement(session, product, item["size"], item["qty"], "return", note=f"Отмена заказа #{order.id}")


async def change_status(session: AsyncSession, order: Order, status: str, track: str | None = None,
                        actor: str | None = None) -> Order:
    if status not in TRANSITIONS:
        raise ShopError("Неизвестный статус")
    if status != order.status and status not in TRANSITIONS[order.status]:
        raise ShopError(
            f"Нельзя перевести заказ из «{texts.STATUS_PLAIN[order.status]}» в «{texts.STATUS_PLAIN[status]}»"
        )
    settings = await get_settings(session)
    changed = status != order.status
    if status == "cancelled" and changed:
        await _restore_stock(session, order)
        if order.coupon_code:
            coupon = (await session.execute(select(Coupon).where(Coupon.code == order.coupon_code))).scalar_one_or_none()
            if coupon and coupon.used_count > 0:
                coupon.used_count -= 1
    if status in ("paid", "done") and not order.paid_at:
        order.paid_at = now()
        order.paid_via = "Наличные" if order.payment_method == "cash" else f"Карта · {order.card_label or '—'}"
    if track is not None:
        order.track = track.strip()[:100] or None
    order.status = status
    if changed:
        add_history(order, texts.STATUS_PLAIN[status] + (f" · трек {order.track}" if status == "shipped" and order.track else ""), actor)
    elif track is not None:
        add_history(order, f"Трек-номер: {order.track or '—'}", actor)
    if status == "done" and changed:
        from loyalty import award_order_points

        await award_order_points(session, order, settings)
    await session.commit()

    if changed or track is not None:
        text = texts.status_update(order, settings["currency"])
        if text:
            await safe_send(order.user_id, text, reply_markup=keyboards.rate_kb(order.id) if status == "done" else None)
    return order


async def toggle_assign(session: AsyncSession, order: Order, admin_id: int, admin_name: str) -> Order:
    """«Взять в работу» / «Снять с себя» — чтобы двое админов не делали одно и то же."""
    if order.assignee_id == admin_id:
        order.assignee_id, order.assignee_name = None, None
        add_history(order, "Снял с себя", admin_name)
    else:
        order.assignee_id, order.assignee_name = admin_id, admin_name
        add_history(order, "Взял в работу", admin_name)
    await session.commit()
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
    if order.payment_method == "cash":
        raise ShopError("Этот заказ оплачивается наличными при получении — чек не нужен")
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
    add_history(order, "Покупатель прислал чек")
    await session.commit()
    await safe_send(order.user_id, texts.RECEIPT_RECEIVED.format(id=order.id))
    return order


# ---------- склад ----------

def log_movement(session, product, size: str, delta: int, kind: str, *, note: str = "",
                 cost: int | None = None, admin_id: int | None = None) -> None:
    if delta:
        session.add(StockMovement(product_id=product.id, product_title=product.title, size=size, delta=delta,
                                  kind=kind, cost=cost, note=note[:500], admin_id=admin_id))


def clean_sizes(raw: list) -> list[dict]:
    sizes, seen = [], set()
    for s in raw or []:
        size = str(s.get("size") or "").strip()[:20]
        if not size or size in seen:
            continue
        seen.add(size)
        sizes.append({"size": size, "stock": to_int(s.get("stock"))})
    return sizes


async def create_product(session: AsyncSession, values: dict, admin_id: int | None) -> Product:
    """Новый товар; начальные остатки записываются в журнал как приход."""
    product = Product(**values)
    session.add(product)
    await session.flush()
    for s in product.sizes:
        log_movement(session, product, s["size"], s["stock"], "receipt", note="Создание товара", admin_id=admin_id)
    await session.commit()
    return product


async def apply_sizes(session, product: Product, new_sizes: list[dict], admin_id: int | None,
                      note: str = "Ручная правка остатков", kind: str = "adjust") -> None:
    """Меняет размеры/остатки и пишет разницу в журнал (корректировка или инвентаризация)."""
    old = {s["size"]: s["stock"] for s in product.sizes}
    new = {s["size"]: s["stock"] for s in new_sizes}
    for size in dict.fromkeys([*old, *new]):
        log_movement(session, product, size, new.get(size, 0) - old.get(size, 0), kind, note=note, admin_id=admin_id)
    product.sizes = [dict(s) for s in new_sizes]
    await notify_back_in_stock(session, product, [s for s in new if new[s] > 0 and old.get(s, 0) <= 0])


async def receive_stock(session: AsyncSession, product: Product, items: list[dict], *, cost: int | None,
                        note: str, admin_id: int | None) -> Product:
    """Оприходование: пришедшее количество по размерам прибавляется к остатку."""
    sizes = [dict(s) for s in product.sizes]
    added, refilled = 0, []
    for item in items:
        size = str(item.get("size") or "").strip()[:20]
        qty = to_int(item.get("qty"))
        if not size or qty <= 0:
            continue
        entry = size_entry(sizes, size)
        if entry:
            if entry["stock"] <= 0:
                refilled.append(size)
            entry["stock"] += qty
        else:
            sizes.append({"size": size, "stock": qty})
            refilled.append(size)
        log_movement(session, product, size, qty, "receipt", note=note, cost=cost, admin_id=admin_id)
        added += qty
    if not added:
        raise ShopError("Укажи, сколько штук пришло хотя бы по одному размеру")
    product.sizes = sizes
    await session.commit()
    await notify_back_in_stock(session, product, refilled)
    return product


async def writeoff_stock(session: AsyncSession, product: Product, items: list[dict], *, reason: str,
                         admin_id: int | None) -> Product:
    """Списание: брак, подарок, вещь для съёмки — с причиной в журнале."""
    settings = await get_settings(session)
    sizes = [dict(s) for s in product.sizes]
    removed, changes = 0, []
    for item in items:
        size = str(item.get("size") or "").strip()
        qty = to_int(item.get("qty"))
        entry = size_entry(sizes, size)
        if not entry or qty <= 0:
            continue
        if qty > entry["stock"]:
            raise ShopError(f"Размер {size}: на складе только {entry['stock']} шт.")
        changes.append((size, entry["stock"], entry["stock"] - qty))
        entry["stock"] -= qty
        log_movement(session, product, size, -qty, "writeoff", note=reason or "Списание", admin_id=admin_id)
        removed += qty
    if not removed:
        raise ShopError("Укажи, сколько штук списать")
    product.sizes = sizes
    await session.commit()
    for size, before, after in changes:
        await low_stock_alert(product, size, before, after, settings)
    return product


async def low_stock_alert(product: Product, size: str, before: int, after: int, settings: dict) -> None:
    threshold = settings["low_stock"]
    if before > threshold >= after:
        await notify_admins(texts.low_stock(product, size, after))


async def notify_back_in_stock(session: AsyncSession, product: Product, sizes: list[str], soon_released: bool = False) -> None:
    """Пишет всем, кто нажал «Сообщить о поступлении», и снимает их подписку."""
    wanted = list(sizes) + (["*"] if soon_released else [])
    if not wanted or not product.is_active or product.badge == "soon":
        return
    subs = list((await session.execute(
        select(Subscription).where(Subscription.product_id == product.id, Subscription.size.in_(wanted))
    )).scalars())
    if not subs:
        return
    for sub in subs:
        await safe_send(sub.user_id, texts.back_in_stock(product, sub.size), reply_markup=keyboards.product_kb(product.id))
    await session.execute(delete(Subscription).where(Subscription.id.in_([s.id for s in subs])))
    await session.commit()
