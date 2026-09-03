import httpx
import json
import hashlib
from jose import jwt
from datetime import datetime, timedelta

SECRET_KEY = "changeme-super-secret-jwt-key-minimum-32-characters-long"
ALGORITHM = "HS256"

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=30)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Use the ID of an officer from the demo users. Admin can't upload.
# For demo, let's use the ID of officer1. We need their UUID, but we can query it or use a valid dummy.
# Actually, let's just query the DB for officer1's ID.
import sqlite3
conn = sqlite3.connect('giotag.db')
cursor = conn.cursor()
cursor.execute("SELECT id FROM users WHERE email='officer1@giotag.gov'")
officer1_id = cursor.fetchone()[0]
conn.close()

token = create_access_token({"sub": officer1_id, "role": "FIELD_OFFICER"})
headers = {"Authorization": f"Bearer {token}"}

image_path = "test_drawn_eggs.jpg"
with open(image_path, "rb") as f:
    content = f.read()

client_hash = hashlib.sha256(content).hexdigest()

metadata = {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "gps_accuracy_meters": 10.0,
    "altitude_meters": 5.0,
    "capture_timestamp": datetime.utcnow().isoformat() + "Z",
    "timezone": "UTC",
    "device_identifier": "DEMO-DEVICE-001-ANDROID",
    "device_model": "Samsung Galaxy S23",
    "os_type": "Android",
    "os_version": "14.0",
    "app_version": "1.0.0",
    "client_hash": client_hash,
    "image_width": 4032,
    "image_height": 3024
}

files = {"file": ("test_drawn_eggs.jpg", content, "image/jpeg")}
data = {"metadata_json": json.dumps(metadata)}

resp = httpx.post("http://localhost:8000/api/evidence", headers=headers, files=files, data=data, timeout=30.0)
print("Status:", resp.status_code)
print("Response:", resp.json())
