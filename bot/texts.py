"""Все тексты бота в одном месте — правь здесь, код трогать не нужно."""
import html

STATUS_LABELS = {
    "awaiting_payment": "⏳ Ожидает оплаты",
    "checking": "🔎 Проверяем оплату",
    "paid": "✅ Оплачен",
    "shipped": "🚚 Отправлен",
    "done": "📦 Получен",
    "cancelled": "✖️ Отменён",
}


def e(value) -> str:
    return html.escape(str(value or ""))


def money(amount: int, currency: str) -> str:
    return f"{amount:,}".replace(",", " ") + f" {currency}"


WELCOME = (
    "<b>DAYZ DROP</b> — магазин одежды прямо в Telegram 🖤\n\n"
    "🛍 Выбирай вещи прямо кнопками ниже или в мини-приложении — как удобнее.\n"
    "💳 Оплата — переводом по реквизитам. Чек присылаешь сюда, мы проверяем и подтверждаем заказ.\n"
    "📦 Статус заказа и трек-номер придут в этот чат."
)
WELCOME_ADMIN = "\n\n⚙️ Ты админ — снизу есть кнопка админ-панели."

HELP = (
    "<b>Как сделать заказ</b>\n"
    "1. Открой «👕 Каталог» (или мини-приложение).\n"
    "2. Выбери вещь и размер, добавь в корзину.\n"
    "3. Оформи заказ — бот пришлёт реквизиты для перевода.\n"
    "4. Переведи сумму и пришли сюда скриншот или PDF чека.\n"
    "5. Мы проверим оплату вручную и подтвердим заказ, потом пришлём трек-номер.\n\n"
    "Команды: /start — меню, /catalog — каталог, /cart — корзина, /orders — мои заказы, "
    "/support — поддержка, /cancel — отменить ввод."
)

OPEN_SHOP = "Чтобы сделать заказ, открой магазин кнопкой ниже 👇"
NO_ORDERS = "У тебя пока нет заказов. Загляни в каталог 👇"
RECEIPT_NO_ORDER = (
    "Не нашёл заказов, которые ждут оплаты. Сначала оформи заказ в магазине, "
    "а если есть вопрос — напиши в поддержку."
)
RECEIPT_CHOOSE = "У тебя несколько неоплаченных заказов. К какому относится этот чек?"
RECEIPT_EXPIRED = "Не вижу чек — пришли его ещё раз, пожалуйста."
RECEIPT_RECEIVED = (
    "🧾 Чек по заказу <b>#{id}</b> получен!\n"
    "Проверяем оплату вручную — обычно это занимает до нескольких часов. Как подтвердим — сразу напишем."
)
ADMIN_ONLY = "Это только для админов."


def items_block(items: list, currency: str) -> str:
    return "\n".join(
        f"• {e(i['title'])} — {e(i['size'])} × {i['qty']} = {money(i['price'] * i['qty'], currency)}"
        for i in items
    )


def order_created(order, settings: dict) -> str:
    cur = settings["currency"]
    return (
        f"🧾 <b>Заказ #{order.id} оформлен!</b>\n\n"
        f"{items_block(order.items, cur)}\n"
        f"<b>Итого: {money(order.total, cur)}</b>\n\n"
        f"💳 <b>Оплата переводом:</b>\n{e(settings['payment_details'])}\n\n"
        f"В комментарии к переводу укажи: <code>Заказ #{order.id}</code>\n\n"
        "После оплаты <b>пришли сюда скриншот или PDF чека</b> — "
        "мы проверим поступление и подтвердим заказ."
    )


def _customer(order) -> str:
    username = f"@{e(order.username)}, " if order.username else ""
    return f"{e(order.customer_name)} ({username}id <code>{order.user_id}</code>)"


def admin_new_order(order, currency: str, title: str | None = None) -> str:
    lines = [
        title or f"🆕 <b>Новый заказ #{order.id}</b>",
        "",
        f"👤 {_customer(order)}",
        f"📞 {e(order.phone)}",
        f"🚚 {e(order.delivery)}",
    ]
    if order.address:
        lines.append(f"📍 {e(order.address)}")
    if order.comment:
        lines.append(f"💬 {e(order.comment)}")
    lines += [
        "",
        items_block(order.items, currency),
        f"<b>Итого: {money(order.total, currency)}</b>",
        "",
        f"Статус: {STATUS_LABELS.get(order.status, order.status)}",
    ]
    if order.track:
        lines.append(f"Трек: <code>{e(order.track)}</code>")
    lines.append("\n<i>Ответь реплаем на это сообщение — ответ уйдёт покупателю.</i>")
    return "\n".join(lines)


def admin_order_card(order, currency: str) -> str:
    return admin_new_order(order, currency, title=f"🧾 <b>Заказ #{order.id}</b>")


def admin_receipt(order, currency: str) -> str:
    return (
        f"💳 <b>Чек по заказу #{order.id}</b>\n"
        f"Сумма к оплате: <b>{money(order.total, currency)}</b>\n"
        f"👤 {_customer(order)}\n\n"
        "Проверь поступление денег и нажми кнопку 👇"
    )


def admin_decision(order, admin_name: str, confirmed: bool) -> str:
    mark = "✅ Оплату подтвердил" if confirmed else "❌ Чек отклонил"
    return f"\n\n{mark}: {e(admin_name)}"


def status_update(order, currency: str) -> str | None:
    s, n = order.status, order.id
    if s == "paid":
        return f"✅ Оплата по заказу <b>#{n}</b> подтверждена! Собираем заказ и скоро отправим."
    if s == "shipped":
        text = f"🚚 Заказ <b>#{n}</b> отправлен!"
        if order.track:
            text += f"\nТрек-номер: <code>{e(order.track)}</code>"
        return text
    if s == "done":
        return f"📦 Заказ <b>#{n}</b> получен. Спасибо, что выбрал DAYZ DROP! 🖤"
    if s == "cancelled":
        return f"✖️ Заказ <b>#{n}</b> отменён. Если это ошибка — напиши в поддержку."
    if s == "awaiting_payment":
        return (
            f"⚠️ Не нашли оплату по заказу <b>#{n}</b> по присланному чеку.\n"
            f"Проверь перевод на {money(order.total, currency)} и пришли чек ещё раз или напиши в поддержку."
        )
    return None


# ---------- магазин на кнопках ----------

MENU = "<b>DAYZ DROP</b> 🖤\nВыбирай, что открыть:"
UNKNOWN = "Не понял 🙂 Выбери, что открыть:"
CANCELLED = "Ок, отменил."
CATALOG = "👕 <b>Каталог</b>\nВыбери категорию:"
CATALOG_EMPTY = "Каталог пока пуст — скоро здесь появятся вещи 🖤"
CART_EMPTY = "🛒 Корзина пуста. Загляни в каталог 👇"
NO_STOCK = "Этого размера больше нет в наличии"

ASK_NAME = "✍️ <b>Оформление заказа</b>\n\nКак зовут получателя? Напиши имя и фамилию."
ASK_PHONE = "📱 Номер телефона для связи и доставки — нажми кнопку ниже или напиши его."
PHONE_SAVED = "Номер сохранён ✅"
ASK_DELIVERY = "🚚 Как доставить заказ?"
ASK_ADDRESS = "📍 Напиши город и адрес (или адрес пункта выдачи)."
ASK_COMMENT = "💬 Комментарий к заказу? Если нет — нажми «Пропустить»."
CHECKOUT_CANCELLED = "Оформление отменено. Корзина сохранена 🛒"
ORDER_DONE = "✅ Заказ <b>#{id}</b> оформлен! Реквизиты для оплаты — в следующем сообщении 👇"

SUPPORT_ASK = (
    "💬 <b>Поддержка</b>\n\n"
    "Напиши свой вопрос одним сообщением (можно с фото) — его получат админы, ответ придёт сюда."
)
SUPPORT_SENT = "✅ Сообщение отправлено админам. Ответ придёт в этот чат."
SUPPORT_ANSWER = "💬 <b>Ответ поддержки DAYZ DROP</b>\n<i>Чтобы ответить — ответь реплаем на это сообщение.</i>"
SUPPORT_DELIVERED = "✅ Ответ отправлен покупателю"


def support_header(user) -> str:
    username = f" (@{e(user.username)})" if user.username else ""
    return (
        f"💬 <b>Сообщение в поддержку</b>\n"
        f"👤 {e(user.full_name)}{username}, id <code>{user.id}</code>\n\n"
        "<i>Ответь реплаем на это или следующее сообщение — ответ уйдёт покупателю.</i>"
    )


def stock_total(product) -> int:
    return sum(s["stock"] for s in product.sizes)


def product_card(product, currency: str) -> str:
    sizes = ", ".join(e(s["size"]) + ("" if s["stock"] else " (нет)") for s in product.sizes)
    lines = [f"<b>{e(product.title)}</b>", f"💰 {money(product.price, currency)}"]
    if product.category:
        lines.append(f"🏷 {e(product.category)}")
    lines.append(f"📏 Размеры: {sizes}")
    if product.description:
        lines += ["", e(product.description[:700])]
    lines += ["", "Выбери размер, чтобы добавить в корзину 👇" if stock_total(product) else "Сейчас нет в наличии"]
    return "\n".join(lines)


def cart_text(lines: list, currency: str) -> str:
    total = sum(l["product"].price * l["qty"] for l in lines)
    rows = [
        f"• {e(l['product'].title)} — {e(l['size'])} × {l['qty']} = {money(l['product'].price * l['qty'], currency)}"
        for l in lines
    ]
    return "🛒 <b>Корзина</b>\n\n" + "\n".join(rows) + f"\n\n<b>Итого: {money(total, currency)}</b>"


def checkout_summary(data: dict, lines: list, currency: str) -> str:
    total = sum(l["product"].price * l["qty"] for l in lines)
    rows = [
        "🧾 <b>Проверь заказ</b>",
        "",
        "\n".join(f"• {e(l['product'].title)} — {e(l['size'])} × {l['qty']}" for l in lines),
        f"<b>Итого: {money(total, currency)}</b>",
        "",
        f"👤 {e(data['customer_name'])}",
        f"📞 {e(data['phone'])}",
        f"🚚 {e(data['delivery'])}",
    ]
    if data.get("address"):
        rows.append(f"📍 {e(data['address'])}")
    if data.get("comment"):
        rows.append(f"💬 {e(data['comment'])}")
    rows += ["", "Всё верно?"]
    return "\n".join(rows)


# ---------- админка на кнопках ----------

def admin_menu(counts: dict) -> str:
    return (
        "⚙️ <b>Админ-панель DAYZ DROP</b>\n\n"
        f"🔎 Ждут проверки оплаты: <b>{counts.get('checking', 0)}</b>\n"
        f"⏳ Ждут оплату: <b>{counts.get('awaiting_payment', 0)}</b>\n"
        f"📦 Оплачены, нужно отправить: <b>{counts.get('paid', 0)}</b>\n"
        f"🚚 В пути: <b>{counts.get('shipped', 0)}</b>"
    )


def admin_product_card(product, currency: str) -> str:
    sizes = "\n".join(f"   {e(s['size'])}: {s['stock']} шт" for s in product.sizes) or "   —"
    return (
        f"<b>{e(product.title)}</b>\n"
        f"💰 {money(product.price, currency)}\n"
        f"🏷 {e(product.category) or 'без категории'}\n"
        f"👁 {'Показывается в каталоге' if product.is_active else 'Скрыт из каталога'}\n"
        f"🖼 Фото: {len(product.photos)}\n"
        f"📦 Остатки:\n{sizes}\n\n"
        f"{e(product.description[:600]) if product.description else '<i>Без описания</i>'}"
    )


SIZES_HINT = (
    "Пришли размеры и остатки через запятую или с новой строки, например:\n"
    "<code>S 3, M 5, L 2, XL 0</code>\nили <code>One size 10</code>"
)
ASK_PRODUCT = {
    "title": "✏️ Название товара:",
    "category": "🏷 Категория (например: Худи, Футболки). Выбери или напиши новую:",
    "price": "💰 Цена (только число):",
    "description": "📝 Описание (материал, посадка, уход):",
    "sizes": "📦 " + SIZES_HINT,
    "photos": "🖼 Пришли фото товара (можно несколько, первое — обложка). Потом нажми «Готово».",
}
ASK_SETTING = {
    "payment_details": "💳 Пришли реквизиты для оплаты (номер карты, банк, получатель):",
    "currency": "💱 Валюта (например ₽, сум, $):",
    "delivery_options": "🚚 Способы доставки — каждый с новой строки:",
}
ASK_TRACK = "🚚 Пришли трек-номер отправления (или нажми «Без трека»):"
BAD_PRICE = "Цена должна быть целым числом, например 4990"
BAD_SIZES = "Не понял размеры. " + SIZES_HINT
SAVED = "✅ Сохранено"


def admin_settings(settings: dict) -> str:
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"💳 <b>Реквизиты:</b>\n{e(settings['payment_details'])}\n\n"
        f"💱 <b>Валюта:</b> {e(settings['currency'])}\n\n"
        f"🚚 <b>Доставка:</b>\n{e(settings['delivery_options'])}"
    )


def admin_stats(by_status: dict, revenue: int, users: int, products: int, currency: str) -> str:
    total = sum(by_status.values())
    return (
        "📊 <b>Статистика</b>\n\n"
        f"💰 Выручка (оплаченные): <b>{money(revenue, currency)}</b>\n"
        f"🧾 Всего заказов: <b>{total}</b>\n"
        + "\n".join(f"   {STATUS_LABELS[s]}: {by_status.get(s, 0)}" for s in STATUS_LABELS)
        + f"\n👥 Пользователей бота: <b>{users}</b>\n👕 Товаров: <b>{products}</b>"
    )


def my_orders(orders: list, currency: str) -> str:
    lines = ["<b>Твои заказы:</b>", ""]
    for o in orders:
        lines.append(f"#{o.id} — {money(o.total, currency)} — {STATUS_LABELS.get(o.status, o.status)}")
        if o.track:
            lines.append(f"    трек: <code>{e(o.track)}</code>")
    return "\n".join(lines)
