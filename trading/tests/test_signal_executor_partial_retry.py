"""signal_executor NXT 부분체결 잔량 재시도 테스트.

NXT 매수는 최유리 IOC 라 주문 접수 수량과 실제 체결 수량이 달라질 수 있다.
워커가 체결내역으로 부분체결을 확인하면 목표 수량까지 잔량을 별도 멱등키로 재주문해야 한다.
"""
from datetime import datetime as real_datetime

from workers import signal_executor as se


class FixedDateTime:
    @staticmethod
    def now():
        return real_datetime(2026, 7, 8, 19, 40, 0)


class FakeClient:
    paper = False

    def __init__(self, executions):
        self.executions = list(executions)
        self.buys = []

    def get_executions(self, **kwargs):
        return self.executions.pop(0) if self.executions else {"cntr": []}

    def buy(self, stk_cd, qty, price, trde_tp=None, dmst_stex_tp=None):
        self.buys.append({
            "stk_cd": stk_cd,
            "qty": qty,
            "price": price,
            "trde_tp": trde_tp,
            "dmst_stex_tp": dmst_stex_tp,
        })
        return {"return_code": 0, "return_msg": "ok", "ord_no": f"R{len(self.buys)}"}


class FakeRisk:
    def __init__(self):
        self.checks = []
        self.recorded = 0

    def check(self, trade_date, stk_cd, notional):
        self.checks.append((trade_date, stk_cd, notional))
        return type("Decision", (), {"allowed": True, "reason": ""})()

    def record_order(self, trade_date):
        self.recorded += 1


class FakeData:
    def get_market_price(self, stk_cd):
        return 16700


class FakeEngine:
    def __init__(self, client):
        self.client = client
        self.risk = FakeRisk()
        self.data = FakeData()


def _patch_repos(monkeypatch):
    events = []
    intended = []
    sent = []
    monkeypatch.setattr(se.time, "sleep", lambda _: None)
    monkeypatch.setattr(se, "datetime", FixedDateTime)
    monkeypatch.setattr(se.audit_log, "append", lambda *a, **k: events.append(a))
    monkeypatch.setattr(se.order_repo, "find_by_idempotency_key", lambda key: None)

    def create_intended(*args, **kwargs):
        intended.append(args)
        return len(intended)

    monkeypatch.setattr(se.order_repo, "create_intended", create_intended)
    monkeypatch.setattr(se.order_repo, "mark_sent", lambda *a: sent.append(a))
    return events, intended, sent


def test_nxt_partial_fill_retries_remaining_quantity(monkeypatch):
    events, intended, sent = _patch_repos(monkeypatch)
    client = FakeClient([
        {"cntr": [{"ord_no": "A1", "cntr_qty": "8"}]},
        {"cntr": [
            {"ord_no": "A1", "cntr_qty": "8"},
            {"ord_no": "R1", "cntr_qty": "10"},
        ]},
    ])
    engine = FakeEngine(client)

    out = se._retry_nxt_partial_fill(
        engine,
        "20260708",
        {"id": 2770, "stk_cd": "439090"},
        18,
        16720,
        {"ord_no": "A1"},
        (19, 50),
    )

    assert client.buys == [{
        "stk_cd": "439090",
        "qty": 10,
        "price": 0,
        "trde_tp": "16",
        "dmst_stex_tp": "NXT",
    }]
    assert intended[0][0] == "20260708:2770:buy:partial:1"
    assert intended[0][4] == 10
    assert sent == [(1, "R1", "sent")]
    assert engine.risk.recorded == 1
    assert out["attempts"] == 1
    assert out["remaining"] == 0
    assert "buy_partial_retry_sent" in [e[0] for e in events]


def test_nxt_retry_skips_when_execution_rows_are_not_visible(monkeypatch):
    events, intended, sent = _patch_repos(monkeypatch)
    client = FakeClient([{"cntr": []}])
    engine = FakeEngine(client)

    out = se._retry_nxt_partial_fill(
        engine,
        "20260708",
        {"id": 2770, "stk_cd": "439090"},
        18,
        16720,
        {"ord_no": "A1"},
        (19, 50),
    )

    assert client.buys == []
    assert intended == []
    assert sent == []
    assert out["remaining"] == 18
    assert ("buy_partial_retry_skip", "439090", {
        "reason": "체결내역 미확인",
        "target_qty": 18,
        "order_nos": ["A1"],
    }) in events


def test_nxt_retry_waits_for_latest_retry_execution_before_second_retry(monkeypatch):
    events, intended, sent = _patch_repos(monkeypatch)
    client = FakeClient([
        {"cntr": [{"ord_no": "A1", "cntr_qty": "8"}]},
        {"cntr": [{"ord_no": "A1", "cntr_qty": "8"}]},
    ])
    engine = FakeEngine(client)

    out = se._retry_nxt_partial_fill(
        engine,
        "20260708",
        {"id": 2770, "stk_cd": "439090"},
        18,
        16720,
        {"ord_no": "A1"},
        (19, 50),
    )

    assert len(client.buys) == 1
    assert client.buys[0]["qty"] == 10
    assert len(intended) == 1
    assert sent == [(1, "R1", "sent")]
    assert out["remaining"] == 10
    assert "최근 재시도 체결내역 미확인" in [e[2].get("reason") for e in events if len(e) > 2]
