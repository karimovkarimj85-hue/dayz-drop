"""Все тексты бота в одном месте — правь здесь, код трогать не нужно."""
import html

STATUS_LABELS = {
    "awaiting_payment": "⏳ Ожидает оплаты",
    "checking": "🔎 Проверяем оплату",
    "confirmed": "🤝 Подтверждён · оплата при получении",
    "paid": "✅ Оплачен",
    "shipped": "🚚 Отправлен",
    "done": "📦 Получен",
    "cancelled": "✖️ Отменён",
}
STATUS_PLAIN = {
    "awaiting_payment": "Ожидает оплаты",
    "checking": "Проверяем оплату",
    "confirmed": "Подтверждён (наличные)",
    "paid": "Оплачен",
    "shipped": "Отправлен",
    "done": "Получен",
    "cancelled": "Отменён",
}
KIND_LABELS = {"receipt": "📥 Приход", "sale": "🛒 Продажа", "return": "↩️ Возврат", "writeoff": "🗑 Списание",
               "inventory": "📋 Инвентаризация", "adjust": "✏️ Корректировка"}
KIND_PLAIN = {"receipt": "Приход", "sale": "Продажа", "return": "Возврат", "writeoff": "Списание",
              "inventory": "Инвентаризация", "adjust": "Корректировка"}


def e(value) -> str:
    return html.escape(str(value or ""))


def money(amount: int, currency: str) -> str:
    return f"{int(amount or 0):,}".replace(",", " ") + f" {currency}"


WELCOME = (
    "<b>DAYZ DROP</b> — магазин одежды прямо в Telegram 🖤\n\n"
    "🛍 Выбирай вещи кнопками ниже или в мини-приложении — как удобнее.\n"
    "💳 Оплата переводом на карту (чек присылаешь сюда) или наличными при получении.\n"
    "🎁 Зарегистрируйся в профиле — копи баллы и меняй их на скидки и вещи.\n"
    "📦 Статус заказа и трек-номер придут в этот чат."
)
WELCOME_ADMIN = "\n\n⚙️ Ты админ — снизу есть кнопка админ-панели."

HELP = (
    "<b>Как сделать заказ</b>\n"
    "1. Открой «👕 Каталог» (или мини-приложение).\n"
    "2. Выбери вещь и размер, добавь в корзину.\n"
    "3. Оформи заказ: доставка, оплата картой или наличными, промокод.\n"
    "4. Картой — переведи сумму и пришли сюда скриншот чека, мы проверим и подтвердим.\n"
    "   Наличными — оплатишь при получении.\n"
    "5. Трек-номер и статус придут в этот чат.\n\n"
    "Команды: /start — меню, /catalog — каталог, /cart — корзина, /orders — мои заказы, "
    "/profile — профиль и баллы, /support — поддержка, /cancel — отменить ввод."
)

OPEN_SHOP = "Чтобы сделать заказ, открой магазин кнопкой ниже 👇"
NO_ORDERS = "У тебя пока нет заказов. Загляни в каталог 👇"
RECEIPT_NO_ORDER = (
    "Не нашёл заказов, которые ждут оплаты картой. Сначала оформи заказ, "
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


def totals_block(order, currency: str) -> str:
    subtotal = order.subtotal if order.subtotal is not None else order.total
    lines = [f"Товары: {money(subtotal, currency)}"]
    if order.discount:
        lines.append(f"Скидка{f' ({e(order.coupon_code)})' if order.coupon_code else ''}: −{money(order.discount, currency)}")
    lines.append(f"Доставка ({e(order.delivery)}): {money(order.delivery_price, currency) if order.delivery_price else 'бесплатно'}")
    lines.append(f"<b>Итого: {money(order.total, currency)}</b>")
    return "\n".join(lines)


def order_created(order, settings: dict) -> str:
    cur = settings["currency"]
    head = f"🧾 <b>Заказ #{order.id} оформлен!</b>\n\n{items_block(order.items, cur)}\n\n{totals_block(order, cur)}\n\n"
    if order.payment_method == "cash":
        return head + (
            "🤝 <b>Оплата наличными при получении.</b>\n"
            "Мы свяжемся с тобой, чтобы договориться о времени. Вещи уже отложены за тобой."
        )
    hours = settings.get("cancel_hours")
    return head + (
        f"💳 <b>Переведи {money(order.total, cur)} на карту:</b>\n<code>{e(order.card_details)}</code>\n\n"
        f"В комментарии к переводу можно указать: <code>Заказ #{order.id}</code>\n\n"
        "После оплаты <b>пришли сюда скриншот или PDF чека</b> — мы проверим поступление и подтвердим заказ."
        + (f"\n\n⏳ Вещи отложены на {hours} ч — если чека не будет, заказ снимется автоматически." if hours else "")
    )


def _customer(order) -> str:
    username = f"@{e(order.username)}, " if order.username else ""
    return f"{e(order.customer_name)} ({username}id <code>{order.user_id}</code>)"


def admin_new_order(order, currency: str, title: str | None = None) -> str:
    payment = "🤝 Наличные при получении" if order.payment_method == "cash" else f"💳 Карта · {e(order.card_label)}"
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
    lines += ["", items_block(order.items, currency), "", totals_block(order, currency), payment, "",
              f"Статус: {STATUS_LABELS.get(order.status, order.status)}"]
    if order.assignee_name:
        lines.append(f"👷 Ведёт: {e(order.assignee_name)}")
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
        f"Карта: {e(order.card_label)}\n"
        f"👤 {_customer(order)}\n\n"
        "Проверь поступление денег и нажми кнопку 👇"
    )


def admin_decision(order, admin_name: str, confirmed: bool) -> str:
    mark = "✅ Оплату подтвердил" if confirmed else "❌ Чек отклонил"
    return f"\n\n{mark}: {e(admin_name)}"


def status_update(order, currency: str) -> str | None:
    s, n = order.status, order.id
    if s == "paid":
        if order.payment_method == "cash":
            return f"✅ Оплата по заказу <b>#{n}</b> получена. Спасибо!"
        return f"✅ Оплата по заказу <b>#{n}</b> подтверждена! Собираем заказ и скоро отправим."
    if s == "shipped":
        text = f"🚚 Заказ <b>#{n}</b> в пути!"
        if order.payment_method == "cash" and not order.paid_at:
            text += f"\nПриготовь {money(order.total, currency)} наличными для курьера."
        if order.track:
            text += f"\nТрек-номер: <code>{e(order.track)}</code>"
        return text
    if s == "done":
        text = f"📦 Заказ <b>#{n}</b> получен. Спасибо, что выбрал DAYZ DROP! 🖤"
        if order.points_awarded:
            text += f"\n🎁 Начислили <b>{order.points_awarded}</b> баллов."
        return text + "\n\nОцени заказ — это займёт секунду 👇"
    if s == "cancelled":
        return f"✖️ Заказ <b>#{n}</b> отменён, вещи вернулись в продажу. Если это ошибка — напиши в поддержку."
    if s == "awaiting_payment":
        return (
            f"⚠️ Не нашли оплату по заказу <b>#{n}</b> по присланному чеку.\n"
            f"Проверь перевод на {money(order.total, currency)} и пришли чек ещё раз или напиши в поддержку."
        )
    return None


def payment_reminder(order, currency: str, hours_left: int | None) -> str:
    text = (f"⏰ Напоминаем: заказ <b>#{order.id}</b> ждёт оплаты — {money(order.total, currency)}.\n"
            f"Карта: <code>{e(order.card_details)}</code>\nПосле перевода пришли сюда скриншот чека.")
    if hours_left:
        text += f"\n\nВещи отложены ещё примерно на {hours_left} ч."
    return text


def auto_cancelled_admin(order) -> str:
    return f"⌛ Заказ #{order.id} ({e(order.customer_name)}) снят автоматически — оплата не пришла. Вещи вернулись на склад."


def low_stock(product, size: str, left: int) -> str:
    return f"⚠️ Заканчивается: <b>{e(product.title)}</b>, размер {e(size)} — осталось {left} шт."


def back_in_stock(product, size: str) -> str:
    what = f"размер {e(size)}" if size != "*" else "уже в продаже"
    return f"🔔 <b>{e(product.title)}</b> — {what}! Успей забрать, пока есть 👇"


def points_changed(delta: int, balance: int, reason: str, currency: str) -> str:
    sign = f"+{delta}" if delta > 0 else str(delta)
    return f"🎁 <b>{sign} баллов</b> — {e(reason)}\nБаланс: <b>{balance}</b> баллов"


def reward_coupon(coupon, cost: int, balance: int, currency: str) -> str:
    return (f"🎉 Обмен прошёл! «{e(coupon.title)}»\nТвой купон: <code>{coupon.code}</code>\n"
            f"Введи его при оформлении заказа.\n\nСписано {cost} баллов, осталось <b>{balance}</b>.")


# ---------- магазин на кнопках ----------

MENU = "<b>DAYZ DROP</b> 🖤\nВыбирай, что открыть:"
UNKNOWN = "Не понял 🙂 Выбери, что открыть:"
CANCELLED = "Ок, отменил."
CATALOG = "👕 <b>Каталог</b>\nВыбери категорию:"
CATALOG_EMPTY = "Каталог пока пуст — скоро здесь появятся вещи 🖤"
CART_EMPTY = "🛒 Корзина пуста. Загляни в каталог 👇"
NO_STOCK = "Этого размера больше нет в наличии"
SOON = "Скоро в продаже — нажми «Сообщить о поступлении», и бот напишет первым"

ASK_NAME = "✍️ <b>Оформление заказа</b>\n\nКак зовут получателя? Напиши имя и фамилию."
ASK_PHONE = "📱 Номер телефона для связи — нажми кнопку ниже или напиши в формате +998 90 123 45 67."
PHONE_SAVED = "Номер сохранён ✅"
ASK_DELIVERY = "🚚 Как доставить заказ?"
ASK_ADDRESS = "📍 Напиши город и адрес доставки (ориентир тоже пригодится)."
ASK_PAYMENT = "💳 Как будешь платить?"
ASK_COUPON = "🏷 Есть промокод или купон? Пришли его сообщением или нажми «Нет промокода»."
ASK_COMMENT = "💬 Комментарий к заказу? Если нет — нажми «Пропустить»."
CHECKOUT_CANCELLED = "Оформление отменено. Корзина сохранена 🛒"
ORDER_DONE = "✅ Заказ <b>#{id}</b> оформлен! Подробности — в следующем сообщении 👇"

SUPPORT_ASK = (
    "💬 <b>Поддержка</b>\n\n"
    "Напиши свой вопрос одним сообщением (можно с фото) — его получат админы, ответ придёт сюда."
)
SUPPORT_SENT = "✅ Сообщение отправлено админам. Ответ придёт в этот чат."
SUPPORT_ANSWER = "💬 <b>Ответ поддержки DAYZ DROP</b>\n<i>Чтобы ответить — ответь реплаем на это сообщение.</i>"
SUPPORT_DELIVERED = "✅ Ответ отправлен покупателю"

PROFILE_GUEST = (
    "👤 <b>Профиль</b>\n\nТы пока без регистрации — покупать можно и так.\n"
    "Зарегистрируйся — получишь <b>{welcome}</b> баллов сразу и <b>{percent}%</b> баллами с каждого заказа.\n"
    "Баллы меняются на скидки и вещи. Нужен только номер телефона 👇"
)
REGISTER_ASK = "📱 Нажми кнопку ниже, чтобы поделиться номером — это и есть регистрация."
REGISTER_DONE = "🎉 Готово, ты зарегистрирован! Баланс: <b>{points}</b> баллов."


def profile_text(user, coupons: list, currency: str) -> str:
    lines = [f"👤 <b>{e(user.full_name or user.first_name)}</b>", f"📞 {e(user.phone)}", "",
             f"🎁 Баланс: <b>{user.points or 0}</b> баллов"]
    active = [c for c in coupons if not (c.max_uses is not None and c.used_count >= c.max_uses)]
    if active:
        lines += ["", "🏷 <b>Твои купоны:</b>"] + [f"<code>{c.code}</code> — {e(c.title)}" for c in active]
    lines += ["", "Обменять баллы на скидку или вещь — кнопки ниже 👇"]
    return "\n".join(lines)


def support_header(user) -> str:
    username = f" (@{e(user.username)})" if user.username else ""
    return (
        f"💬 <b>Сообщение в поддержку</b>\n"
        f"👤 {e(user.full_name)}{username}, id <code>{user.id}</code>\n\n"
        "<i>Ответь реплаем на это или следующее сообщение — ответ уйдёт покупателю.</i>"
    )


def stock_total(product) -> int:
    return sum(s["stock"] for s in product.sizes)


BADGE_TEXT = {"new": "🆕 Новинка", "hit": "🔥 Хит", "soon": "⏳ Скоро"}


def product_card(product, currency: str) -> str:
    sizes = ", ".join(e(s["size"]) + ("" if s["stock"] else " (нет)") for s in product.sizes)
    price = money(product.price, currency)
    if product.old_price:
        price = f"<s>{money(product.old_price, currency)}</s> <b>{price}</b>"
    lines = [f"<b>{e(product.title)}</b>" + (f"  {BADGE_TEXT[product.badge]}" if product.badge in BADGE_TEXT else ""),
             f"💰 {price}"]
    if product.category:
        lines.append(f"🏷 {e(product.category)}")
    lines.append(f"📏 Размеры: {sizes}")
    if product.description:
        lines += ["", e(product.description[:500])]
    if product.size_chart:
        lines += ["", "<b>Замеры:</b>", e(product.size_chart[:300])]
    if product.badge == "soon":
        lines += ["", SOON]
    else:
        lines += ["", "Выбери размер, чтобы добавить в корзину 👇" if stock_total(product) else "Сейчас нет в наличии"]
    return "\n".join(lines)


def cart_text(lines: list, currency: str) -> str:
    total = sum(l["product"].price * l["qty"] for l in lines)
    rows = [
        f"• {e(l['product'].title)} — {e(l['size'])} × {l['qty']} = {money(l['product'].price * l['qty'], currency)}"
        for l in lines
    ]
    return "🛒 <b>Корзина</b>\n\n" + "\n".join(rows) + f"\n\n<b>Товары: {money(total, currency)}</b>"


def checkout_summary(data: dict, q: dict, currency: str) -> str:
    rows = [
        "🧾 <b>Проверь заказ</b>",
        "",
        "\n".join(f"• {e(l['product'].title)} — {e(l['size'])} × {l['qty']}" for l in q["lines"]),
        "",
        f"Товары: {money(q['subtotal'], currency)}",
    ]
    if q["discount"]:
        rows.append(f"Скидка ({e(q['coupon'].code)}): −{money(q['discount'], currency)}")
    rows.append(f"Доставка: {money(q['delivery_price'], currency) if q['delivery_price'] else 'бесплатно'}")
    rows += [
        f"<b>Итого: {money(q['total'], currency)}</b>",
        "",
        f"👤 {e(data['customer_name'])}",
        f"📞 {e(data['phone'])}",
        f"🚚 {e(q['delivery']['name'])}",
    ]
    if data.get("address"):
        rows.append(f"📍 {e(data['address'])}")
    rows.append("💳 Картой (перевод)" if q["payment"] == "card" else "🤝 Наличными при получении")
    if data.get("comment"):
        rows.append(f"💬 {e(data['comment'])}")
    if q["registered"] and q["earn_points"]:
        rows.append(f"🎁 За заказ начислим {q['earn_points']} баллов")
    rows += ["", "Всё верно?"]
    return "\n".join(rows)


# ---------- админка на кнопках ----------

def admin_menu(counts: dict) -> str:
    return (
        "⚙️ <b>Админ-панель DAYZ DROP</b>\n\n"
        f"🔎 Ждут проверки оплаты: <b>{counts.get('checking', 0)}</b>\n"
        f"⏳ Ждут оплату картой: <b>{counts.get('awaiting_payment', 0)}</b>\n"
        f"🤝 Наличные, ждут выдачи: <b>{counts.get('confirmed', 0)}</b>\n"
        f"📦 Оплачены, нужно отправить: <b>{counts.get('paid', 0)}</b>\n"
        f"🚚 В пути: <b>{counts.get('shipped', 0)}</b>\n\n"
        "<i>Касса, клиенты, купоны, баллы и настройки — в мини-аппе → «Управление».</i>"
    )


def admin_product_card(product, currency: str) -> str:
    sizes = "\n".join(f"   {e(s['size'])}: {s['stock']} шт" for s in product.sizes) or "   —"
    price = money(product.price, currency) + (f" (было {money(product.old_price, currency)})" if product.old_price else "")
    return (
        f"<b>{e(product.title)}</b>" + (f"  {BADGE_TEXT[product.badge]}" if product.badge in BADGE_TEXT else "") + "\n"
        f"💰 {price}\n"
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
    "price": "💰 Цена в сумах (только число):",
    "description": "📝 Описание (материал, посадка, уход):",
    "sizes": "📦 " + SIZES_HINT,
    "photos": "🖼 Пришли фото товара (можно несколько, первое — обложка). Потом нажми «Готово».",
}
ASK_SETTING = {
    "currency": "💱 Валюта (например сум):",
}
ASK_TRACK = "🚚 Пришли трек-номер отправления (или нажми «Без трека»):"
BAD_PRICE = "Цена должна быть целым числом, например 349000"
BAD_SIZES = "Не понял размеры. " + SIZES_HINT
SAVED = "✅ Сохранено"

RECEIPT_PICK = "📥 <b>Приход товара</b>\nНа какой товар оформляем поступление?"
RECEIPT_ASK_COST = "💵 Цена закупки за 1 шт (чтобы считать прибыль) — или нажми «Пропустить»:"
BROADCAST_ASK = ("📣 <b>Рассылка</b>\n\nПришли сообщение, которое получат все пользователи бота: текст или фото с подписью.\n"
                 "Перед отправкой покажу предпросмотр.")


def receipt_ask_items(product) -> str:
    current = ", ".join(f"{e(s['size'])}: {s['stock']}" for s in product.sizes) or "—"
    return (
        f"📥 <b>Приход: {e(product.title)}</b>\n"
        f"Сейчас на складе: {current}\n\n"
        "Сколько штук пришло? Пришли по размерам, например:\n<code>M 5, L 3, XL 2</code>\n"
        "Новый размер тоже можно — он добавится."
    )


def receipt_done(product, items: list, cost: int | None, currency: str) -> str:
    added = ", ".join(f"{e(i['size'])} +{i['qty']}" for i in items if i["qty"] > 0)
    units = sum(i["qty"] for i in items if i["qty"] > 0)
    now = ", ".join(f"{e(s['size'])}: {s['stock']}" for s in product.sizes)
    text = f"✅ <b>Оприходовано: {e(product.title)}</b>\nПришло: {added} ({units} шт)\nТеперь на складе: {now}"
    if cost is not None:
        text += f"\nЗакупка: {money(cost, currency)} × {units} = <b>{money(cost * units, currency)}</b>"
    return text


def movements(rows: list) -> str:
    if not rows:
        return "📜 <b>Движения склада</b>\n\nПока пусто."
    lines = ["📜 <b>Движения склада</b> (последние 20)", ""]
    for m in rows:
        date = m.created_at.strftime("%d.%m %H:%M") if m.created_at else ""
        sign = f"+{m.delta}" if m.delta > 0 else str(m.delta)
        note = f" — {e(m.note)}" if m.note else ""
        lines.append(f"{date} {KIND_LABELS.get(m.kind, m.kind)} {e(m.product_title)} {e(m.size)} <b>{sign}</b>{note}")
    return "\n".join(lines)


def admin_settings(settings: dict) -> str:
    cards = "\n".join(f"   {'✅' if c.get('active', True) else '⏸'} {e(c['label'])}" for c in settings["cards"]) or "   — не добавлены"
    delivery = "\n".join(
        f"   {e(m['name'])}: {money(m['price'], settings['currency']) if m['price'] else 'бесплатно'}"
        + (" · наличные" if m["cash"] else " · только карта")
        for m in settings["delivery_methods"]
    )
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"💳 <b>Карты для переводов:</b>\n{cards}\n\n"
        f"🚚 <b>Доставка:</b>\n{delivery}\n\n"
        f"💱 Валюта: {e(settings['currency'])}\n"
        f"⏰ Напоминание об оплате: через {settings['remind_hours']} ч, автоотмена: через {settings['cancel_hours']} ч\n"
        f"🎁 Баллы: {settings['earn_percent']}% с заказа, {settings['welcome_points']} за регистрацию"
        + ("" if settings["loyalty_enabled"] else " (выключены)")
        + "\n\n<i>Карты, доставку и баллы меняй в мини-аппе → «Управление» → «Настройки».</i>"
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
