from fastapi.testclient import TestClient
from sample_service.app import create_app

def test_create_order():
    with TestClient(create_app()) as client:
        response = client.post("/orders", headers={"X-User": "alice"}, json={"quantity": 2})
        assert response.status_code == 201
        assert response.json()["quantity"] == 2

def test_get_own_order():
    with TestClient(create_app()) as client:
        response = client.get("/orders/1", headers={"X-User": "alice"})
        assert response.status_code == 200
        assert response.json()["owner"] == "alice"

def test_cancel_pending_order():
    with TestClient(create_app()) as client:
        response = client.post("/orders/1/cancel", headers={"X-User": "alice"})
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
