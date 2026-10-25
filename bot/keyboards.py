from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import WEBAPP_URL


def webapp_url(**params) -> str:
    if not params:
        return WEBAPP_URL
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}{query}"


def support_url(contact: str) -> str | None:
    contact = (contact or "").strip()
    if contact.startswith("@"):
        return f"https://t.me/{contact[1:]}"
    if contact.startswith("http"):
        return contact
    return None


def _app_button(text: str, **params) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url(**params)))


def _cb(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def start_kb(is_admin: bool, cart_count: int = 0) -> InlineKeyboardMarkup:
    rows = []
    if WEBAPP_URL:
        rows.append([_app_button("🛍 Открыть магазин (мини-апп)")])
    rows.append([_cb("👕 Каталог", "cat"), _cb(f"🛒 Корзина{f' ({cart_count})' if cart_count else ''}", "cart")])
    rows.append([_cb("📦 Мои заказы", "my_orders"), _cb("👤 Профиль и баллы", "profile")])
    rows.append([_cb("💬 Поддержка", "support")])
    if is_admin:
        rows.append([_cb("⚙️ Админ-панель", "adm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_kb() -> InlineKeyboardMarkup:
    rows = []
    if WEBAPP_URL:
        rows.append([_app_button("🛍 Открыть магазин (мини-апп)")])
    rows.append([_cb("👕 Каталог", "cat"), _cb("🛒 Корзина", "cart")])
    rows.append([_cb("⬅️ Меню", "menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_kb(order_id: int) -> InlineKeyboardMarkup:
    rows = [[_cb("📦 Мои заказы", "my_orders"), _cb("💬 Поддержка", "support")]]
    if WEBAPP_URL:
        rows.insert(0, [_app_button("📦 Открыть заказ в мини-аппе", page="order", id=order_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_kb(order_id: int) -> InlineKeyboardMarkup:
    rows = [[_cb("⚙️ Открыть заказ в админке", f"ao:{order_id}")]]
    if WEBAPP_URL:
        rows.append([_app_button("🛍 В мини-аппе", page="admin", order=order_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def receipt_admin_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Деньги пришли", callback_data=f"pay:ok:{order_id}"),
                InlineKeyboardButton(text="❌ Не пришли", callback_data=f"pay:no:{order_id}"),
            ]
        ]
    )


def choose_order_kb(orders: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Заказ #{o.id}", callback_data=f"rcpt:{o.id}")] for o in orders
        ]
    )


def rate_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_cb("⭐" * n, f"rate:{order_id}:{n}") for n in (1, 2, 3)],
                                                 [_cb("⭐" * n, f"rate:{order_id}:{n}") for n in (4, 5)]])


def product_kb(product_id: int) -> InlineKeyboardMarkup:
    rows = []
    if WEBAPP_URL:
        rows.append([_app_button("🛍 Смотреть", page="product", id=product_id)])
    rows.append([_cb("👕 Каталог", "cat")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_kb() -> InlineKeyboardMarkup:
    rows = [[_cb("👤 Профиль и баллы", "profile")]]
    if WEBAPP_URL:
        rows.append([_app_button("🎁 Обменять баллы в мини-аппе", page="profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_open_kb() -> InlineKeyboardMarkup:
    if WEBAPP_URL:
        return InlineKeyboardMarkup(inline_keyboard=[[_app_button("🛍 Смотреть в магазине")]])
    return InlineKeyboardMarkup(inline_keyboard=[[_cb("👕 Открыть каталог", "cat")]])
