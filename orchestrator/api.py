import flask
import psutil

HOST = "127.0.0.1"

app = flask.Flask(__name__)


async def get_port(host: str, start_port: int = 10000, end_port: int = 65535) -> int:
    """Trouve un port disponible à partir de start_port."""
    used_ports = {
        conn.laddr.port
        for conn in psutil.net_connections()
        if conn.laddr and conn.laddr.ip == host
    }
    return next(
        (port for port in range(start_port, end_port) if port not in used_ports), None
    )


async def start_api():
    """Démarre l'API Flask."""
    port = await get_port(HOST)
    print(f"Démarrage de l'API sur {HOST}:{port}...")
    app.run(host=HOST, port=port)


@app.route("/connect", methods=["GET"])
def request_task():
    """Endpoint pour se connecter à l'API."""
    client_ip = flask.request.remote_addr
    print(f"Client {client_ip} s'est connecté.")
    return flask.jsonify({"message": "Connexion réussie", "client_ip": client_ip})


@app.route("/status", methods=["GET"])
def get_status():
    """Endpoint pour obtenir le statut de l'API."""
    return flask.jsonify({"status": "API en cours d'exécution"})


@app.route("/disconnect", methods=["GET"])
def disconnect():
    """Endpoint pour se déconnecter de l'API."""
    client_ip = flask.request.remote_addr
    print(f"Client {client_ip} s'est déconnecté.")
    return flask.jsonify({"message": "Déconnexion réussie", "client_ip": client_ip})


if __name__ == "__main__":
    start_api()
