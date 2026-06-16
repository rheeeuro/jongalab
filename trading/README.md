# trading — Auto-Trading Execution Server

자동매매 집행 전용 서버 (FastAPI, localhost :8002) + 독립 대시보드(`frontend/`, :3001).

이 도메인만 **주문 권한**을 가진다. 시세·수급은 kiwoom 데이터 서버(:8001)에서 읽고,
**주문/계좌는 kiwoom REST(`/api/dostk/ordr`, `/api/dostk/acnt`)로 직접 호출**한다
(kiwoom 데이터 서버는 읽기 전용 불변식 유지). 토큰은 `kiwoom` DB 의 공유 토큰을
**읽기 전용**으로 사용한다(발급/갱신은 kiwoom 워커 담당).

## 경계
- `jongalab`(closing_bet) 가 **무엇을 살지** 결정 → `trade_signal` 테이블 적재
- `trading` 이 **언제·얼마나·어떻게 집행**하고 포지션/리스크 관리

## 안전장치 (집행 전 필수)
- `TRADING_MODE=paper` 기본 (모의·미전송). 실주문은 `live` 명시 필요.
- 글로벌 킬스위치: env(`TRADING_KILL_SWITCH=1`) + DB `kill_switch` 플래그
- 하드 한도/서킷브레이커, 주문 멱등성 키, 불변 감사로그 (구현 예정)

## 기동
```
uv run uvicorn api:app --host 127.0.0.1 --port 8002   # 백엔드 API
cd frontend && npm run dev                             # 대시보드(:3001)
```

## 첫 구현 범위
**종가베팅 집행만** — 매수 집행(signal_executor) + 종가베팅 사이클 청산(settle) + 정합성(reconcile).
장중 상시 손절 감시(position_monitor)·멀티 전략은 다음 단계.
