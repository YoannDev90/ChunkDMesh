import httpx
from utils import ResourceReportFormat, get_available_resources_averaged

SERVER_URL = "http://localhost:8000"

def connect_to_server(power_score: float):
    try:
        response = httpx.post(f"{SERVER_URL}/auth/login", json={"power_score": power_score})
        if response.status_code == 200:
            print("Connected to server successfully!")
            return True
        else:
            print(f"Failed to connect to server. Status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error connecting to server: {e}")
        return False



if __name__ == "__main__":
    power_score = get_available_resources_averaged(print_output=False, return_format=ResourceReportFormat.VALUE)
    print(f"Calculated power score: {power_score:.2f}")
    connect_to_server(power_score)
