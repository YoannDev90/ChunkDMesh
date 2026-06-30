"""Task generation and client assignment."""

from __future__ import annotations

import logging
import math

from config import Config
from db import Batch, Task, World, get_db_session
from geometry import generate_spiral_order, is_inside_shape
from sqlalchemy import func, select

logger = logging.getLogger(__name__)

MAX_ASSIGNMENTS = 2


async def fill_tasks_table(config: Config):
    """Fills the tasks table with regions in spiral order from center."""
    async with get_db_session() as session:
        existing = await session.execute(select(func.count(Task.id)))
        if existing.scalar() > 0:
            logger.info("Tasks table already populated, skipping fill.")
            return

        radius_chunks = config.radius
        shape = config.shape
        radius_regions = math.ceil(radius_chunks / 32)

        logger.info(
            "Filling tasks table with shape %s and radius %d chunks (%d regions)...",
            shape,
            radius_chunks,
            radius_regions,
        )

        tasks_to_add = []
        for rx, rz in generate_spiral_order(radius_regions):
            cx, cz = rx * 32, rz * 32
            if is_inside_shape(cx, cz, shape, radius_chunks):
                tasks_to_add.append(Task(region_x=rx, region_z=rz))

            if len(tasks_to_add) >= 1000:
                session.add_all(tasks_to_add)
                await session.commit()
                tasks_to_add = []

        if tasks_to_add:
            session.add_all(tasks_to_add)
            await session.commit()

    logger.info("Tasks table filled in spiral order from center.")


async def attribute_tasks_to_client(client_id: int):
    """Assign next available task to client in spiral order from center."""
    config = Config()
    await config.validate()
    max_assign = MAX_ASSIGNMENTS if config.verification else 1

    async with get_db_session() as session:
        count_subq = (
            select(Batch.region_x, Batch.region_z, Batch.id.label("batch_id"))
            .where(Batch.status.in_(["assigned", "working", "completed", "validated"]))
            .subquery()
        )

        task_counts = (
            select(
                Task.region_x,
                Task.region_z,
                func.count(count_subq.c.batch_id).label("assignment_count"),
            )
            .outerjoin(
                count_subq,
                (Task.region_x == count_subq.c.region_x) & (Task.region_z == count_subq.c.region_z),
            )
            .group_by(Task.id)
            .having(func.count(count_subq.c.batch_id) < max_assign)
            .order_by(Task.region_x * Task.region_x + Task.region_z * Task.region_z)
            .limit(1)
        )

        result = await session.execute(task_counts)
        rows = result.all()

    if not rows:
        raise ValueError("No available tasks")

    region_coords = [(row.region_x, row.region_z) for row in rows]
    logger.info("Attributing %d tasks to client %s: %s", len(region_coords), client_id, region_coords)

    async with get_db_session() as session:
        world_result = await session.execute(select(World).where(World.name == config.world_name).limit(1))
        world = world_result.scalar_one_or_none()

        if not world:
            world = World(
                name=config.world_name,
                seed=int(config.seed),
                mc_version=config.minecraft_version,
                loader_type=config.minecraft_loader,
                status="active",
            )
            session.add(world)
            await session.flush()

        first_rx, first_rz = region_coords[0]
        result = await session.execute(
            Batch.__table__.insert()
            .values(
                assigned_to=client_id,
                world_id=world.id,
                region_x=first_rx,
                region_z=first_rz,
                status="assigned",
            )
            .returning(Batch.id)
        )
        batch_id = result.scalar_one()
        await session.commit()

    return batch_id, region_coords
