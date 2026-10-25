"""HTTP API мини-аппа для покупателя. Каждый запрос подписан Telegram (initData) — подделать пользователя нельзя."""
import json
import logging
import mimetypes
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from aiohttp import web
from aiogram.utils.web_app import safe_parse_webapp_init_data
from sqlalchemy import delete, func, select

import finance
import loyalty
import services
from config import ADMIN_IDS, BOT_TOKEN
from db import Coupon, Favorite, Order, Product, Reward, Session, Subscription, User, aware
from loader import bot

log = logging.getLogger(__name__)
routes = web.RouteTableDef()

INIT_DATA_TTL = timedelta(days=1)
PHOTO_KINDS = {"image/jpeg", "image/png"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


# ---------- общее ----------

@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        response = web.Response()
    else:
        try:
            response = await handler(request)
        except ApiError as exc:
            response = web.json_response({"error": str(exc)}, status=exc.status)
        except services.ShopError as exc:
            response = web.json_response({"error": str(exc)}, status=400)
        except web.HTTPException as exc:
            response = web.json_response({"error": exc.reason}, status=exc.status)
        except Exception:
            log.exception("API error")
            response = web.json_response({"error": "Ошибка сервера, попробуй ещё раз"}, status=500)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Init-Data"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    # Нужен, когда мини-апп с GitHub Pages обращается к серверу на localhost (локальный тест)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


def current_user(request: web.Request):
    try:
        data = safe_parse_webapp_init_data(BOT_TOKEN, request.headers.get("X-Init-Data", ""))
    except ValueError:
        raise ApiError(401, "Открой магазин через бота в Telegram")
    auth_date = data.auth_date if data.auth_date.tzinfo else data.auth_date.replace(tzinfo=timezone.utc)
    if not data.user or datetime.now(timezone.utc) - auth_date > INIT_DATA_TTL:
        raise ApiError(401, "Сессия устарела — закрой и заново открой магазин")
    return data.user


def admin_user(request: web.Request):
    user = current_user(request)
    if user.id not in ADMIN_IDS:
        raise ApiError(403, "Только для админов")
    return user


async def read_json(request: web.Request) -> dict:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise ApiError(400, "Некорректный запрос")
    if not isinstance(data, dict):
        raise ApiError(400, "Некорректный запрос")
    return data


async def read_upload(request: web.Request):
    form = await request.post()
    file = form.get("file")
    if not isinstance(file, web.FileField):
        raise ApiError(400, "Файл не получен")
    content = file.file.read()
    if not content:
        raise ApiError(400, "Пустой файл")
    return content, file.filename or "file", (file.content_type or "").lower()


def iso(dt) -> str | None:
    return aware(dt).isoformat() if dt else None


def product_json(p: Product, ratings: dict | None = None, likes: dict | None = None) -> dict:
    rating = (ratings or {}).get(p.id)
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "category": p.category,
        "price": p.price,
        "old_price": p.old_price,
        "sizes": p.sizes,
        "photos": p.photos,
        "size_chart": p.size_chart,
        "badge": p.badge,
        "is_active": p.is_active,
        "sort": p.sort,
        "rating": round(rating[0] / rating[1], 1) if rating else None,
        "rating_count": rating[1] if rating else 0,
        "likes": (likes or {}).get(p.id, 0),
        "created_at": iso(p.created_at),
    }


def order_json(o: Order, admin: bool = False) -> dict:
    data = {
        "id": o.id,
        "items": o.items,
        "subtotal": o.subtotal if o.subtotal is not None else o.total,
        "discount": o.discount or 0,
        "coupon_code": o.coupon_code,
        "delivery_price": o.delivery_price or 0,
        "total": o.total,
        "status": o.status,
        "track": o.track,
        "customer_name": o.customer_name,
        "phone": o.phone,
        "delivery": o.delivery,
        "address": o.address,
        "comment": o.comment,
        "payment_method": o.payment_method or "card",
        "card_label": o.card_label,
        "card_details": o.card_details if o.status in ("awaiting_payment", "checking") else None,
        "has_receipt": bool(o.receipt_file_id),
        "points_awarded": o.points_awarded or 0,
        "rating": o.rating,
        "rating_comment": o.rating_comment,
        "created_at": iso(o.created_at),
        "paid_at": iso(o.paid_at),
    }
    if admin:
        cogs, unknown = finance.order_cogs(o)
        data.update(
            user_id=o.user_id,
            username=o.username,
            receipt_file_id=o.receipt_file_id,
            receipt_kind=o.receipt_kind,
            paid_via=o.paid_via,
            assignee_id=o.assignee_id,
            assignee_name=o.assignee_name,
            history=o.history or [],
            cogs=cogs,
            cogs_unknown=unknown,
            card_details=o.card_details,
        )
    return data


def user_json(u: User | None) -> dict:
    if not u:
        return {"registered": False, "points": 0}
    return {
        "id": u.id,
        "username": u.username,
        "first_name": u.first_name,
        "full_name": u.full_name,
        "phone": u.phone,
        "registered": bool(u.registered_at),
        "registered_at": iso(u.registered_at),
        "points": u.points or 0,
    }


def public_settings(settings: dict) -> dict:
    return {
        "currency": settings["currency"],
        "about": settings["about"],
        "delivery_methods": services.delivery_methods(settings),
        "card_payments": bool(services.active_cards(settings)),
        "loyalty_enabled": settings["loyalty_enabled"],
        "earn_percent": settings["earn_percent"],
        "welcome_points": settings["welcome_points"],
        "cancel_hours": settings["cancel_hours"],
    }


async def product_stats(session) -> tuple[dict, dict]:
    """Средние оценки (из полученных заказов) и число «сердечек» по товарам."""
    ratings: dict[int, list[int]] = {}
    rated = (await session.execute(select(Order).where(Order.rating.is_not(None)))).scalars()
    for o in rated:
        for pid in {i["product_id"] for i in o.items}:
            acc = ratings.setdefault(pid, [0, 0])
            acc[0] += o.rating
            acc[1] += 1
    likes = dict((await session.execute(select(Favorite.product_id, func.count()).group_by(Favorite.product_id))).all())
    return ratings, likes


@routes.get("/health")
async def health(request: web.Request):
    return web.Response(text="ok")


# ---------- фото из Telegram ----------

_photo_cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()


@routes.get("/api/photo/{file_id}")
async def photo(request: web.Request):
    """Отдаёт фото товара по file_id из Telegram, не раскрывая токен бота."""
    file_id = request.match_info["file_id"]
    if file_id in _photo_cache:
        _photo_cache.move_to_end(file_id)
        body, content_type = _photo_cache[file_id]
    else:
        try:
            tg_file = await bot.get_file(file_id)
            body = (await bot.download_file(tg_file.file_path)).read()
        except Exception:
            raise ApiError(404, "Фото не найдено")
        content_type = mimetypes.guess_type(tg_file.file_path)[0] or "application/octet-stream"
        _photo_cache[file_id] = (body, content_type)
        while len(_photo_cache) > 150:
            _photo_cache.popitem(last=False)
    return web.Response(body=body, content_type=content_type, headers={"Cache-Control": "public, max-age=2592000"})


# ---------- старт и каталог ----------

@routes.get("/api/bootstrap")
async def bootstrap(request: web.Request):
    tg_user = current_user(request)
    async with Session() as session:
        user = await services.upsert_user(session, tg_user)
        settings = await services.get_settings(session)
        favorites = [r[0] for r in (await session.execute(
            select(Favorite.product_id).where(Favorite.user_id == tg_user.id))).all()]
        subs = [{"product_id": s.product_id, "size": s.size} for s in (await session.execute(
            select(Subscription).where(Subscription.user_id == tg_user.id))).scalars()]
    return web.json_response({
        "user": user_json(user),
        "is_admin": tg_user.id in ADMIN_IDS,
        "bot_username": (await bot.me()).username,
        "settings": public_settings(settings),
        "favorites": favorites,
        "subscriptions": subs,
    })


@routes.get("/api/products")
async def products(request: web.Request):
    async with Session() as session:
        rows = await services.active_products(session)
        ratings, likes = await product_stats(session)
    return web.json_response([product_json(p, ratings, likes) for p in rows])


@routes.post("/api/favorites/{product_id}")
async def toggle_favorite(request: web.Request):
    user = current_user(request)
    product_id = int(request.match_info["product_id"])
    async with Session() as session:
        await services.upsert_user(session, user)
        fav = await session.get(Favorite, (user.id, product_id))
        if fav:
            await session.delete(fav)
        else:
            session.add(Favorite(user_id=user.id, product_id=product_id))
        await session.commit()
        count = (await session.execute(
            select(func.count()).select_from(Favorite).where(Favorite.product_id == product_id))).scalar_one()
    return web.json_response({"favorite": not fav, "likes": count})


@routes.post("/api/subscribe")
async def subscribe(request: web.Request):
    """«Сообщить о поступлении»: on=true — подписаться, false — отписаться."""
    user = current_user(request)
    data = await read_json(request)
    product_id, size = int(data.get("product_id") or 0), str(data.get("size") or "*")[:20]
    async with Session() as session:
        await services.upsert_user(session, user)
        await session.execute(delete(Subscription).where(
            Subscription.user_id == user.id, Subscription.product_id == product_id, Subscription.size == size))
        if data.get("on", True):
            session.add(Subscription(user_id=user.id, product_id=product_id, size=size))
        await session.commit()
    return web.json_response({"subscribed": bool(data.get("on", True))})


# ---------- заказ ----------

@routes.post("/api/quote")
async def quote(request: web.Request):
    """Предпросмотр итога: доставка, купон, способы оплаты — пересчитывается при каждом изменении."""
    user = current_user(request)
    data = await read_json(request)
    async with Session() as session:
        q = await services.quote(session, user.id, data)
    return web.json_response(services.quote_json(q))


@routes.post("/api/orders")
async def create_order(request: web.Request):
    user = current_user(request)
    data = await read_json(request)
    async with Session() as session:
        await services.upsert_user(session, user)
        order = await services.create_order(session, user, data)
    return web.json_response(order_json(order))


@routes.get("/api/orders/my")
async def my_orders(request: web.Request):
    user = current_user(request)
    async with Session() as session:
        rows = (await session.execute(
            select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(50)
        )).scalars().all()
    return web.json_response([order_json(o) for o in rows])


async def _own_order(session, user, order_id: str) -> Order:
    order = await session.get(Order, int(order_id))
    if not order or order.user_id != user.id:
        raise ApiError(404, "Заказ не найден")
    return order


@routes.post("/api/orders/{id}/receipt")
async def upload_receipt(request: web.Request):
    user = current_user(request)
    content, filename, content_type = await read_upload(request)
    kind = "photo" if content_type in PHOTO_KINDS else "document"
    async with Session() as session:
        order = await _own_order(session, user, request.match_info["id"])
        await services.attach_receipt(session, order, content=content, filename=filename, kind=kind)
    return web.json_response(order_json(order))


@routes.post("/api/orders/{id}/cancel")
async def cancel_order(request: web.Request):
    user = current_user(request)
    async with Session() as session:
        order = await _own_order(session, user, request.match_info["id"])
        if order.status not in ("awaiting_payment", "confirmed"):
            raise ApiError(400, "Этот заказ уже нельзя отменить — напиши в поддержку")
        await services.change_status(session, order, "cancelled", actor="Покупатель")
        await services.notify_admins(f"✖️ Покупатель отменил заказ #{order.id}")
    return web.json_response(order_json(order))


@routes.post("/api/orders/{id}/rate")
async def rate_order(request: web.Request):
    user = current_user(request)
    data = await read_json(request)
    rating = services.to_int(data.get("rating"))
    if not 1 <= rating <= 5:
        raise ApiError(400, "Оценка от 1 до 5")
    async with Session() as session:
        order = await _own_order(session, user, request.match_info["id"])
        if order.status != "done":
            raise ApiError(400, "Оценить можно после получения заказа")
        order.rating = rating
        order.rating_comment = str(data.get("comment") or "").strip()[:1000] or None
        await session.commit()
    stars = "★" * rating + "☆" * (5 - rating)
    comment = f"\n💬 {order.rating_comment}" if order.rating_comment else ""
    await services.notify_admins(f"⭐ Оценка заказа #{order.id}: {stars}{comment}")
    return web.json_response(order_json(order))


# ---------- профиль, баллы, награды ----------

@routes.get("/api/profile")
async def profile(request: web.Request):
    tg_user = current_user(request)
    async with Session() as session:
        user = await services.upsert_user(session, tg_user)
        settings = await services.get_settings(session)
        products_map = {p.id: p for p in (await session.execute(select(Product))).scalars()}
        coupons = (await session.execute(
            select(Coupon).where(Coupon.user_id == tg_user.id).order_by(Coupon.id.desc()))).scalars()
        rewards = (await session.execute(
            select(Reward).where(Reward.is_active.is_(True)).order_by(Reward.sort, Reward.cost))).scalars()
        history = await finance.points_history(session, tg_user.id)
        orders_count = (await session.execute(
            select(func.count()).select_from(Order).where(Order.user_id == tg_user.id))).scalar_one()
    cur = settings["currency"]
    return web.json_response({
        "user": user_json(user),
        "coupons": [loyalty.coupon_json(c, products_map, cur) for c in coupons],
        "rewards": [loyalty.reward_json(r, products_map, cur) for r in rewards],
        "history": history,
        "orders_count": orders_count,
    })


@routes.post("/api/profile/register")
async def register(request: web.Request):
    tg_user = current_user(request)
    data = await read_json(request)
    async with Session() as session:
        user = await loyalty.register_user(session, tg_user, data.get("name"), data.get("phone"))
    return web.json_response(user_json(user))


@routes.post("/api/rewards/{id}/exchange")
async def exchange(request: web.Request):
    tg_user = current_user(request)
    async with Session() as session:
        user = await session.get(User, tg_user.id)
        reward = await session.get(Reward, int(request.match_info["id"]))
        if not user or not reward:
            raise ApiError(404, "Награда не найдена")
        coupon = await loyalty.exchange_reward(session, user, reward)
        settings = await services.get_settings(session)
        products_map = {p.id: p for p in (await session.execute(select(Product))).scalars()}
    return web.json_response({"coupon": loyalty.coupon_json(coupon, products_map, settings["currency"]),
                              "points": user.points})
