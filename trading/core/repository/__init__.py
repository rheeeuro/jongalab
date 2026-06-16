"""trading repository — DB 접근 계층.

라우터/워커/엔진에서 raw SQL 직접 작성 금지. 모든 DB 접근은 이 패키지의 모듈을 경유한다.
서브모듈 import 형태로 사용한다: `from core.repository import order as order_repo`.

- kiwoom_token : 키움 공유 토큰 조회 (읽기 전용, kiwoom DB)
- trade_signal : jongalab 이 넘긴 매수 시그널 큐
- order        : 주문 의도/전송 기록
- fill         : 체결 기록
- position     : 보유 포지션 상태
- risk_state   : 일일 한도·서킷브레이커·킬스위치 상태
- audit_log    : 모든 주문 의도 + 키움 응답 원문 (불변 감사로그)
"""
