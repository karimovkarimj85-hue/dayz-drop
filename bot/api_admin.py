"""HTTP API админки мини-аппа (только ADMIN_IDS)."""
import asyncio
import logging

from aiohttp import web
from aiogram.types import BufferedInputFile
from sqlalchemy import func, or_, select

import finance
import loyalty
import services
import tasks
from api import ApiError, admin_user, iso, order_json, product_json, product_stats, read_json, read_upload, user_json, PHOTO_KINDS
from db import Coupon, Expense, Order, PointsTx, Product, Reward, Session, StockMovement, User, now
from loader import bot

log = logging.getLogger(__name__)
routes = web.RouteTableDef()

KIND_LABELS = {"receipt": "Приход", "sale": "Продажа", "return": "Возврат", "writeoff": "Списание",
               "inventory": "Инвентаризация", "adjust": "Корректировка"}
BADGES = {"new", "hit", "soon"}


def admin_name(user) -> str:
    return user.first_name or user.username or str(user.id)


async def _settings(session) -> dict:
    return await services.get_settings(session)


# ---------- обзор ----------

@routes.get("/api/admin/dashboard")
async def dashboard(request: web.Request):
    admin_user(request)
    async with Session() as session:
        settings = await _settings(session)
        by_status = dict((await session.execute(select(Order.status, func.count()).group_by(Order.status))).all())
        today = await finance.report(session, "today")
        month = await finance.report(session, "month")
        products = list((await session.execute(select(Product))).scalars())
        users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        registered = (await session.execute(
            select(func.count()).select_from(User).where(User.registered_at.is_not(None)))).scalar_one()
    low = [{"product_id": p.id, "title": p.title, "size": s["size"], "stock": s["stock"]}
           for p in products if p.is_active for s in p.sizes if s["stock"] <= settings["low_stock"]]
    return web.json_response({
        "by_status": by_status,
        "today": {k: today[k] for k in ("revenue", "orders", "profit")},
        "month": {k: month[k] for k in ("revenue", "orders", "profit")},
        "units": sum(s["stock"] for p in products for s in p.sizes),
        "products": len(products),
        "low_stock": low,
        "users": users,
        "registered": registered,
    })


@routes.get("/api/admin/stats")
async def stats(request: web.Request):
    admin_user(request)
    async with Session() as session:
        by_status = dict((await session.execute(select(Order.status, func.count()).group_by(Order.status))).all())
        r = await finance.report(session, "all")
        users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        products_count = (await session.execute(select(func.count()).select_from(Product))).scalar_one()
    return web.json_response({"by_status": by_status, "revenue": r["revenue"], "users": users, "products": products_count})


# ---------- заказы ----------

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
        customer = await session.get(User, order.user_id)
    data = order_json(order, admin=True)
    data["customer"] = user_json(customer) | {"no_cash": bool(customer and customer.no_cash),
                                              "note": customer.note if customer else None}
    return web.json_response(data)


@routes.post("/api/admin/orders/{id}/status")
async def admin_order_status(request: web.Request):
    user = admin_user(request)
    data = await read_json(request)
    async with Session() as session:
        order = await session.get(Order, int(request.match_info["id"]))
        if not order:
            raise ApiError(404, "Заказ не найден")
        await services.change_status(session, order, str(data.get("status")), data.get("track"), actor=admin_name(user))
    return web.json_response(order_json(order, admin=True))


@routes.post("/api/admin/orders/{id}/assign")
async def admin_order_assign(request: web.Request):
    user = admin_user(request)
    async with Session() as session:
        order = await session.get(Order, int(request.match_info["id"]))
        if not order:
            raise ApiError(404, "Заказ не найден")
        await services.toggle_assign(session, order, user.id, admin_name(user))
    return web.json_response(order_json(order, admin=True))


@routes.post("/api/admin/orders/{id}/noshow")
async def admin_order_noshow(request: web.Request):
    """«Не выкупил»: отмена наличного заказа и запрет наличных для этого покупателя."""
    user = admin_user(request)
    async with Session() as session:
        order = await session.get(Order, int(request.match_info["id"]))
        if not order:
            raise ApiError(404, "Заказ не найден")
        await services.change_status(session, order, "cancelled", actor=f"{admin_name(user)} (не выкупил)")
        customer = await session.get(User, order.user_id)
        if customer:
            customer.no_cash = True
            await session.commit()
    return web.json_response(order_json(order, admin=True))


# ---------- товары ----------

def _clean_product(data: dict) -> dict:
    title = str(data.get("title") or "").strip()[:200]
    if not title:
        raise ApiError(400, "Нужно название товара")
    price = services.to_int(data.get("price"), -1)
    if price < 0:
        raise ApiError(400, "Укажи цену")
    sizes = services.clean_sizes(data.get("sizes"))
    if not sizes:
        raise ApiError(400, "Добавь хотя бы один размер")
    old_price = services.to_int(data.get("old_price")) or None
    if old_price and old_price <= price:
        old_price = None
    badge = data.get("badge") if data.get("badge") in BADGES else None
    return {
        "title": title,
        "description": str(data.get("description") or "").strip()[:3000],
        "category": str(data.get("category") or "").strip()[:100],
        "price": price,
        "old_price": old_price,
        "size_chart": str(data.get("size_chart") or "").strip()[:2000] or None,
        "badge": badge,
        "sizes": sizes,
        "photos": [str(p) for p in (data.get("photos") or []) if p][:10],
        "is_active": bool(data.get("is_active", True)),
        "sort": services.to_int(data.get("sort"), 0, None),
    }


@routes.get("/api/admin/products")
async def admin_products(request: web.Request):
    admin_user(request)
    async with Session() as session:
        rows = (await session.execute(select(Product).order_by(Product.sort, Product.id.desc()))).scalars().all()
        ratings, likes = await product_stats(session)
    return web.json_response([product_json(p, ratings, likes) for p in rows])


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
        was_soon = product.badge == "soon"
        await services.apply_sizes(session, product, values.pop("sizes"), user.id)
        for key, value in values.items():
            setattr(product, key, value)
        await session.commit()
        if was_soon and product.badge != "soon":
            await services.notify_back_in_stock(session, product, [s["size"] for s in product.sizes if s["stock"] > 0],
                                                soon_released=True)
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
    """Загружает фото в Telegram (себе в чат и сразу удаляет) и возвращает file_id."""
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


# ---------- склад ----------

@routes.get("/api/admin/stock")
async def admin_stock(request: web.Request):
    admin_user(request)
    product_id = request.query.get("product_id")
    query = select(StockMovement).order_by(StockMovement.id.desc()).limit(150)
    if product_id:
        query = query.where(StockMovement.product_id == int(product_id))
    async with Session() as session:
        products = (await session.execute(select(Product).order_by(Product.sort, Product.id.desc()))).scalars().all()
        movements = (await session.execute(query)).scalars().all()
        report = await finance.report(session, "all")
        settings = await _settings(session)
    return web.json_response({
        "products": [product_json(p) for p in products],
        "units": sum(s["stock"] for p in products for s in p.sizes),
        "received_value": report["purchases"],
        "stock_value": report["stock_value"],
        "low_stock": settings["low_stock"],
        "movements": [{
            "id": m.id, "product_id": m.product_id, "product_title": m.product_title, "size": m.size,
            "delta": m.delta, "kind": m.kind, "kind_label": KIND_LABELS.get(m.kind, m.kind), "cost": m.cost,
            "note": m.note, "created_at": iso(m.created_at),
        } for m in movements],
    })


async def _product_or_404(session, product_id) -> Product:
    product = await session.get(Product, services.to_int(product_id))
    if not product:
        raise ApiError(404, "Товар не найден")
    return product


@routes.post("/api/admin/stock/receipt")
async def admin_stock_receipt(request: web.Request):
    user = admin_user(request)
    data = await read_json(request)
    cost = services.to_int(data.get("cost")) or None if data.get("cost") not in (None, "") else None
    async with Session() as session:
        product = await _product_or_404(session, data.get("product_id"))
        await services.receive_stock(session, product, data.get("items") or [], cost=cost,
                                     note=str(data.get("note") or "Приход товара").strip(), admin_id=user.id)
    return web.json_response(product_json(product))


@routes.post("/api/admin/stock/writeoff")
async def admin_stock_writeoff(request: web.Request):
    user = admin_user(request)
    data = await read_json(request)
    async with Session() as session:
        product = await _product_or_404(session, data.get("product_id"))
        await services.writeoff_stock(session, product, data.get("items") or [],
                                      reason=str(data.get("reason") or "Списание").strip(), admin_id=user.id)
    return web.json_response(product_json(product))


@routes.post("/api/admin/stock/inventory")
async def admin_stock_inventory(request: web.Request):
    """Инвентаризация: вводишь фактические остатки, разница пишется в журнал."""
    user = admin_user(request)
    data = await read_json(request)
    async with Session() as session:
        product = await _product_or_404(session, data.get("product_id"))
        sizes = services.clean_sizes(data.get("sizes"))
        if not sizes:
            raise ApiError(400, "Укажи остатки")
        await services.apply_sizes(session, product, sizes, user.id, note=str(data.get("note") or "Инвентаризация"),
                                   kind="inventory")
        await session.commit()
    return web.json_response(product_json(product))


# ---------- касса ----------

@routes.get("/api/admin/finance")
async def admin_finance(request: web.Request):
    admin_user(request)
    period = request.query.get("period", "month")
    if period not in finance.PERIODS:
        period = "month"
    async with Session() as session:
        return web.json_response(await finance.report(session, period) | {"kinds": finance.EXPENSE_KINDS})


@routes.post("/api/admin/expenses")
async def admin_add_expense(request: web.Request):
    user = admin_user(request)
    data = await read_json(request)
    amount = services.to_int(data.get("amount"))
    kind = data.get("kind") if data.get("kind") in finance.EXPENSE_KINDS else "other"
    if amount <= 0:
        raise ApiError(400, "Укажи сумму расхода")
    async with Session() as session:
        expense = Expense(kind=kind, amount=amount, note=str(data.get("note") or "").strip()[:500],
                          admin_name=admin_name(user))
        session.add(expense)
        await session.commit()
    return web.json_response(finance.expense_json(expense))


@routes.delete("/api/admin/expenses/{id}")
async def admin_delete_expense(request: web.Request):
    admin_user(request)
    async with Session() as session:
        expense = await session.get(Expense, int(request.match_info["id"]))
        if expense:
            await session.delete(expense)
            await session.commit()
    return web.json_response({"ok": True})


# ---------- покупатели ----------

async def _customer_stats(session) -> dict[int, dict]:
    stats: dict[int, dict] = {}
    for o in (await session.execute(select(Order))).scalars():
        s = stats.setdefault(o.user_id, {"orders": 0, "spent": 0, "cancelled": 0, "last": None})
        if o.status == "cancelled":
            s["cancelled"] += 1
            continue
        s["orders"] += 1
        if o.paid_at:
            s["spent"] += o.total
        s["last"] = max(filter(None, [s["last"], iso(o.created_at)]), default=None)
    return stats


@routes.get("/api/admin/customers")
async def admin_customers(request: web.Request):
    admin_user(request)
    q = (request.query.get("q") or "").strip().lstrip("@")
    async with Session() as session:
        query = select(User)
        if q:
            like = f"%{q}%"
            query = query.where(or_(User.full_name.ilike(like), User.first_name.ilike(like),
                                    User.username.ilike(like), User.phone.ilike(like)))
        users = list((await session.execute(query.limit(300))).scalars())
        stats = await _customer_stats(session)
    rows = []
    for u in users:
        s = stats.get(u.id, {"orders": 0, "spent": 0, "cancelled": 0, "last": None})
        rows.append(user_json(u) | s | {"no_cash": bool(u.no_cash), "note": u.note})
    rows.sort(key=lambda r: (-r["spent"], -r["orders"]))
    return web.json_response(rows)


@routes.get("/api/admin/customers/{id}")
async def admin_customer(request: web.Request):
    admin_user(request)
    user_id = int(request.match_info["id"])
    async with Session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise ApiError(404, "Покупатель не найден")
        orders = (await session.execute(select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()))).scalars()
        history = await finance.points_history(session, user_id)
        stats = (await _customer_stats(session)).get(user_id, {"orders": 0, "spent": 0, "cancelled": 0, "last": None})
    return web.json_response(user_json(user) | stats | {
        "no_cash": bool(user.no_cash), "note": user.note,
        "orders_list": [order_json(o, admin=True) for o in orders], "history": history,
    })


@routes.put("/api/admin/customers/{id}")
async def admin_update_customer(request: web.Request):
    admin_user(request)
    data = await read_json(request)
    async with Session() as session:
        user = await session.get(User, int(request.match_info["id"]))
        if not user:
            raise ApiError(404, "Покупатель не найден")
        if "note" in data:
            user.note = str(data.get("note") or "").strip()[:1000] or None
        if "no_cash" in data:
            user.no_cash = bool(data["no_cash"])
        await session.commit()
    return web.json_response({"ok": True})


@routes.post("/api/admin/customers/{id}/points")
async def admin_customer_points(request: web.Request):
    admin = admin_user(request)
    data = await read_json(request)
    delta = services.to_int(data.get("delta"), 0, None)
    reason = str(data.get("reason") or "").strip() or ("Бонус от DAYZ DROP" if delta > 0 else "Списание баллов")
    async with Session() as session:
        user = await session.get(User, int(request.match_info["id"]))
        if not user:
            raise ApiError(404, "Покупатель не найден")
        if not user.registered_at:
            raise ApiError(400, "Баллы можно начислять только зарегистрированным")
        await loyalty.add_points(session, user, delta, reason, admin_name=admin_name(admin))
    return web.json_response({"points": user.points})


@routes.post("/api/admin/points/campaign")
async def admin_points_campaign(request: web.Request):
    """Бонус всем зарегистрированным разом — например, к новому дропу."""
    admin = admin_user(request)
    data = await read_json(request)
    amount = services.to_int(data.get("amount"))
    reason = str(data.get("reason") or "Бонус от DAYZ DROP").strip()[:200]
    if amount <= 0:
        raise ApiError(400, "Укажи, сколько баллов начислить")
    async with Session() as session:
        users = list((await session.execute(select(User).where(User.registered_at.is_not(None)))).scalars())
        for u in users:
            await loyalty.add_points(session, u, amount, reason, admin_name=admin_name(admin))
    return web.json_response({"users": len(users)})


# ---------- купоны и награды ----------

async def _maps(session):
    products_map = {p.id: p for p in (await session.execute(select(Product))).scalars()}
    return products_map, (await _settings(session))["currency"]


@routes.get("/api/admin/coupons")
async def admin_coupons(request: web.Request):
    admin_user(request)
    async with Session() as session:
        products_map, cur = await _maps(session)
        rows = (await session.execute(select(Coupon).where(Coupon.source == "admin").order_by(Coupon.id.desc()))).scalars()
        rewards = (await session.execute(select(Reward).order_by(Reward.sort, Reward.cost))).scalars()
        issued = (await session.execute(select(func.count()).select_from(Coupon).where(Coupon.source == "reward"))).scalar_one()
    return web.json_response({
        "coupons": [loyalty.coupon_json(c, products_map, cur) for c in rows],
        "rewards": [loyalty.reward_json(r, products_map, cur) for r in rewards],
        "reward_coupons_issued": issued,
    })


@routes.post("/api/admin/coupons")
async def admin_create_coupon(request: web.Request):
    admin_user(request)
    data = await read_json(request)
    values = loyalty.clean_coupon(data)
    async with Session() as session:
        code = loyalty.normalize_code(data.get("code")) or await loyalty.unique_code(session)
        if not 4 <= len(code) <= 12:
            raise ApiError(400, "Промокод — от 4 до 12 латинских букв и цифр")
        if (await session.execute(select(Coupon.id).where(Coupon.code == code))).first():
            raise ApiError(400, "Такой промокод уже есть")
        coupon = Coupon(code=code, source="admin", used_count=0, **values)
        session.add(coupon)
        await session.commit()
        products_map, cur = await _maps(session)
    return web.json_response(loyalty.coupon_json(coupon, products_map, cur))


@routes.put("/api/admin/coupons/{id}")
async def admin_update_coupon(request: web.Request):
    admin_user(request)
    values = loyalty.clean_coupon(await read_json(request))
    async with Session() as session:
        coupon = await session.get(Coupon, int(request.match_info["id"]))
        if not coupon:
            raise ApiError(404, "Промокод не найден")
        for key, value in values.items():
            setattr(coupon, key, value)
        await session.commit()
        products_map, cur = await _maps(session)
    return web.json_response(loyalty.coupon_json(coupon, products_map, cur))


@routes.delete("/api/admin/coupons/{id}")
async def admin_delete_coupon(request: web.Request):
    admin_user(request)
    async with Session() as session:
        coupon = await session.get(Coupon, int(request.match_info["id"]))
        if coupon:
            await session.delete(coupon)
            await session.commit()
    return web.json_response({"ok": True})


@routes.post("/api/admin/rewards")
async def admin_create_reward(request: web.Request):
    admin_user(request)
    values = loyalty.clean_reward(await read_json(request))
    async with Session() as session:
        reward = Reward(**values)
        session.add(reward)
        await session.commit()
        products_map, cur = await _maps(session)
    return web.json_response(loyalty.reward_json(reward, products_map, cur))


@routes.put("/api/admin/rewards/{id}")
async def admin_update_reward(request: web.Request):
    admin_user(request)
    values = loyalty.clean_reward(await read_json(request))
    async with Session() as session:
        reward = await session.get(Reward, int(request.match_info["id"]))
        if not reward:
            raise ApiError(404, "Награда не найдена")
        for key, value in values.items():
            setattr(reward, key, value)
        await session.commit()
        products_map, cur = await _maps(session)
    return web.json_response(loyalty.reward_json(reward, products_map, cur))


@routes.delete("/api/admin/rewards/{id}")
async def admin_delete_reward(request: web.Request):
    admin_user(request)
    async with Session() as session:
        reward = await session.get(Reward, int(request.match_info["id"]))
        if reward:
            await session.delete(reward)
            await session.commit()
    return web.json_response({"ok": True})


# ---------- рассылка, выгрузки, бэкап ----------

@routes.post("/api/admin/broadcast")
async def admin_broadcast(request: web.Request):
    user = admin_user(request)
    data = await read_json(request)
    text = str(data.get("text") or "").strip()
    if not text:
        raise ApiError(400, "Напиши текст рассылки")
    if len(text) > (1000 if data.get("photo") else 4000):
        raise ApiError(400, "Слишком длинный текст")
    audience = "registered" if data.get("audience") == "registered" else "all"
    async with Session() as session:
        query = select(func.count()).select_from(User)
        if audience == "registered":
            query = query.where(User.registered_at.is_not(None))
        count = (await session.execute(query)).scalar_one()
    asyncio.create_task(tasks.broadcast(user.id, text, data.get("photo") or None, audience, bool(data.get("button", True))))
    return web.json_response({"queued": count})


@routes.post("/api/admin/export")
async def admin_export(request: web.Request):
    """Excel-файл приходит админу в чат с ботом — из мини-аппа в Telegram так надёжнее, чем скачивание."""
    user = admin_user(request)
    data = await read_json(request)
    kind = data.get("kind", "all")
    async with Session() as session:
        if kind == "backup":
            content, filename = await finance.backup_zip(session)
        else:
            try:
                content, filename = await finance.export_xlsx(session, kind)
            except ValueError:
                raise ApiError(400, "Неизвестная выгрузка")
    await bot.send_document(user.id, BufferedInputFile(content, filename=filename), caption=f"📤 {filename}")
    return web.json_response({"ok": True, "filename": filename})


# ---------- настройки ----------

@routes.get("/api/admin/settings")
async def admin_settings(request: web.Request):
    admin_user(request)
    async with Session() as session:
        settings = await _settings(session)
    return web.json_response({k: v for k, v in settings.items() if k in services.EDITABLE_KEYS})


@routes.put("/api/admin/settings")
async def admin_save_settings(request: web.Request):
    admin_user(request)
    data = await read_json(request)
    async with Session() as session:
        settings = await services.save_settings(session, data)
    return web.json_response({k: v for k, v in settings.items() if k in services.EDITABLE_KEYS})
