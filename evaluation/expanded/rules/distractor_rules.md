# 확장 코퍼스 — 범위 밖 distractor 업무 규칙

아래 규칙들은 주문(order) 조사 범위와 무관한 다른 도메인의 규칙이다.

## PAY-001 — 수량/금액 경계값 / create_payment
결제 값은 정수 100~1000000(양 끝 포함)이다. 99과 1000001은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## PAY-002 — 조회/변경 권한 / create_payment
결제 자원은 결제자만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## PAY-003 — 상태 전이 / create_payment
captured 상태의 결제 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 captured을 유지한다.

## INV-001 — 수량/금액 경계값 / adjust_inventory
재고 값은 정수 0~9999(양 끝 포함)이다. 0과 10000은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## INV-002 — 조회/변경 권한 / adjust_inventory
재고 자원은 관리자만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## INV-003 — 상태 전이 / adjust_inventory
out_of_stock 상태의 재고 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 out_of_stock을 유지한다.

## CPN-001 — 수량/금액 경계값 / issue_coupon
쿠폰 값은 정수 1~90(양 끝 포함)이다. 0과 91은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## CPN-002 — 조회/변경 권한 / issue_coupon
쿠폰 자원은 발급자만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## CPN-003 — 상태 전이 / issue_coupon
expired 상태의 쿠폰 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 expired을 유지한다.

## SHP-001 — 수량/금액 경계값 / update_shipping
배송 값은 정수 0~50000(양 끝 포함)이다. 0과 50001은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## SHP-002 — 조회/변경 권한 / update_shipping
배송 자원은 주문자만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## SHP-003 — 상태 전이 / update_shipping
in_transit 상태의 배송 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 in_transit을 유지한다.

## USR-001 — 수량/금액 경계값 / update_user
회원 값은 정수 8~64(양 끝 포함)이다. 7과 65은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## USR-002 — 조회/변경 권한 / update_user
회원 자원은 본인만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## USR-003 — 상태 전이 / update_user
withdrawn 상태의 회원 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 withdrawn을 유지한다.

## RVW-001 — 수량/금액 경계값 / create_review
리뷰 값은 정수 1~5(양 끝 포함)이다. 0과 6은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## RVW-002 — 조회/변경 권한 / create_review
리뷰 자원은 작성자만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## RVW-003 — 상태 전이 / create_review
hidden 상태의 리뷰 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 hidden을 유지한다.

## CRT-001 — 수량/금액 경계값 / add_cart_item
장바구니 값은 정수 1~99(양 끝 포함)이다. 0과 100은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## CRT-002 — 조회/변경 권한 / add_cart_item
장바구니 자원은 본인만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## CRT-003 — 상태 전이 / add_cart_item
ordered 상태의 장바구니 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 ordered을 유지한다.

## RFD-001 — 수량/금액 경계값 / request_refund
환불 값은 정수 100~1000000(양 끝 포함)이다. 99과 1000001은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## RFD-002 — 조회/변경 권한 / request_refund
환불 자원은 구매자만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## RFD-003 — 상태 전이 / request_refund
approved 상태의 환불 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 approved을 유지한다.

## PNT-001 — 수량/금액 경계값 / use_point
포인트 값은 정수 1~500000(양 끝 포함)이다. 0과 500001은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## PNT-002 — 조회/변경 권한 / use_point
포인트 자원은 회원만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## PNT-003 — 상태 전이 / use_point
spent 상태의 포인트 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 spent을 유지한다.

## ADR-001 — 수량/금액 경계값 / update_address
배송지 값은 정수 1~20(양 끝 포함)이다. 0과 21은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## ADR-002 — 조회/변경 권한 / update_address
배송지 자원은 본인만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## ADR-003 — 상태 전이 / update_address
archived 상태의 배송지 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 archived을 유지한다.

## WSH-001 — 수량/금액 경계값 / add_wishlist
위시리스트 값은 정수 1~200(양 끝 포함)이다. 0과 201은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## WSH-002 — 조회/변경 권한 / add_wishlist
위시리스트 자원은 본인만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## WSH-003 — 상태 전이 / add_wishlist
removed 상태의 위시리스트 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 removed을 유지한다.

## SLR-001 — 수량/금액 경계값 / update_seller
판매자 값은 정수 1~100(양 끝 포함)이다. 0과 101은 HTTP 400으로 거절한다. 양 끝 경계를 모두 검증해야 한다.

## SLR-002 — 조회/변경 권한 / update_seller
판매자 자원은 판매자만 변경할 수 있다. 다른 사용자의 접근은 HTTP 403으로 거절한다.

## SLR-003 — 상태 전이 / update_seller
suspended 상태의 판매자 자원에 대한 되돌리기는 HTTP 409로 거절하고 상태는 suspended을 유지한다.
