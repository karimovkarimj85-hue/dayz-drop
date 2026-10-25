"""HTTP API для мини-аппа. Каждый запрос подписан Telegram (initData) — подделать пользователя нельзя."""
import json
import logging
import mimetypes
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from aiohttp import web
from aiogram.types import BufferedInputFile
from aiogram.utils.web_app import safe_parse_webapp_init_data
from sqlalchemy import func, select

import services
from config import ADMIN_IDS, BOT_TOKEN
from db import Order, Product, Session, StockMovement, User
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


def product_json(p: Product) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "category": p.category,
        "price": p.price,
        "sizes": p.sizes,
        "photos": p.photos,
        "is_active": p.is_active,
        "sort": p.sort,
    }


def order_json(o: Order, admin: bool = False) -> dict:
    data = {
        "id": o.id,
        "items": o.items,
        "total": o.total,
        "status": o.status,
        "track": o.track,
        "customer_name": o.customer_name,
        "phone": o.phone,
        "delivery": o.delivery,
        "address": o.address,
        "comment": o.comment,
        "has_receipt": bool(o.receipt_file_id),
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
    if admin:
        data.update(
            user_id=o.user_id,
            username=o.username,
            receipt_file_id=o.receipt_file_id,
            receipt_kind=o.receipt_kind,
        )
    return data


def public_settings(settings: dict) -> dict:
    return {
        "currency": settings["currency"],
        "delivery_options": services.delivery_options(settings),
        "support_contact": settings["support_contact"],
        "payment_details": settings["payment_details"],
        "about": settings["about"],
    }


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


# ---------- покупатель ----------

@routes.get("/api/bootstrap")
async def bootstrap(request: web.Request):
    user = current_user(request)
    async with Session() as session:
        await services.upsert_user(session, user)
        settings = await services.get_settings(session)
    return web.json_response(
        {
            "user": {"id": user.id, "first_name": user.first_name},
            "is_admin": user.id in ADMIN_IDS,
            "bot_username": (await bot.me()).username,
            "settings": public_settings(settings),
        }
    )


@routes.get("/api/products")
async def products(request: web.Request):
    async with Session() as session:
        rows = (
            await session.execute(
                select(Product).where(Product.is_active.is_(True)).order_by(Product.sort, Product.id.desc())
            )
        ).scalars().all()
    return web.json_response([product_json(p) for p in rows])


@routes.post("/api/orders")
async def create_order(request: web.Request):
    user = current_user(request)
    data = await read_json(request)
    async with Session() as session:
        order = await services.create_order(session, user, data)
    return web.json_response(order_json(order))


@routes.get("/api/orders/my")
async def my_orders(request: web.Request):
    user = current_user(request)
    async with Session() as session:
        rows = (
            await session.execute(
                select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(50)
            )
        ).scalars().all()
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
        if order.status != "awaiting_payment":
            raise ApiError(400, "Этот заказ уже нельзя отменить — напиши в поддержку")
        await services.change_status(session, order, "cancelled")
    return web.json_response(order_json(order))


# ---------- админка ----------

def _clean_product(data: dict) -> dict:
    title = str(data.get("title") or "").strip()[:200]
    if not title:
        raise ApiError(400, "Нужно название товара")
    try:
        price = int(data.get("price"))
        sort = int(data.get("sort") or 0)
    except (TypeError, ValueError):
        raise ApiError(400, "Цена должна быть числом")
    if price < 0:
        raise ApiError(400, "Цена не может быть отрицательной")

    sizes = services.clean_sizes(data.get("sizes"))
    if not sizes:
        raise ApiError(400, "Добавь хотя бы один размер")

    photos = [str(p) for p in (data.get("photos") or []) if p][:10]
    return {
        "title": title,
        "description": str(data.get("description") or "").strip()[:3000],
        "category": str(data.get("category") or "").strip()[:100],
        "price": price,
        "sizes": sizes,
        "photos": photos,
        "is_active": bool(data.get("is_active", True)),
        "sort": sort,
    }


@routes.get("/api/admin/products")
async def admin_products(request: web.Request):
    admin_user(request)
    async with Session() as session:
        rows = (await session.execute(select(Product).order_by(Product.sort, Product.id.desc()))).scalars().all()
    return web.json_response([product_json(p) for p in rows])


@routes.post("/api/admin/products")
async def admin_create_product(request: web.Request):
    user = admin_user(request)
    values = _clean_product(await read_json(request))
    async with Session() as session:
        product = await services.create_product(session, values, user.id)
    return web.json_response(product_json(product))


@routes.put("/api/admin/products/{id}")
async def admin_update_product(request: web.Request):
    user = admin_user(request)
    values = _clean_product(await read_json(request))
    async with Session() as session:
        product = await session.get(Product, int(request.match_info["id"]))
        if not product:
            raise ApiError(404, "Товар не найден")
        services.apply_sizes(session, product, values.pop("sizes"), user.id)
        for key, value in values.items():
            setattr(product, key, value)
        await session.commit()
    return web.json_response(product_json(product))


# ---------- склад ----------

KIND_LABELS = {"receipt": "Приход", "sale": "Продажа", "return": "Возврат", "adjust": "Корректировка"}


@routes.get("/api/admin/stock")
async def admin_stock(request: web.Request):
    admin_user(request)
    product_id = request.query.get("product_id")
    query = select(StockMovement).order_by(StockMovement.id.desc()).limit(100)
    if product_id:
        query = query.where(StockMovement.product_id == int(product_id))
    async with Session() as session:
        products = (await session.execute(select(Product).order_by(Product.sort, Product.id.desc()))).scalars().all()
        movements = (await session.execute(query)).scalars().all()
        received = (
            await session.execute(
                select(func.coalesce(func.sum(StockMovement.delta * StockMovement.cost), 0)).where(
                    StockMovement.kind == "receipt", StockMovement.cost.is_not(None)
                )
            )
        ).scalar_one()
    return web.json_response(
        {
            "products": [product_json(p) for p in products],
            "units": sum(s["stock"] for p in products for s in p.sizes),
            "received_value": int(received),
            "movements": [
                {
                    "id": m.id,
                    "product_id": m.product_id,
                    "product_title": m.product_title,
                    "size": m.size,
                    "delta": m.delta,
                    "kind": m.kind,
                    "kind_label": KIND_LABELS.get(m.kind, m.kind),
                    "cost": m.cost,
                    "note": m.note,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in movements
            ],
        }
    )


@routes.post("/api/admin/stock/receipt")
async def admin_stock_receipt(request: web.Request):
    user = admin_user(request)
    data = await read_json(request)
    cost = data.get("cost")
    try:
        cost = int(cost) if cost not in (None, "") else None
    except (TypeError, ValueError):
        raise ApiError(400, "Цена закупки должна быть числом")
    async with Session() as session:
        product = await session.get(Product, int(data.get("product_id") or 0))
        if not product:
            raise ApiError(404, "Товар не найден")
        await services.receive_stock(
            session, product, data.get("items") or [], cost=cost,
            note=str(data.get("note") or "Приход товара").strip(), admin_id=user.id,
        )
    return web.json_response(product_json(product))


@routes.delete("/api/admin/products/{id}")
async def admin_delete_product(request: web.Request):
    admin_user(request)
    async with Session() as session:
        product = await session.get(Product, int(request.match_info["id"]))
        if product:
            await session.delete(product)
            await session.commit()
    return web.json_response({"ok": True})


@routes.post("/api/admin/upload")
async def admin_upload(request: web.Request):
    """Загружает фото товара в Telegram (себе в чат и сразу удаляет) и возвращает file_id."""
    user = admin_user(request)
    content, filename, content_type = await read_upload(request)
    if content_type not in PHOTO_KINDS:
        raise ApiError(400, "Нужна картинка JPG или PNG")
    try:
        msg = await bot.send_photo(user.id, BufferedInputFile(content, filename=filename), disable_notification=True)
    except Exception as exc:
        log.warning("upload failed: %s", exc)
        raise ApiError(400, "Не удалось загрузить фото. Напиши боту /start и попробуй снова")
    try:
        await bot.delete_message(user.id, msg.message_id)
    except Exception:
        pass
    return web.json_response({"file_id": msg.photo[-1].file_id})


@routes.get("/api/admin/orders")
async def admin_orders(request: web.Request):
    admin_user(request)
    status = request.query.get("status")
    query = select(Order).order_by(Order.id.desc()).limit(200)
    if status:
        query = query.where(Order.status == status)
    async with Session() as session:
        rows = (await session.execute(query)).scalars().all()
    return web.json_response([order_json(o, admin=True) for o in rows])


@routes.get("/api/admin/orders/{id}")
async def admin_order(request: web.Request):
    admin_user(request)
    async with Session() as session:
        order = await session.get(Order, int(request.match_info["id"]))
    if not order:
        raise ApiError(404, "Заказ не найден")
    return web.json_response(order_json(order, admin=True))


@routes.post("/api/admin/orders/{id}/status")
async def admin_order_status(request: web.Request):
    admin_user(request)
    data = await read_json(request)
    async with Session() as session:
        order = await session.get(Order, int(request.match_info["id"]))
        if not order:
            raise ApiError(404, "Заказ не найден")
        await services.change_status(session, order, str(data.get("status")), data.get("track"))
    return web.json_response(order_json(order, admin=True))


@routes.get("/api/admin/settings")
async def admin_settings(request: web.Request):
    admin_user(request)
    async with Session() as session:
        return web.json_response(await services.get_settings(session))


@routes.put("/api/admin/settings")
async def admin_save_settings(request: web.Request):
    admin_user(request)
    data = await read_json(request)
    async with Session() as session:
        return web.json_response(await services.save_settings(session, data))


@routes.get("/api/admin/stats")
async def admin_stats(request: web.Request):
    admin_user(request)
    async with Session() as session:
        by_status = dict(
            (await session.execute(select(Order.status, func.count()).group_by(Order.status))).all()
        )
        revenue = (
            await session.execute(
                select(func.coalesce(func.sum(Order.total), 0)).where(Order.status.in_(["paid", "shipped", "done"]))
            )
        ).scalar_one()
        users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        products_count = (await session.execute(select(func.count()).select_from(Product))).scalar_one()
    return web.json_response(
        {"by_status": by_status, "revenue": int(revenue), "users": users, "products": products_count}
    )
