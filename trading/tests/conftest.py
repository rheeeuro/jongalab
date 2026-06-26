"""자금 경로 테스트 공용 fixture.

핵심 전략: DB·키움 네트워크를 절대 건드리지 않는다.
- 클라이언트/리스크/데이터는 가짜(fake) 객체를 생성자로 주입한다.
- repository 모듈 함수(order/audit_log/fill/position/risk_state)는 monkeypatch 로
  recorder 에 연결해, 어떤 부수효과가 어떤 인자로 일어났는지 검증한다.
"""
import pytest

from core import execution_engine as ee
from core.risk_engine import RiskConfig, RiskDecision


# ── 가짜 협력 객체 ─────────────────────────────────────────────

class FakeOrderClient:
    """KiwoomOrderClient 대역. paper 속성과 buy/sell/get_deposit 만 흉내."""

    def __init__(self, paper=True, buy_resp=None, sell_resp=None, deposit="10000000"):
        self.paper = paper
        self.buys = []
        self.sells = []
        self._deposit = deposit
        self._buy_resp = buy_resp if buy_resp is not None else {
            "return_code": 0, "return_msg": "paper", "paper": True, "ord_no": "PB1"
        }
        self._sell_resp = sell_resp if sell_resp is not None else {
            "return_code": 0, "return_msg": "paper", "paper": True, "ord_no": "PS1"
        }

    def buy(self, stk_cd, qty, price, trde_tp=None, dmst_stex_tp=None):
        self.buys.append(dict(stk_cd=stk_cd, qty=qty, price=price,
                              trde_tp=trde_tp, dmst_stex_tp=dmst_stex_tp))
        return self._buy_resp

    def sell(self, stk_cd, qty, price, trde_tp=None, dmst_stex_tp=None):
        self.sells.append(dict(stk_cd=stk_cd, qty=qty, price=price,
                               trde_tp=trde_tp, dmst_stex_tp=dmst_stex_tp))
        return self._sell_resp

    def get_deposit(self):
        return {"ord_alow_amt": self._deposit}


class FakeRisk:
    """RiskEngine 대역. check() 는 고정 판정을 돌려주고 record_order 횟수만 센다."""

    def __init__(self, allowed=True, reason=""):
        self.cfg = RiskConfig()
        self._decision = RiskDecision(allowed, reason)
        self.checks = []
        self.orders_recorded = 0

    def check(self, trade_date, stk_cd, notional):
        self.checks.append(dict(trade_date=trade_date, stk_cd=stk_cd, notional=notional))
        return self._decision

    def record_order(self, trade_date, n=1):
        self.orders_recorded += n


class FakeData:
    """KiwoomDataClient 대역. 사이징 fallback 의 현재가만 제공."""

    def __init__(self, price=10000):
        self._price = price

    def get_market_price(self, stk_cd):
        return self._price


# ── repository 부수효과 recorder ────────────────────────────────

class RepoRecorder:
    def __init__(self):
        self.events = []          # audit_log.append (event_type, stk_cd, payload)
        self.intended = []        # order_repo.create_intended 인자
        self.sent = []            # order_repo.mark_sent (order_id, ord_no, status)
        self.fills = []           # fill_repo.record_fill
        self.buys_applied = []    # position_repo.apply_buy_fill
        self.sells_applied = []   # position_repo.apply_sell_fill
        self.realized_added = []  # risk_repo.add_realized_pnl
        self.find_result = None   # find_by_idempotency_key 반환값(중복 시뮬레이션)
        self.realized_value = 0   # apply_sell_fill 반환 실현손익
        self._next_order_id = 1

    @property
    def event_types(self):
        return [e[0] for e in self.events]


@pytest.fixture
def repo_rec(monkeypatch):
    """execution_engine 이 부르는 repository 함수들을 recorder 로 교체."""
    rec = RepoRecorder()

    def _create_intended(*a, **k):
        rec.intended.append((a, k))
        oid = rec._next_order_id
        rec._next_order_id += 1
        return oid

    monkeypatch.setattr(ee.order_repo, "find_by_idempotency_key", lambda key: rec.find_result)
    monkeypatch.setattr(ee.order_repo, "create_intended", _create_intended)
    monkeypatch.setattr(ee.order_repo, "mark_sent",
                        lambda order_id, ord_no, status: rec.sent.append((order_id, ord_no, status)))
    monkeypatch.setattr(ee.audit_log, "append",
                        lambda *a, **k: rec.events.append(a))
    monkeypatch.setattr(ee.fill_repo, "record_fill",
                        lambda *a, **k: rec.fills.append((a, k)))
    monkeypatch.setattr(ee.position_repo, "apply_buy_fill",
                        lambda *a, **k: rec.buys_applied.append((a, k)))

    def _apply_sell(*a, **k):
        rec.sells_applied.append((a, k))
        return rec.realized_value

    monkeypatch.setattr(ee.position_repo, "apply_sell_fill", _apply_sell)
    monkeypatch.setattr(ee.risk_repo, "add_realized_pnl",
                        lambda *a, **k: rec.realized_added.append((a, k)))
    return rec


@pytest.fixture
def engine(repo_rec):
    """paper 모드 fake 들로 조립한 ExecutionEngine + recorder 묶음."""
    client = FakeOrderClient(paper=True)
    risk = FakeRisk(allowed=True)
    data = FakeData()
    eng = ee.ExecutionEngine(client=client, risk=risk, data=data)
    return eng, client, risk, data, repo_rec
