from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from config import Config, ChunkyShape
from db import Task, Client, Batch, World, get_db_session
import math

MAX_ASSIGNMENTS = 2


def generate_spiral_order(radius_regions: int):
    """
    Generate region coordinates in concentric rings from center (0,0).
    Yields (rx, rz) tuples ordered by distance from center.
    """
    # Ring 0: just (0,0)
    yield (0, 0)

    # Rings 1, 2, ...
    for ring in range(1, radius_regions + 1):
        # Generate all coordinates at exactly this ring distance
        coords = []

        # Top edge (z = -ring, x from -ring to ring)
        for x in range(-ring, ring + 1):
            coords.append((x, -ring))

        # Right edge (x = ring, z from -ring+1 to ring)
        for z in range(-ring + 1, ring + 1):
            coords.append((ring, z))

        # Bottom edge (z = ring, x from ring-1 down to -ring)
        for x in range(ring - 1, -ring - 1, -1):
            coords.append((x, ring))

        # Left edge (x = -ring, z from ring-1 down to -ring+1)
        for z in range(ring - 1, -ring, -1):
            coords.append((-ring, z))

        # Sort by actual distance from center, then by angle for consistent ordering
        coords.sort(key=lambda c: (c[0]**2 + c[1]**2, math.atan2(c[1], c[0])))

        for coord in coords:
            yield coord


async def fill_tasks_table(config: Config):
    """
    Fills the tasks table with regions based on the configured radius and shape.
    Radius is in chunks, but we group tasks by regions (32x32 chunks).
    Tasks are inserted in spiral-ordered by concentric rings from center (0,0).
    """
    async with get_db_session() as session:
        existing = await session.execute(select(func.count(Task.id)))
        if existing.scalar() > 0:
            print("Tasks table already populated, skipping fill.")
            return

        radius_chunks = config.radius
        shape = config.shape

        # Convert chunk radius to region radius
        radius_regions = math.ceil(radius_chunks / 32)

        print(f"Filling tasks table with shape {shape} and radius {radius_chunks} chunks ({radius_regions} regions)...")

        tasks_to_add = []
        batch_size = 1000

        # Generate all candidate regions in spiral order
        spiral_coords = list(generate_spiral_order(radius_regions))

        for rx, rz in spiral_coords:
            is_inside = False

            # Check if this region is within reaching distance of the shape
            # (Simple center-based check for regions)
            cx, cz = rx * 32, rz * 32

            if shape == ChunkyShape.SQUARE:
                is_inside = True
            elif shape == ChunkyShape.CIRCLE:
                if (cx ** 2 + cz ** 2) <= radius_chunks ** 2:
                    is_inside = True
            elif shape in [ChunkyShape.DIAMOND, ChunkyShape.TRIANGLE]:
                if abs(cx) + abs(cz) <= radius_chunks:
                    is_inside = True
            elif shape in [ChunkyShape.HEXAGON, ChunkyShape.PENTAGON, ChunkyShape.STAR]:
                # Simplified logic for complex shapes
                if (cx ** 2 + cz ** 2) <= radius_chunks ** 2:
                    is_inside = True
            else:
                is_inside = True

            if is_inside:
                tasks_to_add.append(Task(region_x=rx, region_z=rz))

            if len(tasks_to_add) >= batch_size:
                session.add_all(tasks_to_add)
                await session.commit()
                tasks_to_add = []

        if tasks_to_add:
            session.add_all(tasks_to_add)
            await session.commit()

    print("Tasks table filled in spiral order from center.")


async def attribute_tasks_to_client(client_id: int):
    """
    Assign next available task(s) to client in spiral order from center.
    Returns single region (or small batch) from the next available ring.
    """
    SIZE = 1  # One region at a time for immediate upload

    config = Config()
    verification = config.verification
    max_assign = MAX_ASSIGNMENTS if verification else 1

    async with get_db_session() as session:
        count_subq = (
            select(
                Batch.region_x,
                Batch.region_z,
                Batch.id.label("batch_id"),
            )
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
                (Task.region_x == count_subq.c.region_x)
                & (Task.region_z == count_subq.c.region_z),
            )
            .group_by(Task.id)
            .having(func.count(count_subq.c.batch_id) < max_assign)
            .order_by(Task.region_x * Task.region_x + Task.region_z * Task.region_z)  # Closest to center first
            .limit(SIZE)
        )

        result = await session.execute(task_counts)
        rows = result.all()

    if not rows:
        raise ValueError("No available tasks")

    region_coords = [(row.region_x, row.region_z) for row in rows]
    print(f"Attributing {len(region_coords)} tasks to client {client_id}: {region_coords}")

    async with get_db_session() as session:
        world_result = await session.execute(
            select(World).where(World.name == config.world_name).limit(1)
        )
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