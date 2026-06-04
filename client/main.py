import httpx
from utils import ResourceReportFormat, get_available_resources_averaged
from api_config import EndpointConfig, ENDPOINTS, Endpoints

def send_request(endpoint: EndpointConfig, payload=None, headers=None):    
    method = endpoint.method.value
    url = endpoint.url
    headers = headers or endpoint.headers
    payload = payload or endpoint.payload

    with httpx.Client() as client:
        if method == "GET":
            response = client.get(url, headers=headers)
        elif method == "POST":
            response = client.post(url, json=payload, headers=headers)
        elif method == "PUT":
            response = client.put(url, json=payload, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    return response
    

if __name__ == "__main__":
    power_score = get_available_resources_averaged(print_output=False, return_format=ResourceReportFormat.VALUE)
    print(f"Calculated power score: {power_score:.2f}")
    send_request(ENDPOINTS[Endpoints.LOGIN], payload={"power_score": power_score})
