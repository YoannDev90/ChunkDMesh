"""Asynchronous SQLAlchemy models and DB initialization helpers.

Defines the main tables used by the orchestrator and provides an
`init_db()` coroutine that will create the tables for the configured
database. By default this uses SQLite (aiosqlite) and the local
`data/chunkdmesh.db` file.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (BIGINT, DateTime, ForeignKey, Integer, String, Text,
                        func, UniqueConstraint)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import (Mapped, declarative_base, mapped_column,
                            relationship, sessionmaker)

DATABASE_URL = "sqlite+aiosqlite:///./data/chunkdmesh.db"

Base = declarative_base()


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[Optional[str]] = mapped_column(String(128), unique=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45))
    power_score: Mapped[Optional[float]] = mapped_column()
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime)

    batches: Mapped[List["Batch"]] = relationship("Batch", back_populates="client")


class World(Base):
    __tablename__ = "worlds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    seed: Mapped[int] = mapped_column(BIGINT, nullable=False)
    mc_version: Mapped[Optional[str]] = mapped_column(String(50))
    loader_type: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="pending")

    batches: Mapped[List["Batch"]] = relationship("Batch", back_populates="world")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[int] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    region_x: Mapped[int] = mapped_column(Integer, nullable=False)
    region_z: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    world: Mapped["World"] = relationship("World", back_populates="batches")
    client: Mapped[Optional["Client"]] = relationship(
        "Client", back_populates="batches"
    )
    validations: Mapped[List["Validation"]] = relationship(
        "Validation", back_populates="batch"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_x: Mapped[int] = mapped_column(Integer, nullable=False)
    region_z: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("region_x", "region_z", name="uq_task_region"),)


class Validation(Base):
    __tablename__ = "validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    batch: Mapped["Batch"] = relationship("Batch", back_populates="validations")


# Async engine & session factory
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create database tables.

    Example:
            import asyncio
            from server.db import init_db

            asyncio.run(init_db())
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_db_session() -> AsyncSession:
    """Get a new async database session."""
    return AsyncSessionLocal()


if __name__ == "__main__":
    asyncio.run(init_db())
