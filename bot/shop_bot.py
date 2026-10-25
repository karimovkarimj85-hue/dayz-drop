"""Магазин на обычных кнопках бота: каталог, корзина, оформление заказа, поддержка."""
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ReplyParameters,
)

import keyboards
import services
import texts
from config import ADMIN_IDS
from db import Product, Session
from loader import bot
from ui import btn, chunks, kb, show

router = Router()

PAGE = 8
NOT_COMMAND = ~F.text.startswith("/")

# (чат админа, id сообщения) -> id покупателя: чтобы ответ реплаем ушёл нужному человеку
support_threads: dict[tuple[int, int], int] = {}


class Checkout(StatesGroup):
    name = State()
    phone = State()
    delivery = State()
    address = State()
    comment = State()
    confirm = State()


class Support(StatesGroup):
    waiting = State()


# ---------- экраны ----------

async def menu_view(user_id: int):
    async with Session() as session:
        count = sum(i["qty"] for i in await services.get_cart(session, user_id))
    return texts.MENU, keyboards.start_kb(user_id in ADMIN_IDS, count)


def _categories(products: list[Product]) -> list[str]:
    return sorted({p.category for p in products if p.category})


async def catalog_view():
    async with Session() as session:
        products = await services.active_products(session)
    cats = _categories(products)
    if not products:
        return texts.CATALOG_EMPTY, kb([btn("⬅️ Меню", "menu")])
    if len(cats) <= 1:
        return await product_list_view(-1, 0)
    rows = [[btn(c, f"c:{i}:0")] for i, c in enumerate(cats)]
    rows.append([btn("Все товары", "c:-1:0")])
    rows.append([btn("🛒 Корзина", "cart"), btn("⬅️ Меню", "menu")])
    return texts.CATALOG, kb(*rows)


async def product_list_view(cat_index: int, page: int):
    async with Session() as session:
        products = await services.active_products(session)
        settings = await services.get_settings(session)
    cats = _categories(products)
    title = "Все товары"
    if 0 <= cat_index < len(cats):
        title = cats[cat_index]
        products = [p for p in products if p.category == title]
    if not products:
        return texts.CATALOG_EMPTY, kb([btn("⬅️ Меню", "menu")])

    pages = (len(products) - 1) // PAGE + 1
    page = max(0, min(page, pages - 1))
    rows = []
    for p in products[page * PAGE:(page + 1) * PAGE]:
        mark = "" if texts.stock_total(p) else " · нет в наличии"
        rows.append([btn(f"{p.title} · {texts.money(p.price, settings['currency'])}{mark}", f"p:{p.id}:{cat_index}")])
    nav = []
    if page > 0:
        nav.append(btn("◀️", f"c:{cat_index}:{page - 1}"))
    if pages > 1:
        nav.append(btn(f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        nav.append(btn("▶️", f"c:{cat_index}:{page + 1}"))
    rows.append(nav)
    rows.append([btn("⬅️ Категории" if len(cats) > 1 else "⬅️ Меню", "cat" if len(cats) > 1 else "menu"), btn("🛒 Корзина", "cart")])
    return f"👕 <b>{texts.e(title)}</b>\nВыбери вещь:", kb(*rows)


def product_kb(product: Product, cat_index: int, cart_count: int):
    sizes = [
        btn(s["size"], f"a:{product.id}:{cat_index}:{s['size']}") if s["stock"] else btn(f"✖ {s['size']}", "nostock")
        for s in product.sizes
    ]
    rows = chunks(sizes, 4)
    if len(product.photos) > 1:
        rows.append([btn(f"🖼 Все фото ({len(product.photos)})", f"ph:{product.id}")])
    rows.append([btn(f"🛒 Корзина{f' ({cart_count})' if cart_count else ''}", "cart"), btn("⬅️ Назад", f"c:{cat_index}:0")])
    return kb(*rows)


async def product_view(product_id: int, cat_index: int, user_id: int):
    async with Session() as session:
        product = await session.get(Product, product_id)
        settings = await services.get_settings(session)
        count = sum(i["qty"] for i in await services.get_cart(session, user_id))
    if not product or not product.is_active:
        return "Товар больше недоступен", kb([btn("⬅️ Каталог", "cat")]), None
    photo = product.photos[0] if product.photos else None
    return texts.product_card(product, settings["currency"]), product_kb(product, cat_index, count), photo


async def cart_view(user_id: int):
    async with Session() as session:
        lines = await services.cart_lines(session, user_id)
        settings = await services.get_settings(session)
    if not lines:
        return texts.CART_EMPTY, kb([btn("👕 Каталог", "cat"), btn("⬅️ Меню", "menu")])
    rows = []
    for i, line in enumerate(lines):
        label = f"{line['product'].title[:18]} {line['size']} ×{line['qty']}"
        rows.append([btn("➖", f"q:{i}:-1"), btn(label, "noop"), btn("➕", f"q:{i}:1")])
    rows.append([btn("🗑 Очистить", "cart_clear"), btn("✅ Оформить", "co")])
    rows.append([btn("👕 Каталог", "cat"), btn("⬅️ Меню", "menu")])
    return texts.cart_text(lines, settings["currency"]), kb(*rows)


# ---------- навигация ----------

@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data == "nostock")
async def cb_nostock(call: CallbackQuery) -> None:
    await call.answer(texts.NO_STOCK, show_alert=True)


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, *(await menu_view(call.from_user.id)))
    await call.answer()


@router.callback_query(F.data == "cat")
async def cb_catalog(call: CallbackQuery) -> None:
    await show(call, *(await catalog_view()))
    await call.answer()


@router.callback_query(F.data.startswith("c:"))
async def cb_category(call: CallbackQuery) -> None:
    _, cat_index, page = call.data.split(":")
    await show(call, *(await product_list_view(int(cat_index), int(page))))
    await call.answer()


@router.callback_query(F.data.startswith("p:"))
async def cb_product(call: CallbackQuery) -> None:
    _, product_id, cat_index = call.data.split(":")
    text, markup, photo = await product_view(int(product_id), int(cat_index), call.from_user.id)
    await show(call, text, markup, photo)
    await call.answer()


@router.callback_query(F.data.startswith("ph:"))
async def cb_photos(call: CallbackQuery) -> None:
    async with Session() as session:
        product = await session.get(Product, int(call.data.split(":")[1]))
    if product and product.photos:
        await call.message.answer_media_group([InputMediaPhoto(media=p) for p in product.photos[:10]])
    await call.answer()


@router.callback_query(F.data.startswith("a:"))
async def cb_add_to_cart(call: CallbackQuery) -> None:
    _, product_id, cat_index, size = call.data.split(":", 3)
    async with Session() as session:
        product = await session.get(Product, int(product_id))
        entry = next((s for s in product.sizes if s["size"] == size), None) if product else None
        cart = await services.get_cart(session, call.from_user.id)
        item = next((i for i in cart if i["product_id"] == product.id and i["size"] == size), None) if product else None
        if not product or not product.is_active or not entry or entry["stock"] <= (item["qty"] if item else 0):
            await call.answer(texts.NO_STOCK, show_alert=True)
            return
        if item:
            item["qty"] += 1
        else:
            cart.append({"product_id": product.id, "size": size, "qty": 1})
        await services.set_cart(session, call.from_user.id, cart)
    count = sum(i["qty"] for i in cart)
    await call.answer(f"✅ В корзине: {product.title}, {size}")
    try:
        await call.message.edit_reply_markup(reply_markup=product_kb(product, int(cat_index), count))
    except Exception:
        pass


@router.callback_query(F.data == "cart")
async def cb_cart(call: CallbackQuery) -> None:
    await show(call, *(await cart_view(call.from_user.id)))
    await call.answer()


@router.callback_query(F.data.startswith("q:"))
async def cb_cart_qty(call: CallbackQuery) -> None:
    _, index, delta = call.data.split(":")
    async with Session() as session:
        lines = await services.cart_lines(session, call.from_user.id)
        index, delta = int(index), int(delta)
        if index < len(lines):
            line = lines[index]
            if delta > 0 and line["qty"] >= line["stock"]:
                await call.answer(f"Больше нет в наличии ({line['stock']} шт)", show_alert=True)
                return
            line["qty"] += delta
        cart = [{"product_id": l["product"].id, "size": l["size"], "qty": l["qty"]} for l in lines if l["qty"] > 0]
        await services.set_cart(session, call.from_user.id, cart)
    await show(call, *(await cart_view(call.from_user.id)))
    await call.answer()


@router.callback_query(F.data == "cart_clear")
async def cb_cart_clear(call: CallbackQuery) -> None:
    async with Session() as session:
        await services.set_cart(session, call.from_user.id, [])
    await show(call, *(await cart_view(call.from_user.id)))
    await call.answer("Корзина очищена")


# ---------- оформление заказа ----------

@router.callback_query(F.data == "co")
async def co_start(call: CallbackQuery, state: FSMContext) -> None:
    async with Session() as session:
        lines = await services.cart_lines(session, call.from_user.id)
    if not lines:
        await show(call, *(await cart_view(call.from_user.id)))
        await call.answer("Корзина пуста")
        return
    await state.clear()
    await state.set_state(Checkout.name)
    name = call.from_user.full_name
    await call.message.answer(
        texts.ASK_NAME, reply_markup=kb([btn(f"✅ {name[:40]}", "co_name")], [btn("❌ Отменить", "co_cancel")])
    )
    await call.answer()


async def _ask_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(Checkout.phone)
    await message.answer(
        texts.ASK_PHONE,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


@router.callback_query(Checkout.name, F.data == "co_name")
async def co_name_button(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(customer_name=call.from_user.full_name)
    await call.message.edit_reply_markup(reply_markup=None)
    await _ask_phone(call.message, state)
    await call.answer()


@router.message(Checkout.name, F.text, NOT_COMMAND)
async def co_name_text(message: Message, state: FSMContext) -> None:
    await state.update_data(customer_name=message.text.strip()[:200])
    await _ask_phone(message, state)


async def _ask_delivery(message: Message, state: FSMContext, phone: str) -> None:
    await state.update_data(phone=phone[:50])
    await message.answer(texts.PHONE_SAVED, reply_markup=ReplyKeyboardRemove())
    async with Session() as session:
        options = services.delivery_options(await services.get_settings(session))
    await state.set_state(Checkout.delivery)
    rows = [[btn(o, f"dl:{i}")] for i, o in enumerate(options)]
    rows.append([btn("❌ Отменить", "co_cancel")])
    await message.answer(texts.ASK_DELIVERY, reply_markup=kb(*rows))


@router.message(Checkout.phone, F.contact)
async def co_phone_contact(message: Message, state: FSMContext) -> None:
    await _ask_delivery(message, state, message.contact.phone_number)


@router.message(Checkout.phone, F.text, NOT_COMMAND)
async def co_phone_text(message: Message, state: FSMContext) -> None:
    await _ask_delivery(message, state, message.text.strip())


async def _ask_comment(message: Message, state: FSMContext) -> None:
    await state.set_state(Checkout.comment)
    await message.answer(texts.ASK_COMMENT, reply_markup=kb([btn("Пропустить", "co_skip")], [btn("❌ Отменить", "co_cancel")]))


@router.callback_query(Checkout.delivery, F.data.startswith("dl:"))
async def co_delivery(call: CallbackQuery, state: FSMContext) -> None:
    async with Session() as session:
        options = services.delivery_options(await services.get_settings(session))
    index = int(call.data.split(":")[1])
    if index >= len(options):
        await call.answer("Выбери вариант из списка", show_alert=True)
        return
    delivery = options[index]
    await state.update_data(delivery=delivery)
    await call.message.edit_text(f"{texts.ASK_DELIVERY}\n\n✅ {texts.e(delivery)}")
    if "самовывоз" in delivery.lower():
        await state.update_data(address="")
        await _ask_comment(call.message, state)
    else:
        await state.set_state(Checkout.address)
        await call.message.answer(texts.ASK_ADDRESS, reply_markup=kb([btn("❌ Отменить", "co_cancel")]))
    await call.answer()


@router.message(Checkout.address, F.text, NOT_COMMAND)
async def co_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text.strip()[:1000])
    await _ask_comment(message, state)


async def _confirm(message: Message, state: FSMContext, user_id: int) -> None:
    await state.set_state(Checkout.confirm)
    data = await state.get_data()
    async with Session() as session:
        lines = await services.cart_lines(session, user_id)
        settings = await services.get_settings(session)
    if not lines:
        await state.clear()
        await message.answer(texts.CART_EMPTY, reply_markup=keyboards.shop_kb())
        return
    await message.answer(
        texts.checkout_summary(data, lines, settings["currency"]),
        reply_markup=kb([btn("✅ Подтвердить заказ", "co_ok")], [btn("❌ Отменить", "co_cancel")]),
    )


@router.callback_query(Checkout.comment, F.data == "co_skip")
async def co_skip_comment(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(comment="")
    await call.message.edit_reply_markup(reply_markup=None)
    await _confirm(call.message, state, call.from_user.id)
    await call.answer()


@router.message(Checkout.comment, F.text, NOT_COMMAND)
async def co_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text.strip()[:1000])
    await _confirm(message, state, message.from_user.id)


@router.callback_query(Checkout.confirm, F.data == "co_ok")
async def co_ok(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    async with Session() as session:
        cart = await services.get_cart(session, call.from_user.id)
        try:
            order = await services.create_order(session, call.from_user, {**data, "items": cart})
        except services.ShopError as exc:
            await call.message.edit_text(f"⚠️ {texts.e(exc)}", reply_markup=kb([btn("🛒 Корзина", "cart")]))
            await state.clear()
            await call.answer()
            return
        await services.set_cart(session, call.from_user.id, [])
    await state.clear()
    await call.message.edit_text(texts.ORDER_DONE.format(id=order.id))
    await call.answer("Заказ оформлен!")


@router.callback_query(F.data == "co_cancel")
async def co_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(texts.CHECKOUT_CANCELLED, reply_markup=kb([btn("🛒 Корзина", "cart"), btn("⬅️ Меню", "menu")]))
    await call.answer()


# ---------- поддержка ----------

async def start_support(message: Message, state: FSMContext) -> None:
    await state.set_state(Support.waiting)
    await message.answer(texts.SUPPORT_ASK, reply_markup=kb([btn("❌ Отмена", "sup_cancel")]))


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery, state: FSMContext) -> None:
    await start_support(call.message, state)
    await call.answer()


@router.callback_query(F.data == "sup_cancel")
async def cb_support_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, *(await menu_view(call.from_user.id)))
    await call.answer()


async def forward_to_admins(message: Message) -> None:
    header = texts.support_header(message.from_user)
    for admin_id in ADMIN_IDS:
        try:
            head = await bot.send_message(admin_id, header)
            copy = await message.copy_to(admin_id, reply_parameters=ReplyParameters(message_id=head.message_id))
            support_threads[(admin_id, head.message_id)] = message.from_user.id
            support_threads[(admin_id, copy.message_id)] = message.from_user.id
        except Exception as exc:
            services.log.warning("support to admin %s failed: %s", admin_id, exc)


@router.message(Support.waiting, ~F.text.startswith("/"))
async def on_support_message(message: Message, state: FSMContext) -> None:
    await forward_to_admins(message)
    await state.clear()
    await message.answer(texts.SUPPORT_SENT, reply_markup=keyboards.shop_kb())


def _is_support_answer(message: Message) -> bool:
    replied = message.reply_to_message
    return bool(replied and replied.from_user and replied.from_user.is_bot
                and (replied.text or replied.caption or "").startswith("💬 Ответ поддержки"))


@router.message(StateFilter(None), _is_support_answer)
async def on_support_reply(message: Message) -> None:
    """Покупатель отвечает реплаем на ответ поддержки — продолжаем диалог."""
    await forward_to_admins(message)
    await message.answer(texts.SUPPORT_SENT)
