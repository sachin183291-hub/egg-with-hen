import requests
import json
import os

url = "http://localhost:8000/api/evidence"
metadata = {
    "latitude": 13.0,
    "longitude": 80.0,
    "capture_timestamp": "2024-05-10T12:00:00Z",
    "device_identifier": "WEB-DASHBOARD",
    "client_hash": "dummyhash"
}

# create dummy image
with open("test.jpg", "wb") as f:
    f.write(b"fake image data")

with open("test.jpg", "rb") as f:
    files = {"file": ("test.jpg", f, "image/jpeg")}
    data = {"metadata_json": json.dumps(metadata)}
    # need auth token!
    # Let's just login first to get the token
    login_resp = requests.post("http://localhost:8000/api/auth/login", json={"email": "admin@giotag.com", "password": "Password123"})
    if login_resp.status_code != 200:
        print("Login failed:", login_resp.text)
        exit(1)
        
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    resp = requests.post(url, files=files, data=data, headers=headers)
    print(resp.status_code)
    print(resp.text)
