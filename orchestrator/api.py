import flask
import flask.cli
import psutil
import asyncio
import logging
from flasgger import Swagger

from database import Database, Type
import config

# Désactiver les logs et la bannière Flask/Werkzeug pour plus de clarté
logging.getLogger("werkzeug").setLevel(logging.CRITICAL)
flask.cli.show_server_banner = lambda *args: None

HOST = "127.0.0.1"
LOGGER = logging.getLogger(config.LOGGER_NAME)

app = flask.Flask(__name__)
swagger = Swagger(app)


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
    """Endpoint pour se connecter à l'API.
    ---
    responses:
      200:
        description: Connexion réussie
    """
    client_ip = flask.request.remote_addr
    LOGGER.info(f"Client {client_ip} s'est connecté.")
    db = Database()
    db.connect()
    db.execute_query("INSERT INTO clients (ip_address) VALUES (?)", (client_ip,))
    db.close()
    return flask.jsonify({"message": "Connexion réussie", "client_ip": client_ip})


@app.route("/status", methods=["GET"])
def get_status():
    """Endpoint pour obtenir le statut de l'API.
    ---
    responses:
      200:
        description: Statut de l'API
    """
    ip = flask.request.remote_addr
    db = Database()
    db.connect()
    connected_clients = db.execute_query(
        "SELECT ip_address FROM clients", type=Type.LIST
    )
    db.close()
    msg = "Connecté" if ip in connected_clients else "Non connecté"
    return flask.jsonify({"status": "API en cours d'exécution", "message": msg})


@app.route("/disconnect", methods=["GET"])
def disconnect():
    """Endpoint pour se déconnecter de l'API.
    ---
    responses:
      200:
        description: Déconnexion réussie
    """
    client_ip = flask.request.remote_addr
    LOGGER.info(f"Client {client_ip} s'est déconnecté.")
    db = Database()
    db.connect()
    db.execute_query("DELETE FROM clients WHERE ip_address = ?", (client_ip,))
    db.close()
    return flask.jsonify({"message": "Déconnexion réussie", "client_ip": client_ip})


@app.route("/get_task", methods=["GET"])
def get_task():
    """Endpoint pour qu'un client récupère un lot de chunks à traiter.
    ---
    responses:
      200:
        description: Un lot de tâches
      403:
        description: Client non connecté
      404:
        description: Aucune tâche disponible
    """
    client_ip = flask.request.remote_addr
    db = Database()
    db.connect()

    # Trouver l'ID du client
    client_ids = db.execute_query(
        "SELECT id FROM clients WHERE ip_address = ?", (client_ip,), type=Type.LIST
    )
    if not client_ids:
        db.close()
        return flask.jsonify({"error": "Veuillez d'abord appeler /connect"}), 403
    client_id = client_ids[0]

    # Rechargement de la config pour être à jour
    current_config = config.load_config()
    verification_enabled = current_config.get("verification", False)
    batch_size = current_config.get("batch_size", 50)

    if verification_enabled:
        # On cherche des tâches PENDING ou IN_PROGRESS (qui ont < 2 résultats)
        # Mais le client actuel ne doit pas les avoir déjà faites
        query = """
        SELECT t.id, t.x, t.z 
        FROM tasks t
        LEFT JOIN results r ON t.id = r.task_id
        WHERE t.status IN ('PENDING', 'IN_PROGRESS')
        AND t.id NOT IN (SELECT task_id FROM results WHERE client_id = ?)
        GROUP BY t.id
        HAVING COUNT(DISTINCT r.client_id) < 2
        LIMIT ?
        """
        tasks = db.execute_query(query, (client_id, batch_size), type=Type.TUPLE)
    else:
        query = "SELECT id, x, z FROM tasks WHERE status = 'PENDING' LIMIT ?"
        tasks = db.execute_query(query, (batch_size,), type=Type.TUPLE)

    if not tasks:
        db.close()
        return flask.jsonify({"message": "Aucune tâche disponible"}), 404

    task_ids = [t[0] for t in tasks]
    placeholders = ",".join(["?"] * len(task_ids))
    db.execute_query(
        f"UPDATE tasks SET status = 'IN_PROGRESS' WHERE id IN ({placeholders})",
        tuple(task_ids),
    )
    db.close()

    formatted_tasks = [{"task_id": t[0], "x": t[1], "z": t[2]} for t in tasks]

    return flask.jsonify(
        {
            "batch_id": task_ids[0],  # On peut utiliser le premier ID comme repère
            "tasks": formatted_tasks,
            "seed": current_config.get("seed"),
            "shape": current_config.get("shape", "square"),
            "pattern": current_config.get("pattern", "region"),
        }
    )


@app.route("/submit_result", methods=["POST"])
def submit_result():
    """Endpoint pour soumettre les résultats (hashes) d'un lot de chunks.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            results:
              type: array
              items:
                type: object
                properties:
                  task_id:
                    type: integer
                  signature:
                    type: string
    responses:
      200:
        description: Résultats traités
      400:
        description: Données manquantes
      403:
        description: Client non enregistré
    """
    data = flask.request.json
    if not data or "results" not in data:
        return flask.jsonify({"error": "Données manquantes (results)"}), 400

    results_list = data["results"]  # Liste de {"task_id": 1, "signature": "..."}
    client_ip = flask.request.remote_addr

    db = Database()
    db.connect()

    # Trouver l'ID du client
    client_ids = db.execute_query(
        "SELECT id FROM clients WHERE ip_address = ?", (client_ip,), type=Type.LIST
    )
    if not client_ids:
        db.close()
        return flask.jsonify({"error": "Client non enregistré"}), 403
    client_id = client_ids[0]

    current_config = config.load_config()
    verification_enabled = current_config.get("verification", False)

    for res in results_list:
        task_id = res.get("task_id")
        signature = res.get("signature")

        if not task_id or not signature:
            continue

        # Enregistrer le résultat
        db.execute_query(
            "INSERT INTO results (task_id, client_id, signature) VALUES (?, ?, ?)",
            (task_id, client_id, signature),
        )

        all_results = db.execute_query(
            "SELECT signature FROM results WHERE task_id = ?",
            (task_id,),
            type=Type.LIST,
        )

        if verification_enabled:
            if len(all_results) >= 2:
                # On compare les deux dernières signatures (ou les deux premières)
                if all_results[0] == all_results[1]:
                    db.execute_query(
                        "UPDATE tasks SET status = 'VALIDATED' WHERE id = ?", (task_id,)
                    )
                else:
                    db.execute_query(
                        "UPDATE tasks SET status = 'FAILED' WHERE id = ?", (task_id,)
                    )
        else:
            # Sans vérification, le premier résultat valide la tâche
            db.execute_query(
                "UPDATE tasks SET status = 'VALIDATED' WHERE id = ?", (task_id,)
            )

    db.close()
    return flask.jsonify(
        {"message": f"{len(results_list)} résultats traités", "status": "success"}
    )


if __name__ == "__main__":
    asyncio.run(start_api())
