"""Магазин на обычных кнопках бота: каталог, корзина, оформление, профиль с баллами, поддержка."""
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
from sqlalchemy import delete, select

import keyboards
import loyalty
import services
import texts
from config import ADMIN_IDS
from db import Coupon, Order, Product, Reward, Session, Subscription, User
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
    payment = State()
    coupon = State()
    comment = State()
    confirm = State()


class Support(StatesGroup):
    waiting = State()


class Register(StatesGroup):
    phone = State()


def _contact_kb(text: str = "📱 Отправить мой номер") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=text, request_contact=True)]],
                               resize_keyboard=True, one_time_keyboard=True)


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
        mark = " · скоро" if p.badge == "soon" else ("" if texts.stock_total(p) else " · нет в наличии")
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


def product_kb(product: Product, cat_index: int, cart_count: int, subscribed: set[str]):
    rows = []
    if product.badge == "soon":
        on = "*" in subscribed
        rows.append([btn("🔔 Сообщим о старте продаж ✓" if on else "🔔 Сообщить о поступлении", f"sub:{product.id}:{cat_index}:*")])
    else:
        sizes = [
            btn(s["size"], f"a:{product.id}:{cat_index}:{s['size']}") if s["stock"]
            else btn(f"🔔 {s['size']}" + (" ✓" if s["size"] in subscribed else ""), f"sub:{product.id}:{cat_index}:{s['size']}")
            for s in product.sizes
        ]
        rows = chunks(sizes, 4)
        if any(not s["stock"] for s in product.sizes):
            rows.append([btn("🔔 у размера — сообщим, когда появится", "noop")])
    if len(product.photos) > 1:
        rows.append([btn(f"🖼 Все фото ({len(product.photos)})", f"ph:{product.id}")])
    rows.append([btn(f"🛒 Корзина{f' ({cart_count})' if cart_count else ''}", "cart"), btn("⬅️ Назад", f"c:{cat_index}:0")])
    return kb(*rows)


async def _subscribed(session, user_id: int, product_id: int) -> set[str]:
    return {s.size for s in (await session.execute(
        select(Subscription).where(Subscription.user_id == user_id, Subscription.product_id == product_id))).scalars()}


async def product_view(product_id: int, cat_index: int, user_id: int):
    async with Session() as session:
        product = await session.get(Product, product_id)
        settings = await services.get_settings(session)
        count = sum(i["qty"] for i in await services.get_cart(session, user_id))
        subscribed = await _subscribed(session, user_id, product_id)
    if not product or not product.is_active:
        return "Товар больше недоступен", kb([btn("⬅️ Каталог", "cat")]), None
    photo = product.photos[0] if product.photos else None
    return texts.product_card(product, settings["currency"]), product_kb(product, cat_index, count, subscribed), photo


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


@router.callback_query(F.data.startswith("sub:"))
async def cb_subscribe(call: CallbackQuery) -> None:
    """«Сообщить о поступлении» — повторное нажатие отменяет подписку."""
    _, product_id, cat_index, size = call.data.split(":", 3)
    product_id = int(product_id)
    async with Session() as session:
        await services.upsert_user(session, call.from_user)
        existing = await _subscribed(session, call.from_user.id, product_id)
        await session.execute(delete(Subscription).where(
            Subscription.user_id == call.from_user.id, Subscription.product_id == product_id, Subscription.size == size))
        if size not in existing:
            session.add(Subscription(user_id=call.from_user.id, product_id=product_id, size=size))
        await session.commit()
        product = await session.get(Product, product_id)
        count = sum(i["qty"] for i in await services.get_cart(session, call.from_user.id))
        subscribed = await _subscribed(session, call.from_user.id, product_id)
    await call.answer("🔔 Напишем, как только появится" if size not in existing else "Подписка снята")
    try:
        await call.message.edit_reply_markup(reply_markup=product_kb(product, int(cat_index), count, subscribed))
    except Exception:
        pass


@router.callback_query(F.data.startswith("a:"))
async def cb_add_to_cart(call: CallbackQuery) -> None:
    _, product_id, cat_index, size = call.data.split(":", 3)
    async with Session() as session:
        product = await session.get(Product, int(product_id))
        entry = next((s for s in product.sizes if s["size"] == size), None) if product else None
        cart = await services.get_cart(session, call.from_user.id)
        item = next((i for i in cart if i["product_id"] == product.id and i["size"] == size), None) if product else None
        if (not product or not product.is_active or product.badge == "soon" or not entry
                or entry["stock"] <= (item["qty"] if item else 0)):
            await call.answer(texts.NO_STOCK, show_alert=True)
            return
        if item:
            item["qty"] += 1
        else:
            cart.append({"product_id": product.id, "size": size, "qty": 1})
        await services.set_cart(session, call.from_user.id, cart)
        subscribed = await _subscribed(session, call.from_user.id, product.id)
    count = sum(i["qty"] for i in cart)
    await call.answer(f"✅ В корзине: {product.title}, {size}")
    try:
        await call.message.edit_reply_markup(reply_markup=product_kb(product, int(cat_index), count, subscribed))
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

CANCEL_ROW = [btn("❌ Отменить", "co_cancel")]


async def _quote(user_id: int, data: dict, strict: bool = False):
    async with Session() as session:
        cart = await services.get_cart(session, user_id)
        return await services.quote(session, user_id, {**data, "items": cart}, strict=strict)


@router.callback_query(F.data == "co")
async def co_start(call: CallbackQuery, state: FSMContext) -> None:
    async with Session() as session:
        lines = await services.cart_lines(session, call.from_user.id)
        user = await session.get(User, call.from_user.id)
    if not lines:
        await show(call, *(await cart_view(call.from_user.id)))
        await call.answer("Корзина пуста")
        return
    await state.clear()
    await state.set_state(Checkout.name)
    name = (user.full_name if user and user.full_name else call.from_user.full_name)[:40]
    await state.update_data(saved_name=name, saved_phone=user.phone if user else None)
    await call.message.answer(texts.ASK_NAME, reply_markup=kb([btn(f"✅ {name}", "co_name")], CANCEL_ROW))
    await call.answer()


async def _ask_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(Checkout.phone)
    saved = (await state.get_data()).get("saved_phone")
    await message.answer(texts.ASK_PHONE, reply_markup=_contact_kb())
    if saved:
        await message.answer("Или используй сохранённый номер:", reply_markup=kb([btn(f"✅ {saved}", "co_phone")]))


@router.callback_query(Checkout.name, F.data == "co_name")
async def co_name_button(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(customer_name=(await state.get_data())["saved_name"])
    await call.message.edit_reply_markup(reply_markup=None)
    await _ask_phone(call.message, state)
    await call.answer()


@router.message(Checkout.name, F.text, NOT_COMMAND)
async def co_name_text(message: Message, state: FSMContext) -> None:
    await state.update_data(customer_name=message.text.strip()[:200])
    await _ask_phone(message, state)


async def _ask_delivery(message: Message, state: FSMContext, phone: str, user_id: int) -> None:
    await state.update_data(phone=loyalty.normalize_phone(phone) or phone[:50])
    await message.answer(texts.PHONE_SAVED, reply_markup=ReplyKeyboardRemove())
    q = await _quote(user_id, await state.get_data())
    async with Session() as session:
        methods = services.delivery_methods(await services.get_settings(session))
    await state.set_state(Checkout.delivery)
    rows = []
    for m in methods:
        cost = services.delivery_cost(m, q["subtotal"])
        price = texts.money(cost, q["settings"]["currency"]) if cost else "бесплатно"
        rows.append([btn(f"{m['name']} · {price}", f"dl:{m['id']}")])
    rows.append(CANCEL_ROW)
    await message.answer(texts.ASK_DELIVERY, reply_markup=kb(*rows))


@router.callback_query(Checkout.phone, F.data == "co_phone")
async def co_phone_saved(call: CallbackQuery, state: FSMContext) -> None:
    await call.message.edit_reply_markup(reply_markup=None)
    await _ask_delivery(call.message, state, (await state.get_data())["saved_phone"], call.from_user.id)
    await call.answer()


@router.message(Checkout.phone, F.contact)
async def co_phone_contact(message: Message, state: FSMContext) -> None:
    await _ask_delivery(message, state, message.contact.phone_number, message.from_user.id)


@router.message(Checkout.phone, F.text, NOT_COMMAND)
async def co_phone_text(message: Message, state: FSMContext) -> None:
    await _ask_delivery(message, state, message.text.strip(), message.from_user.id)


async def _ask_payment(message: Message, state: FSMContext, user_id: int) -> None:
    q = await _quote(user_id, await state.get_data())
    options = [(k, label) for k, label in (("card", "💳 Картой (перевод)"), ("cash", "🤝 Наличными при получении"))
               if q["payments"][k]]
    if len(options) == 1:  # выбирать не из чего — сразу дальше
        await state.update_data(payment=options[0][0])
        await message.answer(f"Оплата: {options[0][1]}")
        await _ask_coupon(message, state)
        return
    if not options:
        await state.clear()
        await message.answer("Сейчас нет доступного способа оплаты для этой доставки — напиши в поддержку.",
                             reply_markup=kb([btn("💬 Поддержка", "support")]))
        return
    await state.set_state(Checkout.payment)
    await message.answer(texts.ASK_PAYMENT, reply_markup=kb(*[[btn(label, f"pay_m:{k}")] for k, label in options], CANCEL_ROW))


@router.callback_query(Checkout.delivery, F.data.startswith("dl:"))
async def co_delivery(call: CallbackQuery, state: FSMContext) -> None:
    async with Session() as session:
        method = services.find_delivery(await services.get_settings(session), call.data.split(":", 1)[1])
    if not method:
        await call.answer("Выбери вариант из списка", show_alert=True)
        return
    await state.update_data(delivery=method["id"])
    note = f"\n<i>{texts.e(method['note'])}</i>" if method.get("note") else ""
    await call.message.edit_text(f"{texts.ASK_DELIVERY}\n\n✅ {texts.e(method['name'])}{note}")
    if method["address"]:
        await state.set_state(Checkout.address)
        await call.message.answer(texts.ASK_ADDRESS, reply_markup=kb(CANCEL_ROW))
    else:
        await state.update_data(address="")
        await _ask_payment(call.message, state, call.from_user.id)
    await call.answer()


@router.message(Checkout.address, F.text, NOT_COMMAND)
async def co_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text.strip()[:1000])
    await _ask_payment(message, state, message.from_user.id)


@router.callback_query(Checkout.payment, F.data.startswith("pay_m:"))
async def co_payment(call: CallbackQuery, state: FSMContext) -> None:
    payment = call.data.split(":")[1]
    await state.update_data(payment=payment)
    label = "💳 Картой" if payment == "card" else "🤝 Наличными при получении"
    await call.message.edit_text(f"{texts.ASK_PAYMENT}\n\n✅ {label}")
    await _ask_coupon(call.message, state)
    await call.answer()


async def _ask_coupon(message: Message, state: FSMContext) -> None:
    await state.set_state(Checkout.coupon)
    await message.answer(texts.ASK_COUPON, reply_markup=kb([btn("Нет промокода", "co_nocoupon")], CANCEL_ROW))


@router.message(Checkout.coupon, F.text, NOT_COMMAND)
async def co_coupon(message: Message, state: FSMContext) -> None:
    code = loyalty.normalize_code(message.text)
    q = await _quote(message.from_user.id, {**(await state.get_data()), "coupon": code})
    if q["coupon_error"]:
        await message.answer(f"⚠️ {texts.e(q['coupon_error'])}\nПопробуй другой код или нажми «Нет промокода».",
                             reply_markup=kb([btn("Нет промокода", "co_nocoupon")]))
        return
    await state.update_data(coupon=code)
    await message.answer(f"✅ Промокод применён: −{texts.money(q['discount'], q['settings']['currency'])}")
    await _ask_comment(message, state)


@router.callback_query(Checkout.coupon, F.data == "co_nocoupon")
async def co_no_coupon(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(coupon="")
    await call.message.edit_reply_markup(reply_markup=None)
    await _ask_comment(call.message, state)
    await call.answer()


async def _ask_comment(message: Message, state: FSMContext) -> None:
    await state.set_state(Checkout.comment)
    await message.answer(texts.ASK_COMMENT, reply_markup=kb([btn("Пропустить", "co_skip")], CANCEL_ROW))


async def _confirm(message: Message, state: FSMContext, user_id: int) -> None:
    await state.set_state(Checkout.confirm)
    data = await state.get_data()
    try:
        q = await _quote(user_id, data, strict=True)
    except services.ShopError as exc:
        await state.clear()
        await message.answer(f"⚠️ {texts.e(exc)}", reply_markup=kb([btn("🛒 Корзина", "cart")]))
        return
    await message.answer(
        texts.checkout_summary(data, q, q["settings"]["currency"]),
        reply_markup=kb([btn("✅ Подтвердить заказ", "co_ok")], CANCEL_ROW),
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
        await services.upsert_user(session, call.from_user)
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


# ---------- оценка заказа ----------

@router.callback_query(F.data.startswith("rate:"))
async def cb_rate(call: CallbackQuery) -> None:
    _, order_id, rating = call.data.split(":")
    async with Session() as session:
        order = await session.get(Order, int(order_id))
        if not order or order.user_id != call.from_user.id or order.status != "done":
            await call.answer("Оценить можно только полученный заказ", show_alert=True)
            return
        order.rating = max(1, min(5, int(rating)))
        await session.commit()
    stars = "⭐" * order.rating
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"Спасибо за оценку {stars}! Если есть что добавить — напиши в поддержку.")
    await services.notify_admins(f"⭐ Оценка заказа #{order.id}: {stars}")
    await call.answer()


# ---------- профиль и баллы ----------

async def profile_view(user_id: int):
    async with Session() as session:
        user = await session.get(User, user_id)
        settings = await services.get_settings(session)
        if not user or not user.registered_at:
            text = texts.PROFILE_GUEST.format(welcome=settings["welcome_points"], percent=settings["earn_percent"])
            return text, kb([btn("📝 Зарегистрироваться", "reg")], [btn("⬅️ Меню", "menu")])
        coupons = list((await session.execute(
            select(Coupon).where(Coupon.user_id == user_id).order_by(Coupon.id.desc()))).scalars())
        rewards = list((await session.execute(
            select(Reward).where(Reward.is_active.is_(True)).order_by(Reward.sort, Reward.cost))).scalars())
    rows = [[btn(f"{'🎁' if (user.points or 0) >= r.cost else '🔒'} {r.title} · {r.cost} б.", f"rw:{r.id}")] for r in rewards[:8]]
    rows.append([btn("⬅️ Меню", "menu")])
    return texts.profile_text(user, coupons, settings["currency"]), kb(*rows)


async def send_profile(message: Message, user_id: int) -> None:
    text, markup = await profile_view(user_id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, *(await profile_view(call.from_user.id)))
    await call.answer()


@router.callback_query(F.data == "reg")
async def cb_register(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Register.phone)
    await call.message.answer(texts.REGISTER_ASK, reply_markup=_contact_kb("📱 Поделиться номером и зарегистрироваться"))
    await call.answer()


@router.message(Register.phone, F.contact)
async def on_register_contact(message: Message, state: FSMContext) -> None:
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer("Нужен именно твой номер — нажми кнопку ниже.", reply_markup=_contact_kb())
        return
    name = " ".join(filter(None, [message.contact.first_name, message.contact.last_name])) or message.from_user.full_name
    async with Session() as session:
        try:
            user = await loyalty.register_user(session, message.from_user, name, message.contact.phone_number)
        except services.ShopError as exc:
            await message.answer(f"⚠️ {texts.e(exc)}", reply_markup=ReplyKeyboardRemove())
            await state.clear()
            return
    await state.clear()
    await message.answer(texts.REGISTER_DONE.format(points=user.points or 0), reply_markup=ReplyKeyboardRemove())
    await send_profile(message, message.from_user.id)


@router.callback_query(F.data.startswith("rw:"))
async def cb_reward(call: CallbackQuery) -> None:
    async with Session() as session:
        user = await session.get(User, call.from_user.id)
        reward = await session.get(Reward, int(call.data.split(":")[1]))
        if not user or not reward:
            await call.answer("Награда не найдена", show_alert=True)
            return
        try:
            await loyalty.exchange_reward(session, user, reward)
        except services.ShopError as exc:
            await call.answer(str(exc), show_alert=True)
            return
    await call.answer("Готово! Купон пришёл сообщением")
    await show(call, *(await profile_view(call.from_user.id)))


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
