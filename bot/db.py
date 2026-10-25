from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import DATABASE_URL


def _prepare_url(url: str) -> tuple[str, dict]:
    """Приводит строку подключения (Neon, Render, локальная) к виду для async SQLAlchemy."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    connect_args: dict = {}
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = "require"
        # Пулер Neon (pgbouncer) не дружит с подготовленными запросами asyncpg
        connect_args["statement_cache_size"] = 0
        query["prepared_statement_cache_size"] = "0"
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url, connect_args


_url, _connect_args = _prepare_url(DATABASE_URL)
engine = create_async_engine(_url, connect_args=_connect_args, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite отдаёт даты без часового пояса — считаем их UTC, как и сохраняли."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Регистрация необязательна: заполняется, если покупатель сам захотел (даёт баллы)
    full_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    points: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(Text)  # заметка админа о покупателе
    no_cash: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # «не выкупил»


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    price: Mapped[int] = mapped_column(Integer)
    # [{"size": "M", "stock": 3}, ...] — порядок важен, поэтому список, а не словарь
    sizes: Mapped[list] = mapped_column(JSON, default=list)
    # file_id фото в Telegram — так не нужно отдельное хранилище картинок
    photos: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    old_price: Mapped[int | None] = mapped_column(Integer)  # зачёркнутая цена (скидка)
    size_chart: Mapped[str | None] = mapped_column(Text)  # замеры по размерам
    badge: Mapped[str | None] = mapped_column(String(10))  # new | hit | soon


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    customer_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50))
    delivery: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    # Снимок товаров на момент заказа: [{"product_id", "title", "size", "qty", "price", "cost", "photo"}]
    items: Mapped[list] = mapped_column(JSON)
    total: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="awaiting_payment", index=True)
    receipt_file_id: Mapped[str | None] = mapped_column(String(255))
    receipt_kind: Mapped[str | None] = mapped_column(String(10))  # photo | document
    track: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    # Оплата и деньги
    payment_method: Mapped[str] = mapped_column(String(10), default="card", server_default="card")  # card | cash
    card_label: Mapped[str | None] = mapped_column(String(100))  # на чью карту назначен перевод
    card_details: Mapped[str | None] = mapped_column(Text)
    delivery_id: Mapped[str | None] = mapped_column(String(30))
    subtotal: Mapped[int | None] = mapped_column(Integer)  # товары без доставки и скидки
    delivery_price: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    discount: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    coupon_code: Mapped[str | None] = mapped_column(String(20))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_via: Mapped[str | None] = mapped_column(String(100))  # «Карта · Карим» или «Наличные»
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Работа админов
    assignee_id: Mapped[int | None] = mapped_column(BigInteger)
    assignee_name: Mapped[str | None] = mapped_column(String(128))
    history: Mapped[list | None] = mapped_column(JSON)  # [{"at", "who", "text"}]
    # Оценка покупателя после получения
    rating: Mapped[int | None] = mapped_column(Integer)
    rating_comment: Mapped[str | None] = mapped_column(Text)


class StockMovement(Base):
    """Журнал склада: каждое изменение остатка — приход, продажа, возврат, списание или корректировка."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    product_title: Mapped[str] = mapped_column(String(200))
    size: Mapped[str] = mapped_column(String(20))
    delta: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))  # receipt | sale | return | writeoff | inventory | adjust
    cost: Mapped[int | None] = mapped_column(Integer)  # цена закупки за штуку (для прихода)
    note: Mapped[str] = mapped_column(Text, default="")
    admin_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Expense(Base):
    """Расходы для кассы: доставка, реклама, упаковка и прочее (закупка считается из приходов)."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    admin_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Coupon(Base):
    """Промокод админа или личный купон, полученный за баллы."""

    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(10))  # percent | amount | gift
    value: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[int | None] = mapped_column(Integer)  # для gift — какая вещь в подарок
    min_total: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    once_per_user: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)  # личный купон
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(10), default="admin")  # admin | reward
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Reward(Base):
    """Что можно получить за баллы: скидка или вещь в подарок."""

    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))  # percent | amount | gift
    value: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[int] = mapped_column(Integer)  # цена в баллах
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PointsTx(Base):
    """История баллов: начисления за заказы, бонусы админа, обмен на награды."""

    __tablename__ = "points_tx"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(300), default="")
    order_id: Mapped[int | None] = mapped_column(Integer)
    admin_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Subscription(Base):
    """«Сообщить о поступлении»: size="*" — для товара со статусом «Скоро»."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    size: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Cart(Base):
    """Корзина для покупок через кнопки бота: [{"product_id", "size", "qty"}]."""

    __tablename__ = "carts"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    items: Mapped[list] = mapped_column(JSON, default=list)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


def _add_missing_columns(conn) -> None:
    """create_all не добавляет новые колонки в уже существующие таблицы — дописываем их сами."""
    insp = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(dialect=conn.dialect)}"
            if column.server_default is not None:
                default = column.server_default.arg
                ddl += f" DEFAULT {default if default in ('true', 'false') or default.isdigit() else repr(default)}"
            conn.execute(text(ddl))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
