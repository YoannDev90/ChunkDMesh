from enum import Enum

class Endpoints(Enum):
    LOGIN = "login"
    HEALTH = "health"
    MODS = "mods"
    CONFIG = "config"
    TASKS_BATCH = "batch"
    TASKS_SUBMIT = "submit"
    TASKS_UPLOAD = "upload"

class Methods(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"

class EndpointConfig:
    def __init__(self, url: str, method: Methods, headers: dict = None, payload: dict = None):
        self.url = url
        self.method = method
        self.headers = headers or {}
        self.payload = payload or {}

SERVER_URL = "http://localhost:8000"

LOGIN_ENDPOINT = f"{SERVER_URL}/auth/login"
HEALTH_ENDPOINT = f"{SERVER_URL}/health"
ASSETS_ENDPOINT = f"{SERVER_URL}/assets"
MODS_ENDPOINT = f"{ASSETS_ENDPOINT}/mods.zip"
CONFIG_ENDPOINT = f"{ASSETS_ENDPOINT}/config.json"
TASKS_ENDPOINT = f"{SERVER_URL}/tasks"
TASKS_BATCH_ENDPOINT = f"{TASKS_ENDPOINT}/batch"
TASKS_SUBMIT_ENDPOINT = f"{TASKS_ENDPOINT}/submit"
TASKS_UPLOAD_ENDPOINT = f"{TASKS_ENDPOINT}/upload/"


# For each endpoint, define the expected HTTP method(s), and any required parameters or payload structure.

ENDPOINTS = {
    Endpoints.LOGIN: EndpointConfig(LOGIN_ENDPOINT, Methods.POST, payload={"power_score": "float"}),
    Endpoints.HEALTH: EndpointConfig(HEALTH_ENDPOINT, Methods.GET),
    Endpoints.MODS: EndpointConfig(MODS_ENDPOINT, Methods.GET, headers={"Authorization": "Bearer <token>"}),
    Endpoints.CONFIG: EndpointConfig(CONFIG_ENDPOINT, Methods.GET, headers={"Authorization": "Bearer <token>"}),
    Endpoints.TASKS_BATCH: EndpointConfig(TASKS_BATCH_ENDPOINT, Methods.GET, headers={"Authorization": "Bearer <token>"}),
    Endpoints.TASKS_SUBMIT: EndpointConfig(TASKS_SUBMIT_ENDPOINT, Methods.POST, headers={"Authorization": "Bearer <token>"}, payload={"batch_id": "int", "chunk_hashes": "dict"}),
    Endpoints.TASKS_UPLOAD: EndpointConfig(TASKS_UPLOAD_ENDPOINT, Methods.PUT, headers={"Authorization": "Bearer <token>"}, payload={"file": "bytes"})
}

