import httpx
import psutil
import math

SERVER_URL = "http://localhost:8000"

def connect_to_server():
    try:
        cpu_cores = math.ceil(psutil.cpu_count(logical=False) * 0.8)
        ram_gb = math.ceil(psutil.virtual_memory().total / (1024 ** 3) * 0.8)
    except Exception as e:
        print(f"Error retrieving system info: {e}")
    try:
        response = httpx.post(f"{SERVER_URL}/auth/login", json={"cpu_cores": cpu_cores, "ram_gb": ram_gb}, timeout=10)
        response.raise_for_status()
        print("Connected to server successfully!")
        print("Server response:", response.json())
    except httpx.HTTPError as e:
        print(f"Failed to connect to server: {e}")


if __name__ == "__main__":
    connect_to_server()