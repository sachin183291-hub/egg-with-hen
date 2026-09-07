import requests
import json
import uuid

url = "http://localhost:8000"

# Register a test user
unique = str(uuid.uuid4())[:8]
email = f"test_{unique}@test.com"
reg_data = {
    "email": email,
    "username": f"user_{unique}",
    "full_name": "Test User",
    "password": "Password123",
    "role": "FIELD_OFFICER"
}
reg_resp = requests.post(f"{url}/api/auth/register", json=reg_data)
print("Register:", reg_resp.status_code)

login_resp = requests.post(f"{url}/api/auth/login", json={"email": email, "password": "Password123"})
if login_resp.status_code != 200:
    print("Login failed:", login_resp.text)
    exit(1)
    
token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

metadata = {
    "latitude": 13.0,
    "longitude": 80.0,
    "capture_timestamp": "2024-05-10T12:00:00Z",
    "device_identifier": "WEB-DASHBOARD",
    "client_hash": "dummyhash"
}

with open("test.jpg", "wb") as f:
    f.write(b"fake image data")

with open("test.jpg", "rb") as f:
    files = {"file": ("test.jpg", f, "image/jpeg")}
    data = {"metadata_json": json.dumps(metadata)}
    
    resp = requests.post(f"{url}/api/evidence", files=files, data=data, headers=headers)
    print("Upload:", resp.status_code)
    print(resp.text)
