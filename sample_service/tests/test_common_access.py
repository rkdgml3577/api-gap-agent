from fastapi.testclient import TestClient
from sample_service.app import create_app

def test_order_access_isolation():
    with TestClient(create_app()) as client:
        response = client.get("/orders/1", headers={"X-User": "bob"})
        assert response.status_code == 403
