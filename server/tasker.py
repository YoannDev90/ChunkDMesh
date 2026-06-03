from config import Config, ChunkyShape
from db import Task, Client, Batch, get_db_session
import math

async def fill_tasks_table(config: Config):
    """
    Fills the tasks table with regions based on the configured radius and shape.
    Radius is in chunks, but we group tasks by regions (32x32 chunks).
    """
    async with get_db_session() as session:
        radius_chunks = config.radius
        shape = config.shape
        
        # Convert chunk radius to region radius
        radius_regions = math.ceil(radius_chunks / 32)

        print(f"Filling tasks table with shape {shape} and radius {radius_chunks} chunks ({radius_regions} regions)...")
        
        tasks_to_add = []
        batch_size = 1000

        for rx in range(-radius_regions, radius_regions + 1):
            for rz in range(-radius_regions, radius_regions + 1):
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
    
    print("Tasks table filled.")

async def attribute_tasks_to_client(client_id: int):
    SIZE = 10

    # Get SIZE tasks from the tasks table
    async with get_db_session() as session:
        result = await session.execute(
            Task.__table__.select().limit(SIZE)
        )
        tasks = result.scalars().all()

    region_coords = [(task.region_x, task.region_z) for task in tasks]
    print(f"Attributing {len(region_coords)} tasks to client {client_id}: {region_coords}")

    # Create a new batch for this client
    async with get_db_session() as session:
        result = await session.execute(
            Batch.__table__.insert().values(client_id=client_id).returning(Batch.id)
        )
        batch_id = result.scalar_one()

        await session.commit()

    return batch_id, region_coords

    

