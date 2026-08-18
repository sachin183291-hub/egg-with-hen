import httpx
from jose import jwt
from datetime import datetime, timedelta

SECRET_KEY = "changeme-super-secret-jwt-key-minimum-32-characters-long"
ALGORITHM = "HS256"

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=30)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

token = create_access_token({"sub": "09aabfb5-ed43-4de4-8d07-8470aa8549e4", "role": "SUPER_ADMIN"})

headers = {"Authorization": f"Bearer {token}"}

try:
    with open("test_eggs_synthetic.jpg", "rb") as f:
        files = {"image": ("test_eggs_synthetic.jpg", f, "image/jpeg")}
        data = {"target": "eggs"}
        resp = httpx.post("http://localhost:8000/api/ai/analyze-egg-image", headers=headers, files=files, data=data, timeout=30.0)
        print("analyze-egg-image:", resp.status_code, resp.text)
except Exception as e:
    print("Error:", e)
