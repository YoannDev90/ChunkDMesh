import aiosqlite
import config
from enum import Enum
from pathlib import Path


class Type(Enum):
    LIST = "list"
    DICT = "dict"
    TUPLE = "tuple"


class Database:
    def __init__(self, db_path: Path = config.DB_PATH):
        self.db_path = db_path

    async def __aenter__(self):
        absolute_path = self.db_path.resolve()
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = await aiosqlite.connect(str(absolute_path))
        self.connection.row_factory = aiosqlite.Row
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.connection.close()

    async def execute_query(
        self, query: str, params: tuple = (), type: Type = Type.LIST
    ):
        """Exécute une requête SQL de manière asynchrone."""
        async with self.connection.execute(query, params) as cursor:
            results = await cursor.fetchall()
            await self.connection.commit()

            if type == Type.LIST:
                return [row[0] for row in results]
            elif type == Type.DICT:
                return [dict(row) for row in results]
            elif type == Type.TUPLE:
                return [tuple(row) for row in results]
            return results

    async def initialize_schema(self):
        """Initialise le schéma de la base de données avec des index."""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                ip_address TEXT NOT NULL,
                last_connected TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                x INTEGER NOT NULL,
                z INTEGER NOT NULL,
                status TEXT DEFAULT 'PENDING',
                UNIQUE(x, z)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);",
            """
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                signature TEXT NOT NULL,
                data_path TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (id),
                FOREIGN KEY (client_id) REFERENCES clients (id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_results_task_id ON results(task_id);",
            "CREATE INDEX IF NOT EXISTS idx_results_client_id ON results(client_id);",
        ]
        for q in queries:
            await self.connection.execute(q)
        await self.connection.commit()
