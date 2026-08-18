import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), ".env")))
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from app.database.models import User, RoleEnum
from app.security.rbac import get_current_user

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def ensure_test_images():
    """Ensure test images exist before running test."""
    eggs_path = os.path.join(BASE_DIR, "test_drawn_eggs.jpg")
    trays_path = os.path.join(BASE_DIR, "test_drawn_trays.jpg")
    hens_path = os.path.join(BASE_DIR, "test_drawn_hens.jpg")
    
    if not os.path.exists(eggs_path) or not os.path.exists(trays_path) or not os.path.exists(hens_path):
        from generate_test_drawings import create_drawn_eggs, create_drawn_trays, create_drawn_hens
        if not os.path.exists(eggs_path):
            create_drawn_eggs()
        if not os.path.exists(trays_path):
            create_drawn_trays()
        if not os.path.exists(hens_path):
            create_drawn_hens()
            
    return eggs_path, trays_path, hens_path

def test_endpoint():
    eggs_path, trays_path, hens_path = ensure_test_images()

    app.dependency_overrides[get_current_user] = lambda: User(
        id="test-user-id",
        email="admin@giotag.com",
        username="admin",
        full_name="Admin User",
        role=RoleEnum.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    client = TestClient(app)
    try:
        with open(eggs_path, "rb") as f:
            resp = client.post(
                "/api/ai/analyze-egg-image",
                files={"image": ("test_drawn_eggs.jpg", f, "image/jpeg")},
                data={"target": "eggs"}
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        print("Eggs test status:", resp.status_code)
        print("Eggs test response:", resp.json())
        
        with open(trays_path, "rb") as f:
            resp = client.post(
                "/api/ai/analyze-egg-image",
                files={"image": ("test_drawn_trays.jpg", f, "image/jpeg")},
                data={"target": "trays"}
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        print("Trays test status:", resp.status_code)
        print("Trays test response:", resp.json())

        with open(hens_path, "rb") as f:
            resp = client.post(
                "/api/ai/analyze-egg-image",
                files={"image": ("test_drawn_hens.jpg", f, "image/jpeg")},
                data={"target": "hens"}
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        print("Hens test status:", resp.status_code)
        print("Hens test response:", resp.json())
        
        with open(trays_path, "rb") as f1, open(trays_path, "rb") as f2:
            resp = client.post(
                "/api/ai/analyze-dual-egg-images",
                files={
                    "top_image": ("top.jpg", f1, "image/jpeg"),
                    "side_image": ("side.jpg", f2, "image/jpeg")
                },
                data={"target": "trays"}
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        print("Dual Trays test status:", resp.status_code)
        print("Dual Trays test response:", resp.json())
    finally:
        app.dependency_overrides.clear()

if __name__ == "__main__":
    test_endpoint()
