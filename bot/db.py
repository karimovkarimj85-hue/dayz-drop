from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


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
    # Снимок товаров на момент заказа: [{"product_id", "title", "size", "qty", "price", "photo"}]
    items: Mapped[list] = mapped_column(JSON)
    total: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="awaiting_payment", index=True)
    receipt_file_id: Mapped[str | None] = mapped_column(String(255))
    receipt_kind: Mapped[str | None] = mapped_column(String(10))  # photo | document
    track: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Cart(Base):
    """Корзина для покупок через кнопки бота: [{"product_id", "size", "qty"}]."""

    __tablename__ = "carts"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    items: Mapped[list] = mapped_column(JSON, default=list)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
