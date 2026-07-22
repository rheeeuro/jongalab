"""레버리지 ETF 대체매수 치환 순수 로직 고정 (DB 미접근).

불변식:
  - 매핑에 없으면 sig 그대로, swap=None (현행 동작).
  - 매핑에 있으면 종목코드/이름만 ETF 로 교체하고 신호 id·score 는 유지.
  - ETF 코드가 비면 치환하지 않는다(방어).
"""
import workers.signal_executor as se


def test_no_swap_when_not_mapped():
    sig = {"id": 7, "stk_cd": "005930", "stk_nm": "삼성전자", "score": 80}
    out, swap = se.resolve_leverage_target(sig, {"000660": {"etf_cd": "0193T0", "etf_nm": "X"}})
    assert swap is None
    assert out is sig  # 무치환은 원본 그대로


def test_swap_replaces_code_and_name_only():
    sig = {"id": 7, "stk_cd": "005930", "stk_nm": "삼성전자", "score": 80, "rank_no": 1}
    lev = {"005930": {"etf_cd": "0193W0", "etf_nm": "KODEX 삼성전자단일종목레버리지"}}
    out, swap = se.resolve_leverage_target(sig, lev)
    assert out["stk_cd"] == "0193W0"
    assert out["stk_nm"] == "KODEX 삼성전자단일종목레버리지"
    # 신호 식별·점수·순위는 원신호 유지(상태 갱신·멱등키는 원신호 id 기준)
    assert out["id"] == 7 and out["score"] == 80 and out["rank_no"] == 1
    assert swap == {"src_cd": "005930", "src_nm": "삼성전자",
                    "etf_cd": "0193W0", "etf_nm": "KODEX 삼성전자단일종목레버리지"}
    assert sig["stk_cd"] == "005930"  # 원본 불변(새 dict 반환)


def test_no_swap_when_etf_code_missing():
    sig = {"id": 7, "stk_cd": "005930", "stk_nm": "삼성전자"}
    out, swap = se.resolve_leverage_target(sig, {"005930": {"etf_cd": "", "etf_nm": None}})
    assert swap is None
    assert out is sig
