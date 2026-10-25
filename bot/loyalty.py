"""Регистрация, баллы, купоны и награды за баллы."""
import re
import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import keyboards
import services
import texts
from db import Coupon, Order, PointsTx, Product, Reward, User, aware, now
from services import ShopError, to_int

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без похожих O/0 и I/1
CODE_LENGTH = 6
KINDS = {"percent", "amount", "gift"}


def normalize_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(code or "").upper())


async def unique_code(session: AsyncSession) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if not (await session.execute(select(Coupon.id).where(Coupon.code == code))).first():
            return code


def normalize_phone(raw: str) -> str | None:
    """Узбекские номера: 9 цифр после +998. Принимаем «90 123 45 67», «+998901234567» и т.п."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("998") and len(digits) == 12:
        digits = digits[3:]
    if len(digits) != 9:
        return None
    return f"+998 {digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:]}"


# ---------- купоны ----------

def discount_text(kind: str, value: int, product: Product | None, currency: str) -> str:
    if kind == "percent":
        return f"−{value}%"
    if kind == "amount":
        return f"−{texts.money(value, currency)}"
    return f"{product.title if product else 'Вещь'} в подарок"


async def check_coupon(session: AsyncSession, code: str, user_id: int, lines: list, subtotal: int):
    """Проверяет купон для корзины и возвращает (купон, сумма скидки)."""
    code = normalize_code(code)
    coupon = (await session.execute(select(Coupon).where(Coupon.code == code))).scalar_one_or_none()
    if not coupon or not coupon.is_active:
        raise ShopError("Такого промокода нет")
    if coupon.expires_at and aware(coupon.expires_at) < now():
        raise ShopError("Срок действия промокода закончился")
    if coupon.user_id and coupon.user_id != user_id:
        raise ShopError("Этот купон принадлежит другому покупателю")
    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
        raise ShopError("Промокод уже использован" if coupon.max_uses == 1 else "Лимит использований промокода исчерпан")
    if coupon.once_per_user:
        used = (await session.execute(
            select(func.count()).select_from(Order).where(
                Order.user_id == user_id, Order.coupon_code == coupon.code, Order.status != "cancelled"
            )
        )).scalar_one()
        if used:
            raise ShopError("Ты уже использовал этот промокод")
    if subtotal < coupon.min_total:
        settings = await services.get_settings(session)
        raise ShopError(f"Промокод действует от {texts.money(coupon.min_total, settings['currency'])}")

    if coupon.kind == "percent":
        discount = subtotal * min(coupon.value, 100) // 100
    elif coupon.kind == "amount":
        discount = min(coupon.value, subtotal)
    else:  # gift — одна единица выбранной вещи бесплатно
        prices = [l["product"].price for l in lines if l["product"].id == coupon.product_id]
        if not prices:
            product = await session.get(Product, coupon.product_id) if coupon.product_id else None
            raise ShopError(f"Добавь в корзину «{product.title if product else 'подарочную вещь'}», чтобы получить её в подарок")
        discount = min(prices)
    return coupon, discount


def coupon_json(c: Coupon, products: dict[int, Product], currency: str) -> dict:
    product = products.get(c.product_id) if c.product_id else None
    return {
        "id": c.id,
        "code": c.code,
        "title": c.title,
        "kind": c.kind,
        "value": c.value,
        "product_id": c.product_id,
        "product_title": product.title if product else None,
        "label": discount_text(c.kind, c.value, product, currency),
        "min_total": c.min_total,
        "max_uses": c.max_uses,
        "used_count": c.used_count,
        "once_per_user": c.once_per_user,
        "user_id": c.user_id,
        "expires_at": aware(c.expires_at).isoformat() if c.expires_at else None,
        "is_active": c.is_active,
        "source": c.source,
        "spent": c.max_uses is not None and c.used_count >= c.max_uses,
    }


def clean_coupon(data: dict) -> dict:
    kind = data.get("kind")
    if kind not in KINDS:
        raise ShopError("Выбери тип скидки")
    value = to_int(data.get("value"))
    if kind == "percent" and not 1 <= value <= 100:
        raise ShopError("Процент скидки — от 1 до 100")
    if kind == "amount" and value <= 0:
        raise ShopError("Укажи сумму скидки")
    product_id = to_int(data.get("product_id")) or None
    if kind == "gift" and not product_id:
        raise ShopError("Выбери вещь, которая будет в подарок")
    expires = None
    if data.get("expires_at"):
        try:
            expires = datetime.fromisoformat(str(data["expires_at"])[:10] + "T23:59:59+05:00")
        except ValueError:
            raise ShopError("Неверная дата окончания")
    max_uses = data.get("max_uses")
    return {
        "title": str(data.get("title") or "").strip()[:200],
        "kind": kind,
        "value": value if kind != "gift" else 0,
        "product_id": product_id if kind == "gift" else None,
        "min_total": to_int(data.get("min_total")),
        "max_uses": to_int(max_uses) or None if max_uses not in (None, "") else None,
        "once_per_user": bool(data.get("once_per_user", True)),
        "expires_at": expires,
        "is_active": bool(data.get("is_active", True)),
    }


# ---------- регистрация и баллы ----------

async def register_user(session: AsyncSession, tg_user, name: str, phone: str) -> User:
    name = str(name or "").strip()[:200]
    normalized = normalize_phone(phone)
    if len(name) < 2:
        raise ShopError("Напиши имя")
    if not normalized:
        raise ShopError("Номер телефона в формате +998 90 123 45 67")
    user = await services.upsert_user(session, tg_user)
    first_time = user.registered_at is None
    user.full_name, user.phone = name, normalized
    if first_time:
        user.registered_at = now()
    await session.commit()
    settings = await services.get_settings(session)
    if first_time and settings["loyalty_enabled"] and settings["welcome_points"] > 0:
        await add_points(session, user, settings["welcome_points"], "Бонус за регистрацию")
    return user


async def add_points(session: AsyncSession, user: User, delta: int, reason: str, *, order_id: int | None = None,
                     admin_name: str | None = None, notify: bool = True) -> None:
    if not delta:
        return
    balance = (user.points or 0) + delta
    if balance < 0:
        raise ShopError("Недостаточно баллов")
    user.points = balance
    session.add(PointsTx(user_id=user.id, delta=delta, reason=reason[:300], order_id=order_id, admin_name=admin_name))
    await session.commit()
    if notify:
        settings = await services.get_settings(session)
        await services.safe_send(user.id, texts.points_changed(delta, balance, reason, settings["currency"]),
                                 reply_markup=keyboards.profile_kb())


async def award_order_points(session: AsyncSession, order: Order, settings: dict) -> None:
    """Баллы за полученный заказ — только зарегистрированным."""
    if not settings["loyalty_enabled"] or order.points_awarded:
        return
    user = await session.get(User, order.user_id)
    if not user or not user.registered_at:
        return
    base = (order.subtotal if order.subtotal is not None else order.total - (order.delivery_price or 0)) - (order.discount or 0)
    points = max(0, base) * settings["earn_percent"] // 100
    if points <= 0:
        return
    order.points_awarded = points
    await add_points(session, user, points, f"Заказ #{order.id}", order_id=order.id)


async def exchange_reward(session: AsyncSession, user: User, reward: Reward) -> Coupon:
    """Списывает баллы и выдаёт личный одноразовый купон."""
    if not user.registered_at:
        raise ShopError("Сначала зарегистрируйся — баллы копятся только в профиле")
    if not reward.is_active:
        raise ShopError("Эта награда больше недоступна")
    if (user.points or 0) < reward.cost:
        raise ShopError(f"Не хватает {reward.cost - (user.points or 0)} баллов")
    coupon = Coupon(
        code=await unique_code(session),
        title=reward.title,
        kind=reward.kind,
        value=reward.value,
        product_id=reward.product_id,
        min_total=0,
        max_uses=1,
        used_count=0,
        once_per_user=True,
        user_id=user.id,
        source="reward",
        is_active=True,
    )
    session.add(coupon)
    await add_points(session, user, -reward.cost, f"Обмен: {reward.title}", notify=False)
    settings = await services.get_settings(session)
    await services.safe_send(user.id, texts.reward_coupon(coupon, reward.cost, user.points, settings["currency"]),
                             reply_markup=keyboards.profile_kb())
    return coupon


def clean_reward(data: dict) -> dict:
    kind = data.get("kind")
    if kind not in KINDS:
        raise ShopError("Выбери тип награды")
    title = str(data.get("title") or "").strip()[:200]
    if not title:
        raise ShopError("Напиши название награды")
    cost = to_int(data.get("cost"))
    if cost <= 0:
        raise ShopError("Укажи цену в баллах")
    values = clean_coupon({**data, "title": title})
    return {"title": title, "kind": kind, "value": values["value"], "product_id": values["product_id"],
            "cost": cost, "is_active": bool(data.get("is_active", True)), "sort": to_int(data.get("sort"))}


def reward_json(r: Reward, products: dict[int, Product], currency: str) -> dict:
    product = products.get(r.product_id) if r.product_id else None
    return {
        "id": r.id, "title": r.title, "kind": r.kind, "value": r.value, "product_id": r.product_id,
        "product_title": product.title if product else None,
        "product_photo": product.photos[0] if product and product.photos else None,
        "label": discount_text(r.kind, r.value, product, currency),
        "cost": r.cost, "is_active": r.is_active, "sort": r.sort,
    }
