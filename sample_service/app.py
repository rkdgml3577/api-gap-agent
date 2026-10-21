from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

class OrderInput(BaseModel):
    quantity: int


def create_app(variant: str = "healthy"):
    """Each instance has fresh data. buggy intentionally violates the cancellation rule."""
    app = FastAPI(title="Order QA fixture")
    orders = {
        1: {"id": 1, "owner": "alice", "status": "pending", "quantity": 2},
        2: {"id": 2, "owner": "alice", "status": "shipping", "quantity": 2},
    }
    def user(value):
        if value not in ("alice", "bob"):
            raise HTTPException(401, "unknown user")
        return value
    def owned(order_id, name):
        if order_id not in orders:
            raise HTTPException(404)
        order = orders[order_id]
        if order["owner"] != user(name):
            raise HTTPException(403, "not your order")
        return order

    @app.post("/orders", status_code=201, operation_id="create_order")
    def create_order(body: OrderInput, x_user: str = Header()):
        name = user(x_user)
        if not 1 <= body.quantity <= 100:
            raise HTTPException(400, "quantity must be 1..100")
        key = max(orders) + 1
        orders[key] = {"id": key, "owner": name, "quantity": body.quantity, "status": "pending"}
        return orders[key]

    @app.get("/orders/{order_id}", operation_id="get_order")
    def get_order(order_id: int, x_user: str = Header()):
        return owned(order_id, x_user)

    @app.post("/orders/{order_id}/cancel", operation_id="cancel_order")
    def cancel_order(order_id: int, x_user: str = Header()):
        order = owned(order_id, x_user)
        if order["status"] == "shipping" and variant != "buggy":
            raise HTTPException(409, "already shipping")
        order["status"] = "cancelled"
        return order

    return app
