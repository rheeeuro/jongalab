"""reconcile_dead_sent 오판정 방지 테스트 — 체결된 주문을 '소멸'로 마감하지 않는다.

회귀 방지: 2026-08-05 레인보우로보틱스 — 08:03:12 매도 IOC 가 전량체결됐는데 1초 뒤 폴링이
canceled + 멱등키 해제로 마감했다. 체결된 주문은 미체결 목록(ka10075)에 없고 체결내역
(ka10076) 반영은 몇 초 늦으므로, 두 조회가 동시에 "없다"고 답하는 창이 존재한다.
그 결과 sync_fills(status='sent' 만 조회)가 다시는 못 봐 체결·실현손익이 영구 누락되고
유령 포지션이 남았다. 가드는 (1) 전송 후 최소 경과시간, (3) 브로커 체결내역 교차확인이다.
DB·네트워크 없이 fake 로 검증한다(conftest 철학 동일).
"""
import pytest

from core import order_maintenance as om


class FakeClient:
    """reconcile_dead_sent 가 쓰는 최소 표면만: paper, 미체결(oso), 체결내역(cntr)."""

    paper = False

    def __init__(self, oso=(), cntr=()):
        self._oso = list(oso)
        self._cntr = list(cntr)
        self.calls = 0

    def get_open_orders(self, stex_tp="0"):
        self.calls += 1
        return {"oso": self._oso}

    def get_executions(self, qry_tp="0", sell_tp="0", stex_tp="0"):
        self.calls += 1
        return {"cntr": self._cntr}


@pytest.fixture
def spy(monkeypatch):
    """void_dead_order 호출을 가로채고, 로컬 체결분은 0 으로 고정."""
    voided = []
    monkeypatch.setattr(om.order_repo, "void_dead_order", lambda oid: voided.append(oid))
    monkeypatch.setattr(om.fill_repo, "filled_qty", lambda oid: 0)
    return voided


def _aged(monkeypatch, rows):
    """get_open_sent_aged 를 rows 로 대체 — 경과시간 필터는 SQL 이 담당하므로 여기선 주입."""
    monkeypatch.setattr(om.order_repo, "get_open_sent_aged", lambda min_age: list(rows))


ORDER = {"id": 1604, "stk_cd": "277810", "kiwoom_ord_no": "0011580"}


def test_freshly_sent_order_is_not_touched(monkeypatch, spy):
    """경과시간 미달이면 후보에서 빠져 브로커 조회조차 하지 않는다(그날의 실제 경합 구간)."""
    _aged(monkeypatch, [])  # SQL 필터가 갓 전송된 주문을 제외한 상태
    client = FakeClient()
    assert om.reconcile_dead_sent(client) == 0
    assert client.calls == 0  # 조회 자체를 안 함 — 폴링당 API 호출도 늘지 않는다
    assert spy == []


def test_filled_at_broker_is_not_voided(monkeypatch, spy):
    """미체결 목록엔 없지만 체결내역에 체결이 있으면 죽은 주문이 아니다 — sync_fills 몫."""
    _aged(monkeypatch, [ORDER])
    client = FakeClient(oso=[], cntr=[{"ord_no": "0011580", "cntr_qty": "1"}])
    assert om.reconcile_dead_sent(client) == 0
    assert spy == []


def test_zero_qty_execution_row_does_not_protect(monkeypatch, spy):
    """체결수량 0 인 row 는 '체결 있음'이 아니다 — 진짜 소멸 주문은 계속 정리돼야 한다."""
    _aged(monkeypatch, [ORDER])
    client = FakeClient(oso=[], cntr=[{"ord_no": "0011580", "cntr_qty": "0"}])
    assert om.reconcile_dead_sent(client) == 1
    assert spy == [1604]


def test_truly_dead_order_is_voided(monkeypatch, spy):
    """브로커 미체결·체결내역 모두 없고 로컬 체결 0 → 소멸한 IOC. 멱등키 해제로 재매도 허용."""
    _aged(monkeypatch, [ORDER])
    assert om.reconcile_dead_sent(FakeClient(oso=[], cntr=[])) == 1
    assert spy == [1604]


def test_still_open_at_broker_is_preserved(monkeypatch, spy):
    """미체결로 살아있으면 체결 여지가 있어 보존(기존 가드 회귀 확인)."""
    _aged(monkeypatch, [ORDER])
    client = FakeClient(oso=[{"ord_no": "0011580", "stex_tp_txt": "NXT"}], cntr=[])
    assert om.reconcile_dead_sent(client) == 0
    assert spy == []


def test_broker_query_failure_holds_off(monkeypatch, spy):
    """조회 실패 시엔 정리를 보류한다(모르는 상태에서 마감하지 않는다)."""
    _aged(monkeypatch, [ORDER])

    class Boom(FakeClient):
        def get_executions(self, **kw):
            raise RuntimeError("ka10076 timeout")

    assert om.reconcile_dead_sent(Boom(oso=[], cntr=[])) == 0
    assert spy == []


def test_paper_is_noop(monkeypatch, spy):
    """paper 는 즉시 체결 시뮬이라 정리 대상이 없다."""
    _aged(monkeypatch, [ORDER])

    class Paper(FakeClient):
        paper = True

    assert om.reconcile_dead_sent(Paper()) == 0
    assert spy == []
