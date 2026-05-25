import flask
import flask.cli
import psutil
import asyncio
import logging

from database import Database
import config

# Désactiver les logs et la bannière Flask/Werkzeug pour plus de clarté
logging.getLogger("werkzeug").setLevel(logging.CRITICAL)
flask.cli.show_server_banner = lambda *args: None

HOST = "127.0.0.1"
LOGGER = logging.getLogger(config.LOGGER_NAME)

app = flask.Flask(__name__)


async def get_port(host: str, start_port: int = 10000, end_port: int = 65535) -> int:
    """Trouve un port disponible à partir de start_port."""

    def _scan_ports():
        used_ports = set()
        try:
            for conn in psutil.net_connections():
                try:
                    if conn.laddr and conn.laddr.ip == host:
                        used_ports.add(conn.laddr.port)
                except (AttributeError, IndexError):
                    continue
        except Exception:
            # Si on ne peut pas lister les connexions, on se repliera sur le test d'écoute
            pass
        return used_ports

    used_ports = await asyncio.to_thread(_scan_ports)

    # Test direct de bind pour confirmer la disponibilité
    import socket as _socket

    for port in range(start_port, end_port):
        if port not in used_ports:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                try:
                    s.bind((host, port))
                    return port
                except OSError:
                    continue
    return None


async def start_api():
    """Démarre l'API Flask sans bloquer la boucle asyncio."""
    port = await get_port(HOST)
    if port is None:
        raise RuntimeError("Aucun port disponible pour démarrer l'API Flask.")

    LOGGER.info(f"Démarrage de l'API sur {HOST}:{port}...")
    server_task = asyncio.create_task(
        asyncio.to_thread(app.run, host=HOST, port=port, use_reloader=False)
    )
    return HOST, port, server_task


@app.route("/connect", methods=["GET"])
def request_task():
    """Endpoint pour se connecter à l'API."""
    client_ip = flask.request.remote_addr
    LOGGER.info(f"Client {client_ip} s'est connecté.")
    db = Database()
    db.connect()
    db.execute_query("INSERT INTO clients (ip_address) VALUES (?)", (client_ip,))
    db.close()
    return flask.jsonify({"message": "Connexion réussie", "client_ip": client_ip})


@app.route("/status", methods=["GET"])
def get_status():
    """Endpoint pour obtenir le statut de l'API."""
    ip = flask.request.remote_addr
    db = Database()
    db.connect()
    connected_clients = db.execute_query("SELECT ip_address FROM clients")
    db.close()
    msg = "Connecté" if (ip,) in connected_clients else "Non connecté"
    return flask.jsonify({"status": "API en cours d'exécution", "message": msg})


@app.route("/disconnect", methods=["GET"])
def disconnect():
    """Endpoint pour se déconnecter de l'API."""
    client_ip = flask.request.remote_addr
    LOGGER.info(f"Client {client_ip} s'est déconnecté.")
    db = Database()
    db.connect()
    db.execute_query("DELETE FROM clients WHERE ip_address = ?", (client_ip,))
    db.close()
    return flask.jsonify({"message": "Déconnexion réussie", "client_ip": client_ip})


if __name__ == "__main__":
    asyncio.run(start_api())
