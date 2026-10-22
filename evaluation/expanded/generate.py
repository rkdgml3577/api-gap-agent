"""Generate an expanded corpus so retrieval (RAG) becomes meaningful.

The in-scope targets stay ORDER-001/002/003 (the executable "needles"). Around
them we add many plausible-but-out-of-scope rules and test files for other
domains (the "haystack"). The distractors deliberately mirror the real rules'
shape — quantity boundaries, ownership permissions, state transitions — so a
naive keyword match cannot separate them from the ORDER rules. That is exactly
what makes "put the whole corpus in context" vs "retrieve top-k" a fair fight.

Deterministic: same output every run. Nothing here is executed by pytest; the
distractor tests target endpoints that do not exist and live outside
sample_service/tests, so they only ever serve as corpus text to investigate.

    python evaluation/expanded/generate.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (code, domain-ko, operation, resource-path, boundary low/high, owner-role, states)
DOMAINS = [
    ("PAY", "결제", "create_payment", "/payments", 100, 1000000, "결제자", ("pending", "captured")),
    ("INV", "재고", "adjust_inventory", "/inventory", 0, 9999, "관리자", ("in_stock", "out_of_stock")),
    ("CPN", "쿠폰", "issue_coupon", "/coupons", 1, 90, "발급자", ("active", "expired")),
    ("SHP", "배송", "update_shipping", "/shipments", 0, 50000, "주문자", ("ready", "in_transit")),
    ("USR", "회원", "update_user", "/users", 8, 64, "본인", ("active", "withdrawn")),
    ("RVW", "리뷰", "create_review", "/reviews", 1, 5, "작성자", ("visible", "hidden")),
    ("CRT", "장바구니", "add_cart_item", "/cart", 1, 99, "본인", ("open", "ordered")),
    ("RFD", "환불", "request_refund", "/refunds", 100, 1000000, "구매자", ("requested", "approved")),
    ("PNT", "포인트", "use_point", "/points", 1, 500000, "회원", ("held", "spent")),
    ("ADR", "배송지", "update_address", "/addresses", 1, 20, "본인", ("default", "archived")),
    ("WSH", "위시리스트", "add_wishlist", "/wishlist", 1, 200, "본인", ("saved", "removed")),
    ("SLR", "판매자", "update_seller", "/sellers", 1, 100, "판매자", ("open", "suspended")),
]


def rules_markdown():
    out = ["# 확장 코퍼스 — 범위 밖 distractor 업무 규칙", "",
           "아래 규칙들은 주문(order) 조사 범위와 무관한 다른 도메인의 규칙이다.", ""]
    for code, ko, op, path, lo, hi, owner, (s0, s1) in DOMAINS:
        out += [
            f"## {code}-001 — 수량/금액 경계값 / {op}",
            f"{ko} 값은 정수 {lo}~{hi}(양 끝 포함)이다. {lo-1 if lo>0 else lo}과 {hi+1}은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.",
            "",
            f"## {code}-002 — 조회/변경 권한 / {op}",
            f"{ko} 자원은 {owner}만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.",
            "",
            f"## {code}-003 — 상태 전이 / {op}",
            f"{s1} 상태의 {ko} 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 {s1}을 유지한다.",
            "",
        ]
    return "\n".join(out)


def distractor_test(code, ko, op, path, lo, hi, owner, states):
    s1 = states[1]
    return f'''from fastapi.testclient import TestClient
from service.app import create_app  # 범위 밖 도메인: 실제로 존재하지 않는 앱

def test_{op}_boundary():
    with TestClient(create_app()) as client:
        assert client.post("{path}", headers={{"X-User": "alice"}}, json={{"value": {lo}}}).status_code == 201
        assert client.post("{path}", headers={{"X-User": "alice"}}, json={{"value": {hi+1}}}).status_code == 400

def test_{op}_permission():
    with TestClient(create_app()) as client:
        assert client.get("{path}/1", headers={{"X-User": "bob"}}).status_code == 403

def test_{op}_state_transition():
    with TestClient(create_app()) as client:
        r = client.post("{path}/1/revert", headers={{"X-User": "alice"}})
        assert r.status_code == 409 and r.json()["status"] == "{s1}"
'''


def main():
    (HERE / "rules").mkdir(parents=True, exist_ok=True)
    (HERE / "tests").mkdir(parents=True, exist_ok=True)
    (HERE / "rules" / "distractor_rules.md").write_text(rules_markdown())
    for code, ko, op, path, lo, hi, owner, states in DOMAINS:
        (HERE / "tests" / f"test_{op}.py").write_text(
            distractor_test(code, ko, op, path, lo, hi, owner, states))
    # Size report
    corpus = (HERE / "rules" / "distractor_rules.md").read_text()
    for p in sorted((HERE / "tests").glob("*.py")):
        corpus += p.read_text()
    print(f"distractor rules: {len(DOMAINS)*3} across {len(DOMAINS)} domains")
    print(f"distractor test files: {len(DOMAINS)}")
    print(f"distractor corpus: ~{len(corpus)} chars ≈ {len(corpus)//3} tokens")


if __name__ == "__main__":
    main()
