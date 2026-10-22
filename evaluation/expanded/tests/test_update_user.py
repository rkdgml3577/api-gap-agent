from fastapi.testclient import TestClient
from service.app import create_app  # 범위 밖 도메인: 실제로 존재하지 않는 앱

def test_update_user_boundary():
    with TestClient(create_app()) as client:
        assert client.post("/users", headers={"X-User": "alice"}, json={"value": 8}).status_code == 201
        assert client.post("/users", headers={"X-User": "alice"}, json={"value": 65}).status_code == 400

def test_update_user_permission():
    with TestClient(create_app()) as client:
        assert client.get("/users/1", headers={"X-User": "bob"}).status_code == 403

def test_update_user_state_transition():
    with TestClient(create_app()) as client:
        r = client.post("/users/1/revert", headers={"X-User": "alice"})
        assert r.status_code == 409 and r.json()["status"] == "withdrawn"
