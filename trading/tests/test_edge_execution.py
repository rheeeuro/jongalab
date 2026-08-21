"""집행 레이어 rule 판정 순수 로직 고정 (DB·네트워크 미접근).

불변식(깨지면 자금 경로 동작이 바뀐다):
  - 집행 레이어 rule 판정은 **predicate 가 집행기 채움 컬럼(nxt_gap_pct 등)을 쓰는지**로 한다.
    선정 시점에 평가되는 rule 을 집행기가 또 적용하면 이중 필터가 된다.
  - **fail-open 4종**: 집행 rule 없음 / 점수 선정분 / 갭 없음 / 리포트 행 없음 → 전부 매수.
  - 오설정 rule 하나가 전 종목 매수를 막지 않는다(그 rule 만 무시).
  - 매칭은 OR(하나라도 맞으면 매수) — predicate 내부는 AND(edge_predicate 계약).
  - 원본 report_row 를 변형하지 않는다(호출부가 재사용).
"""
import pytest

from core import edge_execution as ee

GAP_RULE = {
    "name": "f3_nxt_gap_quality", "role": "selector",
    "predicate": [
        {"col": "nxt_gap_pct", "op": "between", "value": [1.0, 6.0]},
        {"col": "nxt_listed", "op": "==", "value": 1},
        {"col": "sector_rel_ret", "op": ">=", "value": 0},
        {"col": "change_pct", "op": "between", "value": [0, 12]},
    ],
}
SELECTION_RULE = {"name": "f5_prog_persistent", "role": "selector",
                  "predicate": [{"col": "prog_buy_days", "op": ">=", "value": 4}]}
ROW = {"nxt_listed": 1, "sector_rel_ret": 0.5, "change_pct": 5.0}


def test_layer_detection_by_executor_filled_cols():
    assert ee.is_execution_layer_rule(GAP_RULE) is True
    # 선정 시점에 평가되는 rule 은 집행기가 손대지 않는다(이중 적용 방지)
    assert ee.is_execution_layer_rule(SELECTION_RULE) is False


def test_matched_rule_buys():
    v = ee.decide(ROW, [GAP_RULE], 3.0, 100_000, rule_names="f3_nxt_gap_quality",
                  rank_no=15, score_top_n=10)
    assert v["buy"] is True and v["matched"] == ["f3_nxt_gap_quality"]


def test_unmatched_rule_skips_when_solely_selected_by_it():
    v = ee.decide(ROW, [GAP_RULE], -2.5, 100_000, rule_names="f3_nxt_gap_quality",
                  rank_no=15, score_top_n=10)
    assert v["buy"] is False and v["in_scope"] is True


# ── 판정 대상 범위: "그 rule 이 혼자 데려온 종목"만 (2026-08-03 사용자 결정) ──

def test_score_picked_is_never_skipped():
    """하이브리드의 '잔여 슬롯은 점수순'을 집행 레이어가 뒤집지 않는다."""
    v = ee.decide(ROW, [GAP_RULE], -2.5, 100_000, rule_names=None, rank_no=3, score_top_n=10)
    assert v["buy"] is True and v["in_scope"] is False


def test_multi_rule_selection_is_out_of_scope():
    """다른 rule 과 함께 선정된 종목은 그 rule 이 별도 근거를 갖는다 → 비대상."""
    v = ee.decide(ROW, [GAP_RULE], -2.5, 100_000,
                  rule_names="f3_nxt_gap_quality,f5_prog_persistent",
                  rank_no=15, score_top_n=10)
    assert v["buy"] is True and v["in_scope"] is False
    assert "다른 rule 과 함께" in v["reason"]


def test_other_rule_only_is_out_of_scope():
    """집행 레이어 rule 이 아닌 근거로 들어온 종목은 건드리지 않는다."""
    v = ee.decide(ROW, [GAP_RULE], -2.5, 100_000, rule_names="f5_prog_persistent",
                  rank_no=15, score_top_n=10)
    assert v["buy"] is True and v["in_scope"] is False


def test_also_in_score_top_n_is_out_of_scope():
    """룰이 없어도 점수로 선정될 종목이었다면 비대상."""
    v = ee.decide(ROW, [GAP_RULE], -2.5, 100_000, rule_names="f3_nxt_gap_quality",
                  rank_no=7, score_top_n=10)
    assert v["buy"] is True and v["in_scope"] is False
    assert "점수 top-10" in v["reason"]


def test_missing_rank_info_is_out_of_scope_conservatively():
    for rank, top_n in ((None, 10), (15, None)):
        v = ee.decide(ROW, [GAP_RULE], -2.5, 100_000, rule_names="f3_nxt_gap_quality",
                      rank_no=rank, score_top_n=top_n)
        assert v["buy"] is True and v["in_scope"] is False


@pytest.mark.parametrize("row,rules,gap", [
    (ROW, [], 3.0),
    (ROW, [SELECTION_RULE], -2.5),
    (ROW, [GAP_RULE], None),
    (None, [GAP_RULE], -2.5),
])
def test_fail_open_paths_buy(row, rules, gap):
    v = ee.decide(row, rules, gap, 100_000, rule_names="f3_nxt_gap_quality",
                  rank_no=15, score_top_n=10)
    assert v["buy"] is True


def test_broken_rule_does_not_block_others():
    broken = {"name": "bad", "predicate": [{"col": "nxt_gap_pct", "op": "??", "value": 1}]}
    v = ee.decide(ROW, [broken, GAP_RULE], 3.0, 100_000,
                  rule_names="f3_nxt_gap_quality", rank_no=15, score_top_n=10)
    assert v["buy"] is True and v["matched"] == ["f3_nxt_gap_quality"]
    v2 = ee.decide(ROW, [broken], 3.0, 100_000, rule_names="bad", rank_no=15, score_top_n=10)
    assert v2["buy"] is False


def test_does_not_mutate_report_row():
    row = dict(ROW)
    ee.decide(row, [GAP_RULE], 3.0, 100_000, rule_names="f3_nxt_gap_quality",
              rank_no=15, score_top_n=10)
    assert "nxt_gap_pct" not in row and row == ROW


def test_gap_band_comes_from_predicate_not_constants():
    """밴드를 rule 이 갖는다 — predicate 를 바꾸면 판정이 따라온다(하드코딩 상수 아님)."""
    wide = {**GAP_RULE, "predicate": [
        {"col": "nxt_gap_pct", "op": ">=", "value": -5.0},
        {"col": "nxt_listed", "op": "==", "value": 1},
    ]}
    v = ee.decide(ROW, [wide], -2.5, 100_000, rule_names="f3_nxt_gap_quality",
                  rank_no=15, score_top_n=10)
    assert v["buy"] is True


def test_market_axis_rule_fails_open_instead_of_rejecting_everything():
    """시황 축(`market.*`)을 쓰는 rule 은 집행기가 판정하지 않고 **매수**로 흘린다.

    집행기는 시장 스냅샷을 갖지 않는다(그 축은 jongalab 선정 회차 19:40 이 슬롯 1935 로
    평가한다). 평가하면 NULL 매칭 실패가 되고, 이 레이어는 미매칭이 곧 매수 스킵이라
    조용히 전건 거부된다 — 판정 불가는 매수 쪽으로 흘리는 게 모듈 규약이다.
    """
    rule = {**GAP_RULE, "name": "f3_gap_x_night_fut", "predicate": [
        {"col": "nxt_gap_pct", "op": "between", "value": [1.0, 6.0]},
        {"col": "nxt_listed", "op": "==", "value": 1},
        {"col": "market.k200f_night_ret", "op": ">=", "value": -0.4},
    ]}
    v = ee.decide(ROW, [rule], 3.0, 100_000, rule_names="f3_gap_x_night_fut",
                  rank_no=15, score_top_n=10)
    assert v["buy"] is True
    assert v["matched"] == []
    assert "시황 축" in v["reason"]
