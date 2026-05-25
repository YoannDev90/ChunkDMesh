import sqlite3
import config


class Database:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self.connection = None

    def connect(self):
        """Établit une connexion à la base de données."""
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)

    def close(self):
        """Ferme la connexion à la base de données."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def execute_query(self, query: str, params: tuple = ()):
        """Exécute une requête SQL avec des paramètres optionnels."""
        if not self.connection:
            self.connect()
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        self.connection.commit()
        return cursor.fetchall()

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
        self.execute_query(create_clients_table)
        self.execute_query(create_regions_table)
