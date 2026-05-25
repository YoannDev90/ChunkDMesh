import sqlite3
import config
from enum import Enum


class Type(Enum):
    STR = "str"
    LIST = "list"
    DICT = "dict"
    TUPLE = "tuple"


class Database:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self.connection = None

    def connect(self):
        """Établit une connexion à la base de données."""
        # Résout le chemin absolu pour éviter les problèmes de CWD avec mkdir et sqlite
        absolute_path = self.db_path.resolve()
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(absolute_path))

    def close(self):
        """Ferme la connexion à la base de données."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def execute_query(self, query: str, params: tuple = (), type: Type = Type.STR):
        """Exécute une requête SQL avec des paramètres optionnels."""
        if not self.connection:
            self.connect()
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        self.connection.commit()
        results = cursor.fetchall()
        if type == Type.STR:
            return [item[0] for item in results]
        elif type == Type.LIST:
            return [item[0] for item in results]
        elif type == Type.DICT:
            return {item[0]: item[1] for item in results}
        elif type == Type.TUPLE:
            return [tuple(item) for item in results]
        else:
            return results

    def initialize_schema(self):
        """Initialise le schéma de la base de données."""
        create_clients_table = """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            last_connected TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_regions_table = """
        CREATE TABLE IF NOT EXISTS regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            assigned_client_id INTEGER,
            FOREIGN KEY (assigned_client_id) REFERENCES clients (id)
        );
        """
        create_tasks_table = """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            x INTEGER NOT NULL,
            z INTEGER NOT NULL,
            status TEXT DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, VALIDATED, FAILED
            UNIQUE(x, z)
        );
        """
        create_results_table = """
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            client_id INTEGER NOT NULL,
            signature TEXT NOT NULL, -- Hash du mesh pour vérification
            data_path TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks (id),
            FOREIGN KEY (client_id) REFERENCES clients (id)
        );
        """
        self.execute_query(create_clients_table)
        self.execute_query(create_regions_table)
        self.execute_query(create_tasks_table)
        self.execute_query(create_results_table)
