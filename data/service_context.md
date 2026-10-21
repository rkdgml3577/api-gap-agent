# 테스트 환경
각 테스트는 초기화된 별도 앱을 사용한다.
헤더 X-User로 alice 또는 bob을 지정한다.
주문 1: 소유자 alice, 상태 pending, 수량 2.
주문 2: 소유자 alice, 상태 shipping, 수량 2.
healthy와 buggy는 동일한 명세·규칙·기존 테스트를 사용한다.
covered는 모든 업무 규칙에 대한 기존 테스트가 있는 평가 구성이다.
