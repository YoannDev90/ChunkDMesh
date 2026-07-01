"""Asynchronous SQLAlchemy models and DB initialization helpers.

Defines the main tables used by the orchestrator and provides an
`init_db()` coroutine that will create the tables for the configured
database. By default this uses SQLite (aiosqlite) and the local
`data/chunkdmesh.db` file.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from sqlalchemy import BIGINT, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

_DB_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{_DB_DIR / 'chunkdmesh.db'}"


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""

    pass


class Client(Base):
    """Minecraft client that renders chunks for the orchestrator."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str | None] = mapped_column(String(128), unique=True)
    ip: Mapped[str | None] = mapped_column(String(45))
    power_score: Mapped[float | None] = mapped_column()
    benchmark_score: Mapped[float | None] = mapped_column()
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)

    batches: Mapped[list[Batch]] = relationship("Batch", back_populates="client")


class World(Base):
    """Minecraft world configuration stored in the database."""

    __tablename__ = "worlds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    seed: Mapped[int] = mapped_column(BIGINT, nullable=False)
    mc_version: Mapped[str | None] = mapped_column(String(50))
    loader_type: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="pending")

    batches: Mapped[list[Batch]] = relationship("Batch", back_populates="world")


class Batch(Base):
    """Region batch assigned to a client for rendering."""

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[int] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    region_x: Mapped[int] = mapped_column(Integer, nullable=False)
    region_z: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("clients.id"))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    world: Mapped[World] = relationship("World", back_populates="batches")
    client: Mapped[Client | None] = relationship("Client", back_populates="batches")
    validations: Mapped[list[Validation]] = relationship("Validation", back_populates="batch")


class Task(Base):
    """Available region rendering task."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_x: Mapped[int] = mapped_column(Integer, nullable=False)
    region_z: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("region_x", "region_z", name="uq_task_region"),)


class Validation(Base):
    """Validation record for a rendered region file hash."""

    __tablename__ = "validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    batch: Mapped[Batch] = relationship("Batch", back_populates="validations")


# Async engine & session factory
engine = create_async_engine(DATABASE_URL, echo=False, future=True, connect_args={"timeout": 30})
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create database tables with WAL mode + indexes."""
    async with engine.begin() as conn:
        # Optimize SQLite for concurrent read/write
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        await conn.exec_driver_sql("PRAGMA cache_size=-64000")  # 64 MB cache
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")

        await conn.run_sync(Base.metadata.create_all)

        # Indexes for frequent queries
        await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_batches_region ON batches(region_x, region_z)")
        await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status)")
        await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_batches_assigned ON batches(assigned_to)")
        await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_clients_token ON clients(token)")


def get_db_session() -> AsyncSession:
    """Get a new async database session."""
    return AsyncSessionLocal()


if __name__ == "__main__":
    asyncio.run(init_db())
