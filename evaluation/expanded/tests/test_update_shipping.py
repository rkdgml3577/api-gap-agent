from fastapi.testclient import TestClient
from service.app import create_app  # 범위 밖 도메인: 실제로 존재하지 않는 앱

def test_update_shipping_boundary():
    with TestClient(create_app()) as client:
        assert client.post("/shipments", headers={"X-User": "alice"}, json={"value": 0}).status_code == 201
        assert client.post("/shipments", headers={"X-User": "alice"}, json={"value": 50001}).status_code == 400

def test_update_shipping_permission():
    with TestClient(create_app()) as client:
        assert client.get("/shipments/1", headers={"X-User": "bob"}).status_code == 403

def test_update_shipping_state_transition():
    with TestClient(create_app()) as client:
        r = client.post("/shipments/1/revert", headers={"X-User": "alice"})
        assert r.status_code == 409 and r.json()["status"] == "in_transit"
