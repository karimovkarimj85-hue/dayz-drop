"""Админ-панель на кнопках бота (доступна только ADMIN_IDS)."""
import asyncio
import re

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import func, select

import finance
import keyboards
import tasks
import services
import texts
from config import ADMIN_IDS, WEBAPP_URL
from db import Order, Product, Session, StockMovement, User
from loader import bot
from shop_bot import support_threads
from ui import btn, chunks, kb, show

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

NOT_COMMAND = ~F.text.startswith("/")
PAGE = 8
LIST_TITLES = {
    "checking": "🔎 Ждут проверки оплаты",
    "awaiting_payment": "⏳ Ждут оплату картой",
    "confirmed": "🤝 Наличные — ждут выдачи",
    "paid": "📦 Оплачены — нужно отправить",
    "shipped": "🚚 В пути",
    "all": "🗂 Все заказы",
}
ORDER_ACTIONS = {
    "awaiting_payment": [("✅ Оплата пришла", "paid")],
    "checking": [("✅ Деньги пришли", "paid"), ("❌ Не пришли", "awaiting_payment")],
    "confirmed": [("🚚 Передан курьеру (ввести трек)", "ship"), ("📦 Выдан и оплачен", "done"), ("💵 Деньги получены заранее", "paid")],
    "paid": [("🚚 Отправлен (ввести трек)", "ship"), ("📦 Получен", "done")],
    "shipped": [("📦 Получен", "done"), ("✏️ Изменить трек", "ship")],
}
EDITABLE = {"title", "category", "price", "description", "sizes", "photos"}

_photo_locks: dict[int, asyncio.Lock] = {}


class ProductForm(StatesGroup):
    title = State()
    category = State()
    price = State()
    description = State()
    sizes = State()
    photos = State()


class EditProduct(StatesGroup):
    value = State()
    photos = State()


class EditSetting(StatesGroup):
    value = State()


class ShipTrack(StatesGroup):
    track = State()


class StockReceipt(StatesGroup):
    items = State()
    cost = State()


def parse_sizes(text: str) -> list[dict] | None:
    sizes, seen = [], set()
    for part in re.split(r"[,\n;]+", text):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^(.+?)[\s:=\-–—]+(\d+)$", part)
        if not match:
            return None
        size = match.group(1).strip()[:20]
        if size not in seen:
            seen.add(size)
            sizes.append({"size": size, "stock": int(match.group(2))})
    return sizes or None


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[\s₽$]", "", text)
    return int(digits) if digits.isdigit() else None


# ---------- ответ покупателю реплаем ----------

@router.message(F.reply_to_message)
async def admin_reply_to_customer(message: Message) -> None:
    replied = message.reply_to_message
    user_id = support_threads.get((message.chat.id, replied.message_id))
    source = replied.text or replied.caption or ""
    if not user_id and source[:1] in ("💬", "🆕", "💳", "🧾"):
        match = re.search(r"id (\d{5,})", source)
        user_id = int(match.group(1)) if match else None
    if not user_id or user_id == message.chat.id:
        raise SkipHandler()
    try:
        if message.text:
            await bot.send_message(user_id, f"{texts.SUPPORT_ANSWER}\n\n{message.html_text}")
        else:
            caption = texts.SUPPORT_ANSWER + (f"\n\n{message.html_text}" if message.caption else "")
            await message.copy_to(user_id, caption=caption)
    except Exception as exc:
        await message.reply(f"⚠️ Не удалось отправить: {texts.e(exc)}")
        return
    await message.reply(texts.SUPPORT_DELIVERED)
    for admin_id in ADMIN_IDS - {message.chat.id}:
        await services.safe_send(
            admin_id, f"ℹ️ {texts.e(message.from_user.full_name)} ответил покупателю id <code>{user_id}</code>"
        )


# ---------- главное меню ----------

async def admin_menu_view():
    async with Session() as session:
        counts = dict((await session.execute(select(Order.status, func.count()).group_by(Order.status))).all())
    rows = [
        [btn(f"🔎 На проверке ({counts.get('checking', 0)})", "ol:checking:0")],
        [btn(f"⏳ Ждут оплату ({counts.get('awaiting_payment', 0)})", "ol:awaiting_payment:0"),
         btn(f"🤝 Наличные ({counts.get('confirmed', 0)})", "ol:confirmed:0")],
        [btn(f"📦 Отправить ({counts.get('paid', 0)})", "ol:paid:0"), btn(f"🚚 В пути ({counts.get('shipped', 0)})", "ol:shipped:0")],
        [btn("🗂 Все заказы", "ol:all:0")],
        [btn("➕ Добавить товар", "np"), btn("👕 Товары", "apl:0")],
        [btn("📥 Приход товара", "srp:0"), btn("📜 Движения склада", "smv")],
        [btn("💰 Касса сегодня", "fin"), btn("📤 Excel", "exp")],
        [btn("📣 Рассылка", "bc"), btn("📊 Статистика", "astat")],
        [btn("⚙️ Настройки", "aset")],
    ]
    if WEBAPP_URL:
        rows.append([keyboards._app_button("🛍 Админка в мини-аппе", page="admin")])
    rows.append([btn("⬅️ Меню магазина", "menu")])
    return texts.admin_menu(counts), kb(*rows)


@router.callback_query(F.data == "adm")
async def cb_admin(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, *(await admin_menu_view()))
    await call.answer()


# ---------- заказы ----------

@router.callback_query(F.data.startswith("ol:"))
async def cb_order_list(call: CallbackQuery) -> None:
    _, status, page = call.data.split(":")
    page = int(page)
    query = select(Order).order_by(Order.id.desc())
    if status != "all":
        query = query.where(Order.status == status)
    async with Session() as session:
        orders = list((await session.execute(query.offset(page * PAGE).limit(PAGE + 1))).scalars())
        currency = (await services.get_settings(session))["currency"]
    rows = [
        [btn(f"#{o.id} · {o.customer_name[:16]} · {texts.money(o.total, currency)} · {texts.STATUS_LABELS[o.status][:1]}", f"ao:{o.id}")]
        for o in orders[:PAGE]
    ]
    nav = []
    if page > 0:
        nav.append(btn("◀️", f"ol:{status}:{page - 1}"))
    if len(orders) > PAGE:
        nav.append(btn("▶️", f"ol:{status}:{page + 1}"))
    rows += [nav, [btn("⬅️ Админка", "adm")]]
    text = f"<b>{LIST_TITLES.get(status, status)}</b>\n" + ("Выбери заказ:" if orders else "Заказов нет")
    await show(call, text, kb(*rows))
    await call.answer()


async def order_card_view(order_id: int):
    async with Session() as session:
        order = await session.get(Order, order_id)
        currency = (await services.get_settings(session))["currency"]
    if not order:
        return "Заказ не найден", kb([btn("⬅️ Админка", "adm")])
    rows = [[btn(label, f"os:{order.id}:{action}")] for label, action in ORDER_ACTIONS.get(order.status, [])]
    if order.status not in ("done", "cancelled"):
        rows.insert(0, [btn("👷 Снять с себя" if order.assignee_id else "👷 Взять в работу", f"os:{order.id}:take")])
    if order.payment_method == "cash" and order.status in ("confirmed", "shipped"):
        rows.append([btn("🙅 Не выкупил (отменить и запретить наличные)", f"os:{order.id}:noshow?")])
    if order.receipt_file_id:
        rows.append([btn("🧾 Показать чек", f"orc:{order.id}")])
    if order.username:
        rows.append([keyboards.InlineKeyboardButton(text="✉️ Открыть чат с покупателем", url=f"https://t.me/{order.username}")])
    if order.status not in ("done", "cancelled"):
        rows.append([btn("✖️ Отменить заказ", f"os:{order.id}:cancel?")])
    rows.append([btn("⬅️ Админка", "adm")])
    return texts.admin_order_card(order, currency), kb(*rows)


@router.callback_query(F.data.startswith("ao:"))
async def cb_order_card(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    view = await order_card_view(int(call.data.split(":")[1]))
    if call.message.photo or call.message.document:
        await call.message.answer(*view[:1], reply_markup=view[1])  # не затираем чек — шлём карточку отдельно
    else:
        await show(call, *view)
    await call.answer()


@router.callback_query(F.data.startswith("orc:"))
async def cb_order_receipt(call: CallbackQuery) -> None:
    async with Session() as session:
        order = await session.get(Order, int(call.data.split(":")[1]))
    if order and order.receipt_file_id:
        caption = f"🧾 Чек по заказу #{order.id}"
        if order.receipt_kind == "photo":
            await call.message.answer_photo(order.receipt_file_id, caption=caption)
        else:
            await call.message.answer_document(order.receipt_file_id, caption=caption)
    await call.answer()


@router.callback_query(F.data.startswith("os:"))
async def cb_order_status(call: CallbackQuery, state: FSMContext) -> None:
    _, order_id, action = call.data.split(":")
    order_id = int(order_id)
    if action == "cancel?":
        await show(call, f"Отменить заказ #{order_id}? Товары вернутся на склад, покупателю придёт сообщение.",
                   kb([btn("Да, отменить", f"os:{order_id}:cancelled"), btn("Нет", f"ao:{order_id}")]))
        await call.answer()
        return
    if action == "noshow?":
        await show(call, f"Покупатель не выкупил заказ #{order_id}? Заказ отменится, вещи вернутся на склад, "
                         "а этому покупателю будет доступна только предоплата картой.",
                   kb([btn("Да, не выкупил", f"os:{order_id}:noshow"), btn("Нет", f"ao:{order_id}")]))
        await call.answer()
        return
    if action == "ship":
        await state.set_state(ShipTrack.track)
        await state.update_data(order_id=order_id)
        await call.message.answer(texts.ASK_TRACK, reply_markup=kb([btn("Без трека", "ship_none")], [btn("❌ Отмена", f"ao:{order_id}")]))
        await call.answer()
        return
    who = call.from_user.full_name
    async with Session() as session:
        order = await session.get(Order, order_id)
        try:
            if action == "take":
                await services.toggle_assign(session, order, call.from_user.id, who)
            elif action == "noshow":
                await services.change_status(session, order, "cancelled", actor=f"{who} (не выкупил)")
                customer = await session.get(User, order.user_id)
                if customer:
                    customer.no_cash = True
                    await session.commit()
            else:
                await services.change_status(session, order, action, actor=who)
        except services.ShopError as exc:
            await call.answer(str(exc), show_alert=True)
            return
    await show(call, *(await order_card_view(order_id)))
    if action == "take":
        await call.answer("Заказ за тобой" if order.assignee_id else "Снял с себя")
        others = ADMIN_IDS - {call.from_user.id}
        if order.assignee_id:
            for admin_id in others:
                await services.safe_send(admin_id, f"👷 {texts.e(who)} взял в работу заказ #{order.id}")
    else:
        await call.answer(f"Статус: {texts.STATUS_PLAIN['cancelled' if action == 'noshow' else action]}")


async def _ship(message: Message, state: FSMContext, track: str) -> None:
    order_id = (await state.get_data())["order_id"]
    await state.clear()
    async with Session() as session:
        order = await session.get(Order, order_id)
        try:
            await services.change_status(session, order, "shipped", track, actor=message.from_user.full_name)
        except services.ShopError as exc:
            await message.answer(f"⚠️ {texts.e(exc)}")
            return
    text, markup = await order_card_view(order_id)
    await message.answer(text, reply_markup=markup)


@router.message(ShipTrack.track, F.text, NOT_COMMAND)
async def on_track(message: Message, state: FSMContext) -> None:
    await _ship(message, state, message.text.strip())


@router.callback_query(ShipTrack.track, F.data == "ship_none")
async def on_track_none(call: CallbackQuery, state: FSMContext) -> None:
    await call.message.edit_reply_markup(reply_markup=None)
    await _ship(call.message, state, "")
    await call.answer()


# ---------- товары ----------

@router.callback_query(F.data.startswith("apl:"))
async def cb_products(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, *(await products_list_view(int(call.data.split(":")[1]))))
    await call.answer()


async def products_list_view(page: int):
    async with Session() as session:
        products = list((await session.execute(select(Product).order_by(Product.sort, Product.id.desc()))).scalars())
    chunk = products[page * PAGE:(page + 1) * PAGE]
    rows = [
        [btn(f"{'' if p.is_active else '🙈 '}{p.title} · {texts.stock_total(p)} шт", f"apc:{p.id}")] for p in chunk
    ]
    nav = []
    if page > 0:
        nav.append(btn("◀️", f"apl:{page - 1}"))
    if (page + 1) * PAGE < len(products):
        nav.append(btn("▶️", f"apl:{page + 1}"))
    rows += [nav, [btn("➕ Добавить товар", "np")], [btn("⬅️ Админка", "adm")]]
    return "👕 <b>Товары</b>\n" + ("Выбери товар:" if products else "Пока пусто — добавь первый"), kb(*rows)


async def product_card_view(product_id: int):
    async with Session() as session:
        product = await session.get(Product, product_id)
        currency = (await services.get_settings(session))["currency"]
    if not product:
        return "Товар не найден", kb([btn("⬅️ Товары", "apl:0")]), None
    pid = product.id
    markup = kb(
        [btn("✏️ Название", f"ape:{pid}:title"), btn("💰 Цена", f"ape:{pid}:price")],
        [btn("📝 Описание", f"ape:{pid}:description"), btn("🏷 Категория", f"ape:{pid}:category")],
        [btn("📦 Размеры и остатки", f"ape:{pid}:sizes"), btn("🖼 Фото", f"ape:{pid}:photos")],
        [btn("🙈 Скрыть" if product.is_active else "👁 Показать", f"apv:{pid}"), btn("🗑 Удалить", f"apd:{pid}")],
        [btn("⬅️ Товары", "apl:0")],
    )
    return texts.admin_product_card(product, currency), markup, (product.photos[0] if product.photos else None)


async def send_product_card(message: Message, product_id: int) -> None:
    text, markup, photo = await product_card_view(product_id)
    if photo:
        await message.answer_photo(photo, caption=text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("apc:"))
async def cb_product_card(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, markup, photo = await product_card_view(int(call.data.split(":")[1]))
    await show(call, text, markup, photo)
    await call.answer()


@router.callback_query(F.data.startswith("apv:"))
async def cb_product_visibility(call: CallbackQuery) -> None:
    product_id = int(call.data.split(":")[1])
    async with Session() as session:
        product = await session.get(Product, product_id)
        product.is_active = not product.is_active
        await session.commit()
    text, markup, photo = await product_card_view(product_id)
    await show(call, text, markup, photo)
    await call.answer("Показывается в каталоге" if product.is_active else "Скрыт из каталога")


@router.callback_query(F.data.startswith("apd:"))
async def cb_product_delete(call: CallbackQuery) -> None:
    product_id = int(call.data.split(":")[1])
    await show(call, "Удалить товар? Старые заказы с ним останутся.",
               kb([btn("Да, удалить", f"apx:{product_id}"), btn("Нет", f"apc:{product_id}")]))
    await call.answer()


@router.callback_query(F.data.startswith("apx:"))
async def cb_product_delete_yes(call: CallbackQuery, state: FSMContext) -> None:
    async with Session() as session:
        product = await session.get(Product, int(call.data.split(":")[1]))
        if product:
            await session.delete(product)
            await session.commit()
    await state.clear()
    await show(call, *(await products_list_view(0)))
    await call.answer("Удалено")


@router.callback_query(F.data.startswith("ape:"))
async def cb_product_edit(call: CallbackQuery, state: FSMContext) -> None:
    _, product_id, field = call.data.split(":")
    if field not in EDITABLE:
        await call.answer()
        return
    await state.clear()
    await state.update_data(product_id=int(product_id), field=field, photos=[])
    if field == "photos":
        await state.set_state(EditProduct.photos)
        await call.message.answer(
            texts.ASK_PRODUCT["photos"] + "\nСтарые фото заменятся новыми.",
            reply_markup=kb([btn("✅ Готово", "ph_done")], [btn("❌ Отмена", f"apc:{product_id}")]),
        )
    else:
        await state.set_state(EditProduct.value)
        await call.message.answer(texts.ASK_PRODUCT[field], reply_markup=kb([btn("❌ Отмена", f"apc:{product_id}")]))
    await call.answer()


@router.message(EditProduct.value, F.text, NOT_COMMAND)
async def on_product_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field, value = data["field"], message.text.strip()
    if field == "price":
        value = parse_price(value)
        if value is None:
            await message.answer(texts.BAD_PRICE)
            return
    elif field == "sizes":
        value = parse_sizes(value)
        if not value:
            await message.answer(texts.BAD_SIZES)
            return
    else:
        value = value[:3000] if field == "description" else value[:200]
    async with Session() as session:
        product = await session.get(Product, data["product_id"])
        if field == "sizes":
            await services.apply_sizes(session, product, value, message.from_user.id)
        else:
            setattr(product, field, value)
        await session.commit()
    await state.clear()
    await message.answer(texts.SAVED)
    await send_product_card(message, data["product_id"])


async def _collect_photo(message: Message, state: FSMContext) -> None:
    lock = _photo_locks.setdefault(message.from_user.id, asyncio.Lock())
    async with lock:  # альбом приходит пачкой сообщений одновременно
        photos = (await state.get_data()).get("photos", [])
        if len(photos) >= 10:
            return
        photos.append(message.photo[-1].file_id)
        await state.update_data(photos=photos)
    if not message.media_group_id or len(photos) == 1:
        await message.answer(f"🖼 Фото добавлено ({len(photos)}). Пришли ещё или нажми «Готово».",
                             reply_markup=kb([btn("✅ Готово", "ph_done")]))


@router.message(EditProduct.photos, F.photo)
async def on_edit_photo(message: Message, state: FSMContext) -> None:
    await _collect_photo(message, state)


@router.callback_query(EditProduct.photos, F.data == "ph_done")
async def on_edit_photos_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("photos"):
        await call.answer("Сначала пришли хотя бы одно фото", show_alert=True)
        return
    async with Session() as session:
        product = await session.get(Product, data["product_id"])
        product.photos = data["photos"]
        await session.commit()
    await state.clear()
    await call.answer(texts.SAVED)
    await send_product_card(call.message, data["product_id"])


# ---------- новый товар ----------

@router.callback_query(F.data == "np")
async def cb_new_product(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ProductForm.title)
    await call.message.answer("➕ <b>Новый товар</b>\n\n" + texts.ASK_PRODUCT["title"], reply_markup=kb([btn("❌ Отмена", "adm")]))
    await call.answer()


@router.message(ProductForm.title, F.text, NOT_COMMAND)
async def np_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:200])
    async with Session() as session:
        cats = sorted({c for c in (await session.execute(select(Product.category))).scalars() if c})
    await state.update_data(cats=cats)
    await state.set_state(ProductForm.category)
    rows = chunks([btn(c, f"npc:{i}") for i, c in enumerate(cats)], 2)
    rows.append([btn("Без категории", "npc:-1")])
    await message.answer(texts.ASK_PRODUCT["category"], reply_markup=kb(*rows))


async def _np_ask_price(message: Message, state: FSMContext, category: str) -> None:
    await state.update_data(category=category)
    await state.set_state(ProductForm.price)
    await message.answer(texts.ASK_PRODUCT["price"])


@router.callback_query(ProductForm.category, F.data.startswith("npc:"))
async def np_category_button(call: CallbackQuery, state: FSMContext) -> None:
    index = int(call.data.split(":")[1])
    cats = (await state.get_data()).get("cats", [])
    await call.message.edit_reply_markup(reply_markup=None)
    await _np_ask_price(call.message, state, cats[index] if 0 <= index < len(cats) else "")
    await call.answer()


@router.message(ProductForm.category, F.text, NOT_COMMAND)
async def np_category_text(message: Message, state: FSMContext) -> None:
    await _np_ask_price(message, state, message.text.strip()[:100])


@router.message(ProductForm.price, F.text, NOT_COMMAND)
async def np_price(message: Message, state: FSMContext) -> None:
    price = parse_price(message.text)
    if price is None:
        await message.answer(texts.BAD_PRICE)
        return
    await state.update_data(price=price)
    await state.set_state(ProductForm.description)
    await message.answer(texts.ASK_PRODUCT["description"], reply_markup=kb([btn("Пропустить", "np_skip")]))


async def _np_ask_sizes(message: Message, state: FSMContext, description: str) -> None:
    await state.update_data(description=description)
    await state.set_state(ProductForm.sizes)
    await message.answer(texts.ASK_PRODUCT["sizes"])


@router.callback_query(ProductForm.description, F.data == "np_skip")
async def np_description_skip(call: CallbackQuery, state: FSMContext) -> None:
    await call.message.edit_reply_markup(reply_markup=None)
    await _np_ask_sizes(call.message, state, "")
    await call.answer()


@router.message(ProductForm.description, F.text, NOT_COMMAND)
async def np_description(message: Message, state: FSMContext) -> None:
    await _np_ask_sizes(message, state, message.text.strip()[:3000])


@router.message(ProductForm.sizes, F.text, NOT_COMMAND)
async def np_sizes(message: Message, state: FSMContext) -> None:
    sizes = parse_sizes(message.text)
    if not sizes:
        await message.answer(texts.BAD_SIZES)
        return
    await state.update_data(sizes=sizes, photos=[])
    await state.set_state(ProductForm.photos)
    await message.answer(texts.ASK_PRODUCT["photos"], reply_markup=kb([btn("✅ Готово", "ph_done")]))


@router.message(ProductForm.photos, F.photo)
async def np_photo(message: Message, state: FSMContext) -> None:
    await _collect_photo(message, state)


@router.callback_query(ProductForm.photos, F.data == "ph_done")
async def np_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    async with Session() as session:
        product = await services.create_product(session, {
            "title": data["title"],
            "category": data["category"],
            "price": data["price"],
            "description": data["description"],
            "sizes": data["sizes"],
            "photos": data.get("photos", []),
        }, call.from_user.id)
    await state.clear()
    await call.answer("Товар добавлен!")
    await call.message.answer("✅ Товар добавлен и уже виден в каталоге.")
    await send_product_card(call.message, product.id)


# ---------- склад: приход и журнал ----------

@router.callback_query(F.data.startswith("srp:"))
async def cb_receipt_pick(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = int(call.data.split(":")[1])
    async with Session() as session:
        products = list((await session.execute(select(Product).order_by(Product.sort, Product.id.desc()))).scalars())
    rows = [[btn(f"{p.title} · {texts.stock_total(p)} шт", f"sr:{p.id}")] for p in products[page * PAGE:(page + 1) * PAGE]]
    nav = []
    if page > 0:
        nav.append(btn("◀️", f"srp:{page - 1}"))
    if (page + 1) * PAGE < len(products):
        nav.append(btn("▶️", f"srp:{page + 1}"))
    rows += [nav, [btn("➕ Новый товар", "np")], [btn("⬅️ Админка", "adm")]]
    text = texts.RECEIPT_PICK if products else "Сначала добавь товар — приход оформляется на существующий товар."
    await show(call, text, kb(*rows))
    await call.answer()


@router.callback_query(F.data.startswith("sr:"))
async def cb_receipt_start(call: CallbackQuery, state: FSMContext) -> None:
    product_id = int(call.data.split(":")[1])
    async with Session() as session:
        product = await session.get(Product, product_id)
    if not product:
        await call.answer("Товар не найден", show_alert=True)
        return
    await state.set_state(StockReceipt.items)
    await state.update_data(product_id=product_id)
    await call.message.answer(texts.receipt_ask_items(product), reply_markup=kb([btn("❌ Отмена", "adm")]))
    await call.answer()


@router.message(StockReceipt.items, F.text, NOT_COMMAND)
async def on_receipt_items(message: Message, state: FSMContext) -> None:
    items = parse_sizes(message.text)
    if not items or not any(i["stock"] > 0 for i in items):
        await message.answer(texts.BAD_SIZES)
        return
    await state.update_data(items=[{"size": i["size"], "qty": i["stock"]} for i in items])
    await state.set_state(StockReceipt.cost)
    await message.answer(texts.RECEIPT_ASK_COST, reply_markup=kb([btn("Пропустить", "sr_nocost")]))


async def _finish_receipt(message: Message, state: FSMContext, admin_id: int, cost: int | None) -> None:
    data = await state.get_data()
    await state.clear()
    async with Session() as session:
        product = await session.get(Product, data["product_id"])
        try:
            await services.receive_stock(session, product, data["items"], cost=cost, note="Приход товара", admin_id=admin_id)
        except services.ShopError as exc:
            await message.answer(f"⚠️ {texts.e(exc)}")
            return
        currency = (await services.get_settings(session))["currency"]
    await message.answer(
        texts.receipt_done(product, data["items"], cost, currency),
        reply_markup=kb([btn("📥 Ещё приход", "srp:0"), btn("📜 Движения", "smv")], [btn("⬅️ Админка", "adm")]),
    )


@router.message(StockReceipt.cost, F.text, NOT_COMMAND)
async def on_receipt_cost(message: Message, state: FSMContext) -> None:
    cost = parse_price(message.text)
    if cost is None:
        await message.answer(texts.BAD_PRICE)
        return
    await _finish_receipt(message, state, message.from_user.id, cost)


@router.callback_query(StockReceipt.cost, F.data == "sr_nocost")
async def on_receipt_no_cost(call: CallbackQuery, state: FSMContext) -> None:
    await call.message.edit_reply_markup(reply_markup=None)
    await _finish_receipt(call.message, state, call.from_user.id, None)
    await call.answer()


@router.callback_query(F.data == "smv")
async def cb_movements(call: CallbackQuery) -> None:
    async with Session() as session:
        movements = list(
            (await session.execute(select(StockMovement).order_by(StockMovement.id.desc()).limit(20))).scalars()
        )
    await show(call, texts.movements(movements), kb([btn("📥 Приход товара", "srp:0")], [btn("⬅️ Админка", "adm")]))
    await call.answer()


# ---------- настройки и статистика ----------

@router.callback_query(F.data == "aset")
async def cb_settings(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with Session() as session:
        settings = await services.get_settings(session)
    rows = [[btn("💱 Валюта", "asv:currency")]]
    if WEBAPP_URL:
        rows.append([keyboards._app_button("⚙️ Карты, доставка, баллы — в мини-аппе", page="admin", section="settings")])
    rows.append([btn("⬅️ Админка", "adm")])
    markup = kb(*rows)
    await show(call, texts.admin_settings(settings), markup)
    await call.answer()


@router.callback_query(F.data.startswith("asv:"))
async def cb_setting_edit(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":")[1]
    if key not in texts.ASK_SETTING:
        await call.answer()
        return
    await state.set_state(EditSetting.value)
    await state.update_data(key=key)
    await call.message.answer(texts.ASK_SETTING[key], reply_markup=kb([btn("❌ Отмена", "aset")]))
    await call.answer()


@router.message(EditSetting.value, F.text, NOT_COMMAND)
async def on_setting_value(message: Message, state: FSMContext) -> None:
    key = (await state.get_data())["key"]
    async with Session() as session:
        settings = await services.save_settings(session, {key: message.text})
    await state.clear()
    await message.answer(
        texts.SAVED + "\n\n" + texts.admin_settings(settings),
        reply_markup=kb([btn("⚙️ Настройки", "aset"), btn("⬅️ Админка", "adm")]),
    )


@router.callback_query(F.data == "astat")
async def cb_stats(call: CallbackQuery) -> None:
    async with Session() as session:
        by_status = dict((await session.execute(select(Order.status, func.count()).group_by(Order.status))).all())
        revenue = (await finance.report(session, "all"))["revenue"]
        users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        products = (await session.execute(select(func.count()).select_from(Product))).scalar_one()
        currency = (await services.get_settings(session))["currency"]
    await show(call, texts.admin_stats(by_status, int(revenue), users, products, currency), kb([btn("⬅️ Админка", "adm")]))
    await call.answer()


# ---------- касса, выгрузки, рассылка ----------

@router.callback_query(F.data == "fin")
async def cb_finance(call: CallbackQuery) -> None:
    async with Session() as session:
        text = await finance.daily_report_text(session)
    await show(call, text, kb([btn("📤 Выгрузить в Excel", "exp")], [btn("⬅️ Админка", "adm")]))
    await call.answer()


@router.callback_query(F.data == "exp")
async def cb_export_menu(call: CallbackQuery) -> None:
    await show(call, "📤 <b>Выгрузка в Excel</b>\nЧто выгрузить? Файл придёт сюда.", kb(
        [btn("🧾 Заказы", "exp:orders"), btn("📦 Склад", "exp:stock")],
        [btn("💰 Касса", "exp:finance"), btn("👥 Покупатели", "exp:customers")],
        [btn("🗂 Всё одним файлом", "exp:all")],
        [btn("💾 Резервная копия базы", "exp:backup")],
        [btn("⬅️ Админка", "adm")],
    ))
    await call.answer()


@router.callback_query(F.data.startswith("exp:"))
async def cb_export(call: CallbackQuery) -> None:
    kind = call.data.split(":")[1]
    await call.answer("Готовлю файл…")
    async with Session() as session:
        content, filename = await (finance.backup_zip(session) if kind == "backup" else finance.export_xlsx(session, kind))
    await call.message.answer_document(BufferedInputFile(content, filename=filename), caption=f"📤 {filename}")


class BroadcastForm(StatesGroup):
    message = State()


_broadcast_drafts: dict[int, dict] = {}


@router.callback_query(F.data == "bc")
async def cb_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastForm.message)
    await call.message.answer(texts.BROADCAST_ASK, reply_markup=kb([btn("❌ Отмена", "adm")]))
    await call.answer()


@router.message(BroadcastForm.message, F.photo | (F.text & NOT_COMMAND))
async def on_broadcast_message(message: Message, state: FSMContext) -> None:
    draft = {
        "text": message.html_text if (message.text or message.caption) else "",
        "photo": message.photo[-1].file_id if message.photo else None,
    }
    if not draft["text"] and not draft["photo"]:
        await message.answer("Пришли текст или фото с подписью.")
        return
    _broadcast_drafts[message.from_user.id] = draft
    await state.clear()
    preview_markup = keyboards.shop_open_kb()
    if draft["photo"]:
        await message.answer_photo(draft["photo"], caption=draft["text"] or None, reply_markup=preview_markup)
    else:
        await message.answer(draft["text"], reply_markup=preview_markup)
    async with Session() as session:
        total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        registered = (await session.execute(
            select(func.count()).select_from(User).where(User.registered_at.is_not(None)))).scalar_one()
    await message.answer("☝️ Так увидят покупатели. Кому отправить?", reply_markup=kb(
        [btn(f"📣 Всем ({total})", "bcs:all")],
        [btn(f"🎁 Только зарегистрированным ({registered})", "bcs:registered")],
        [btn("❌ Отмена", "adm")],
    ))


@router.callback_query(F.data.startswith("bcs:"))
async def cb_broadcast_send(call: CallbackQuery) -> None:
    draft = _broadcast_drafts.pop(call.from_user.id, None)
    if not draft:
        await call.answer("Черновик потерялся — начни заново", show_alert=True)
        return
    asyncio.create_task(tasks.broadcast(call.from_user.id, draft["text"], draft["photo"], call.data.split(":")[1], True))
    await call.message.edit_text("📣 Рассылка запущена — напишу, когда закончу.")
    await call.answer()
