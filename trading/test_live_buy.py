"""실계좌 1주 실거래 테스트 — NXT 주문 수락 여부 검증용 (1회성 수동 스크립트).

⚠️ 안전장치: 실제 전송은 'TRADING_MODE=live' 이고 동시에 '--go' 플래그가 있을 때만.
   그 외(paper 이거나 --go 없음)는 미전송 드라이런.

사용:
  uv run python test_live_buy.py --stk 082640                 # 드라이런(미전송)
  uv run python test_live_buy.py --stk 082640 --go            # 실제 1주 매수(live일 때)
  옵션: --qty(기본1) --exchange(기본 NXT) --price(기본 현재가)
"""
import argparse
import time
from datetime import datetime

from core.kiwoom_order_client import KiwoomOrderClient
from core.kiwoom_data_client import KiwoomDataClient, to_int


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stk", required=True, help="종목코드 6자리")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--exchange", default="NXT", help="KRX | NXT | SOR")
    ap.add_argument("--price", type=int, default=0, help="지정가(미지정 시 현재가)")
    ap.add_argument("--go", action="store_true", help="실제 전송(live + 이 플래그 동시 필요)")
    a = ap.parse_args()

    oc = KiwoomOrderClient()
    dc = KiwoomDataClient()
    price = a.price or dc.get_current_price(a.stk)
    if price <= 0:
        print(f"현재가 조회 실패 [{a.stk}] — 중단")
        return 1
    cost = price * a.qty

    print(f"[{datetime.now():%H:%M:%S}] 모드={'LIVE' if not oc.paper else 'paper'} 도메인={oc.base_url}")
    print(f"테스트 매수: {a.stk} {a.qty}주 @ {price:,}원 (예상 {cost:,}원) "
          f"거래소={a.exchange} 보통지정가(trde_tp=0)")

    if oc.paper:
        oc.buy(a.stk, a.qty, price, trde_tp="0", dmst_stex_tp=a.exchange)  # paper echo(미전송)
        print("→ paper: 미전송. 실제 테스트는 .env TRADING_MODE=live 후 --go 로 실행하세요.")
        return 0
    if not a.go:
        print("→ live 이지만 --go 없음: 미전송. 실제 보내려면 --go 추가.")
        return 0

    print("→ 실제 전송합니다...")
    resp = oc.buy(a.stk, a.qty, price, trde_tp="0", dmst_stex_tp=a.exchange)
    rc = resp.get("return_code")
    ono = resp.get("ord_no")
    print(f"응답: return_code={rc} | msg={resp.get('return_msg')} | ord_no={ono}")
    if rc == 0 and ono:
        print("✅ 주문 수락됨. 체결 확인 중...")
        time.sleep(1.5)
        ex = oc.get_executions(qry_tp="1", sell_tp="0", stk_cd=a.stk, stex_tp="0")
        mine = [c for c in (ex.get("cntr") or []) if c.get("ord_no") == ono]
        for c in mine:
            print(f"  체결: 체결량={to_int(c.get('cntr_qty'))} 미체결={to_int(c.get('oso_qty'))} "
                  f"체결가={to_int(c.get('cntr_pric'))}")
        if not mine or all(to_int(c.get("oso_qty")) > 0 for c in mine):
            print(f"  미체결 잔량 있음 → 취소: uv run python -c \"from core.kiwoom_order_client import KiwoomOrderClient as K; "
                  f"print(K().cancel('{ono}','{a.stk}'))\"")
    else:
        print("❌ 주문 거부/오류 — return_msg 확인 (NXT 시간외 주문구분 문제일 수 있음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
