from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import select

import admin_bot
import keyboards
import services
import shop_bot
import texts
from config import ADMIN_IDS
from db import Order, Session

# Команды — первыми: работают из любого шага, сбрасывая незаконченный ввод
router = Router()
# Чеки, решения по оплате и «не понял» — последними, после магазина и админки
misc_router = Router()

LOGO = Path(__file__).parent / "assets" / "logo.png"

# Чек, присланный в чат, пока пользователь выбирает, к какому заказу он относится
_pending_receipts: dict[int, tuple[str, str]] = {}


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    async with Session() as session:
        await services.upsert_user(session, message.from_user)
    if command.args == "support":
        await shop_bot.start_support(message, state)
        return
    is_admin = message.from_user.id in ADMIN_IDS
    caption = texts.WELCOME + (texts.WELCOME_ADMIN if is_admin else "")
    _, markup = await shop_bot.menu_view(message.from_user.id)
    if LOGO.exists():
        await message.answer_photo(FSInputFile(LOGO), caption=caption, reply_markup=markup)
    else:
        await message.answer(caption, reply_markup=markup)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, markup = await shop_bot.menu_view(message.from_user.id)
    await message.answer(texts.CANCELLED + "\n\n" + text, reply_markup=markup)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.HELP, reply_markup=keyboards.shop_kb())


@router.message(Command("catalog"))
async def cmd_catalog(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, markup = await shop_bot.catalog_view()
    await message.answer(text, reply_markup=markup)


@router.message(Command("cart"))
async def cmd_cart(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, markup = await shop_bot.cart_view(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext) -> None:
    await state.clear()
    await shop_bot.start_support(message, state)


async def _my_orders_text(user_id: int) -> str:
    async with Session() as session:
        settings = await services.get_settings(session)
        orders = (
            await session.execute(
                select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(10)
            )
        ).scalars().all()
    return texts.my_orders(orders, settings["currency"]) if orders else texts.NO_ORDERS


@router.message(Command("orders"))
async def cmd_orders(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(await _my_orders_text(message.from_user.id), reply_markup=keyboards.shop_kb())


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(texts.ADMIN_ONLY)
        return
    text, markup = await admin_bot.admin_menu_view()
    await message.answer(text, reply_markup=markup)


@misc_router.callback_query(F.data == "my_orders")
async def cb_orders(call: CallbackQuery) -> None:
    await call.message.answer(await _my_orders_text(call.from_user.id), reply_markup=keyboards.shop_kb())
    await call.answer()


# ---------- чеки от покупателей ----------

async def _attach(message: Message, order_id: int, file_id: str, kind: str) -> None:
    async with Session() as session:
        order = await session.get(Order, order_id)
        if not order or order.user_id != message.chat.id:
            await message.answer(texts.RECEIPT_NO_ORDER)
            return
        try:
            await services.attach_receipt(session, order, file_id=file_id, kind=kind)
        except services.ShopError as exc:
            await message.answer(str(exc))


@misc_router.message(F.photo | F.document)
async def on_receipt(message: Message) -> None:
    if message.photo:
        file_id, kind = message.photo[-1].file_id, "photo"
    else:
        file_id, kind = message.document.file_id, "document"

    async with Session() as session:
        orders = (
            await session.execute(
                select(Order)
                .where(Order.user_id == message.from_user.id, Order.status.in_(["awaiting_payment", "checking"]))
                .order_by(Order.id.desc())
            )
        ).scalars().all()

    if not orders:
        await message.answer(texts.RECEIPT_NO_ORDER, reply_markup=keyboards.shop_kb())
    elif len(orders) == 1:
        await _attach(message, orders[0].id, file_id, kind)
    else:
        _pending_receipts[message.from_user.id] = (file_id, kind)
        await message.answer(texts.RECEIPT_CHOOSE, reply_markup=keyboards.choose_order_kb(orders))


@misc_router.callback_query(F.data.startswith("rcpt:"))
async def cb_choose_order(call: CallbackQuery) -> None:
    pending = _pending_receipts.pop(call.from_user.id, None)
    await call.message.edit_reply_markup(reply_markup=None)
    if not pending:
        await call.message.answer(texts.RECEIPT_EXPIRED)
    else:
        await _attach(call.message, int(call.data.split(":")[1]), *pending)
    await call.answer()


# ---------- решение админа по чеку ----------

@misc_router.callback_query(F.data.startswith("pay:"))
async def cb_payment_decision(call: CallbackQuery) -> None:
    if call.from_user.id not in ADMIN_IDS:
        await call.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    _, decision, order_id = call.data.split(":")
    confirmed = decision == "ok"

    async with Session() as session:
        order = await session.get(Order, int(order_id))
        if not order:
            await call.answer("Заказ не найден", show_alert=True)
            return
        if order.status != "checking":
            await call.answer(f"Уже решено: {texts.STATUS_LABELS[order.status]}", show_alert=True)
            await call.message.edit_reply_markup(reply_markup=keyboards.admin_order_kb(order.id))
            return
        await services.change_status(session, order, "paid" if confirmed else "awaiting_payment")

    admin_name = call.from_user.full_name
    await call.message.edit_caption(
        caption=(call.message.html_text or "") + texts.admin_decision(order, admin_name, confirmed),
        reply_markup=keyboards.admin_order_kb(order.id),
    )
    for admin_id in ADMIN_IDS - {call.from_user.id}:
        verdict = "подтвердил оплату" if confirmed else "отклонил чек"
        await services.safe_send(admin_id, f"ℹ️ {texts.e(admin_name)} {verdict} по заказу #{order.id}")
    await call.answer("Готово")


@misc_router.message()
async def fallback(message: Message) -> None:
    text, markup = await shop_bot.menu_view(message.from_user.id)
    await message.answer(texts.UNKNOWN, reply_markup=markup)
