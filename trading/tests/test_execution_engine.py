"""ExecutionEngine 자금 경로 테스트.

가장 중요한 불변식:
  - 멱등키 중복이면 절대 주문을 전송하지 않는다(cron 재실행 안전).
  - 수량 0 / 리스크 차단이면 전송하지 않는다.
  - paper 모드는 즉시 체결로 시뮬레이션(fill·position·실현손익 기록).
순수 헬퍼(idempotency_key / _now_trde_tp / 증거금 거부 파싱)도 고정한다.
"""
from core.execution_engine import ExecutionEngine


# ── 순수 헬퍼 ──────────────────────────────────────────────────

def test_idempotency_key_format():
    assert ExecutionEngine.idempotency_key("20260626", 42, "buy") == "20260626:42:buy"


def test_now_trde_tp_routing():
    # NXT 는 시장가 미지원 → 최유리지정가 IOC(16), 그 외는 시장가(3)
    assert ExecutionEngine._now_trde_tp("NXT") == "16"
    assert ExecutionEngine._now_trde_tp("KRX") == "3"
    assert ExecutionEngine._now_trde_tp("SOR") == "3"


def test_afford_qty_parses_margin_reject():
    resp = {"return_msg": "[2000](855056:매수증거금이 부족합니다. 2주 매수가능)"}
    assert ExecutionEngine._afford_qty_on_margin_reject(resp) == 2


def test_afford_qty_zero_when_not_margin_message():
    assert ExecutionEngine._afford_qty_on_margin_reject({"return_msg": "장시간 아님"}) == 0


def test_afford_qty_zero_when_margin_but_no_quantity():
    assert ExecutionEngine._afford_qty_on_margin_reject({"return_msg": "증거금이 부족합니다"}) == 0


def test_afford_qty_handles_missing_message():
    assert ExecutionEngine._afford_qty_on_margin_reject({}) == 0


# ── execute_buy (paper) ────────────────────────────────────────

def _signal(qty=10, price=10000, sid=1, stk="005930"):
    return {"id": sid, "stk_cd": stk, "_qty": qty, "_price": price}


def test_buy_skips_on_duplicate_idempotency_key(engine):
    eng, client, risk, data, rec = engine
    rec.find_result = {"id": 99}  # 이미 전송된 주문 존재
    out = eng.execute_buy("20260626", _signal(), "NXT")
    assert out is None
    assert client.buys == []           # 주문 전송 안 됨
    assert risk.checks == []           # 리스크 검사도 안 감(조기 반환)


def test_buy_paper_executes_and_simulates_fill(engine):
    eng, client, risk, data, rec = engine
    out = eng.execute_buy("20260626", _signal(qty=10, price=10000), "NXT")
    assert out is not None
    assert len(client.buys) == 1
    assert client.buys[0]["dmst_stex_tp"] == "NXT"
    assert client.buys[0]["trde_tp"] == "16"          # NXT IOC
    # paper 즉시체결: mark_sent=filled, fill·position 기록
    assert rec.sent[0][2] == "filled"
    assert len(rec.fills) == 1
    assert len(rec.buys_applied) == 1
    assert risk.orders_recorded == 1                  # 일일 주문수 카운트
    assert "buy_filled_paper" in rec.event_types


def test_buy_skips_when_quantity_zero(engine):
    eng, client, risk, data, rec = engine
    out = eng.execute_buy("20260626", _signal(qty=0, price=10000), "KRX")
    assert out is None
    assert client.buys == []
    assert "buy_skipped" in rec.event_types


def test_buy_blocked_by_risk_does_not_send(monkeypatch, repo_rec):
    from tests.conftest import FakeOrderClient, FakeRisk, FakeData
    client = FakeOrderClient(paper=True)
    risk = FakeRisk(allowed=False, reason="kill_switch ON")
    eng = ExecutionEngine(client=client, risk=risk, data=FakeData())
    out = eng.execute_buy("20260626", _signal(), "KRX")
    assert out is None
    assert client.buys == []
    assert "buy_blocked" in repo_rec.event_types
    assert risk.orders_recorded == 0


def test_buy_krx_uses_market_order_type(engine):
    eng, client, risk, data, rec = engine
    eng.execute_buy("20260626", _signal(), "KRX")
    assert client.buys[0]["trde_tp"] == "3"           # KRX 시장가


# ── execute_buy: live 주문가능금액 보정 ─────────────────────────

def _live_engine(monkeypatch, repo_rec, deposit):
    """live 모드(paper=False) 엔진 — 주문가능액 보정 경로 검증용."""
    from tests.conftest import FakeOrderClient, FakeRisk, FakeData
    client = FakeOrderClient(paper=False, deposit=deposit,
                             buy_resp={"return_code": 0, "return_msg": "ok", "ord_no": "B1"})
    eng = ExecutionEngine(client=client, risk=FakeRisk(), data=FakeData())
    return eng, client


def test_buy_clamps_qty_to_live_orderable_cash(monkeypatch, repo_rec):
    # 배분은 10주(@10,000=100,000) 의도하지만 주문가능액은 35,000 → 3주로 축소 발사.
    eng, client = _live_engine(monkeypatch, repo_rec, deposit="35000")
    out = eng.execute_buy("20260626", _signal(qty=10, price=10000), "NXT")
    assert out is not None
    assert client.buys[0]["qty"] == 3                 # 35000 // 10000
    # create_intended(key, sid, stk, "buy", qty, price, "market", mode) → args[4]=qty
    assert repo_rec.intended[-1][0][4] == 3           # 의도 기록도 축소 수량


def test_buy_skips_when_orderable_cash_below_one_share(monkeypatch, repo_rec):
    # 주문가능액이 1주 가격에도 못 미치면 broker 거부 대신 깔끔히 스킵.
    eng, client = _live_engine(monkeypatch, repo_rec, deposit="9000")
    out = eng.execute_buy("20260626", _signal(qty=1, price=10000), "NXT")
    assert out is None
    assert client.buys == []                          # 전송 자체를 안 함
    assert "buy_skipped" in repo_rec.event_types


def test_buy_keeps_qty_when_orderable_cash_sufficient(monkeypatch, repo_rec):
    # 주문가능액이 충분하면 보정 없이 배분 수량 그대로 발사.
    eng, client = _live_engine(monkeypatch, repo_rec, deposit="10000000")
    out = eng.execute_buy("20260626", _signal(qty=10, price=10000), "NXT")
    assert out is not None
    assert client.buys[0]["qty"] == 10


# ── size_order fallback (사전 배분 없을 때 단일 종목 사이징) ──────

def test_size_order_fallback_uses_deposit_and_caps(engine):
    eng, client, risk, data, rec = engine
    # _qty/_price 미주입 → 가용현금 // MAX_POSITIONS, 종목당 캡 적용
    qty, price = eng.size_order({"stk_cd": "005930"})
    # deposit 1천만 // 5슬롯 = 200만, 현재가 1만 → 200주
    assert price == 10000
    assert qty == 200


def test_size_order_uses_injected_allocation(engine):
    eng, *_ = engine
    qty, price = eng.size_order({"stk_cd": "X", "_qty": 7, "_price": 33000})
    assert (qty, price) == (7, 33000)


# ── execute_sell ───────────────────────────────────────────────

def test_sell_skips_on_duplicate_tag_key(engine):
    eng, client, risk, data, rec = engine
    rec.find_result = {"id": 7}
    out = eng.execute_sell("20260626", "005930", 5, 10000, "NXT", tag="nxt")
    assert out is None
    assert client.sells == []


def test_sell_paper_records_realized_pnl(engine):
    eng, client, risk, data, rec = engine
    rec.realized_value = 12345
    out = eng.execute_sell("20260626", "005930", 5, 11000, "KRX", tag="krx")
    assert out is not None
    assert len(client.sells) == 1
    assert rec.sent[0][2] == "filled"
    assert len(rec.sells_applied) == 1
    assert rec.realized_added and rec.realized_added[0][0][1] == 12345
    assert "sell_filled_paper" in rec.event_types
    assert risk.orders_recorded == 0  # 매도는 일일 주문수 한도에 카운트하지 않는다


def test_sell_skips_when_quantity_zero(engine):
    eng, client, risk, data, rec = engine
    out = eng.execute_sell("20260626", "005930", 0, 10000, "KRX", tag="krx")
    assert out is None
    assert client.sells == []
