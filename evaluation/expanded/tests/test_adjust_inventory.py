from fastapi.testclient import TestClient
from service.app import create_app  # 범위 밖 도메인: 실제로 존재하지 않는 앱

def test_adjust_inventory_boundary():
    with TestClient(create_app()) as client:
        assert client.post("/inventory", headers={"X-User": "alice"}, json={"value": 0}).status_code == 201
        assert client.post("/inventory", headers={"X-User": "alice"}, json={"value": 10000}).status_code == 400

def test_adjust_inventory_permission():
    with TestClient(create_app()) as client:
        assert client.get("/inventory/1", headers={"X-User": "bob"}).status_code == 403

def test_adjust_inventory_state_transition():
    with TestClient(create_app()) as client:
        r = client.post("/inventory/1/revert", headers={"X-User": "alice"})
        assert r.status_code == 409 and r.json()["status"] == "out_of_stock"
