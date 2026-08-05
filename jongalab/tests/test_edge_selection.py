"""선정 레이어(core/edge_selection.py) 단위 테스트.

모드 3종(legacy/hybrid/rules) × veto(reduce-only) × 상한 초과 × 매칭 0(무거래) 계약 고정.
순수 로직이라 DB 무의존.
"""
from core.edge_selection import select_signals


def _cand(code, rank, sector_rel, change, is_leader=0, name=None):
    return {
        "stock_code": code, "stock_name": name or code, "rank_no": rank, "score": 100 - rank,
        "sector_rel_ret": sector_rel, "change_pct": change, "is_leader": is_leader,
    }


# 점수순(rank asc) 유니버스
UNIVERSE = [
    _cand("A", 1, 1.0, 3),
    _cand("B", 2, -1.0, 5, is_leader=1),
    _cand("C", 3, 0.5, 2),
    _cand("D", 4, 2.0, 10),
    _cand("E", 5, -2.0, 16),
]

R_SECTOR = {"name": "r_sector", "family": "f4_laggard",
            "predicate": [{"col": "sector_rel_ret", "op": ">=", "value": 1}],
            "stats": {"mean_net": 0.1}}          # 매칭: A(1.0), D(2.0)
R_CHANGE = {"name": "r_change", "family": "f1_news",
            "predicate": [{"col": "change_pct", "op": ">=", "value": 10}],
            "stats": {"mean_net": 2.0}}          # 매칭: D(10), E(16)
V_OVERHEAT = {"name": "v_overheat", "family": "veto",
              "predicate": [{"col": "change_pct", "op": ">=", "value": 15}]}  # 매칭: E(16)


# ── legacy ──
def test_legacy_is_top_n_by_rank():
    sel, names, veto = select_signals("legacy", UNIVERSE, [R_SECTOR], [], top_n=3)
    assert sel == ["A", "B", "C"]
    assert names == {}          # legacy 는 rule 태깅 없음
    assert veto == []


def test_legacy_with_veto_removes_no_backfill():
    # veto 가 top-N 안의 종목을 제외하면 그 자리는 비운다(reduce-only, 승급 없음).
    v_c = {"name": "v_c", "family": "veto", "predicate": [{"col": "stock_code", "op": "==", "value": "C"}]}
    sel, names, veto = select_signals("legacy", UNIVERSE, [], [v_c], top_n=3)
    assert sel == ["A", "B"]    # C 제외, D(rank4)로 채우지 않음
    assert [v["code"] for v in veto] == ["C"]


def test_unknown_mode_falls_back_to_legacy():
    sel, _, _ = select_signals("???", UNIVERSE, [R_SECTOR], [], top_n=2)
    assert sel == ["A", "B"]


# ── hybrid: 표 수(①) → 성적(②) → 점수(③) ──
def test_hybrid_matched_priority_then_fill_by_score():
    # 표: A=r_sector+legacy(rank1≤3)=2 / D=r_sector=1 / B,C=legacy=1 / E=0
    # 2표 A 먼저, 1표 그룹은 성적순(D 0.1 > B·C 성적 미상) → 잔여 슬롯은 점수순 B
    sel, names, veto = select_signals("hybrid", UNIVERSE, [R_SECTOR], [], top_n=3)
    assert sel == ["A", "D", "B"]
    assert names == {"A": "r_sector", "D": "r_sector"}   # 선정된 매칭 종목만 태깅(B 없음)


def test_hybrid_cap_orders_ties_by_rule_performance():
    # 표: A=r_sector+legacy=2 / D=r_sector+r_change=2 / B=legacy=1 / E=r_change=1
    # 동표 2 → 성적으로 가른다: D(best 2.0) > A(best 0.1) — 점수는 A 가 앞서지만 밀린다
    sel, names, _ = select_signals("hybrid", UNIVERSE, [R_SECTOR, R_CHANGE], [], top_n=2)
    assert sel == ["D", "A"]
    assert names["A"] == "r_sector"
    assert set(names["D"].split(",")) == {"r_sector", "r_change"}  # D 는 두 rule 동시 매칭


def test_hybrid_vote_count_outranks_both_score_and_performance():
    # top_n=1 로 legacy 표를 A 에만 준다. E 는 성적 2.0 짜리 rule 1개(1표),
    # D 는 성적 0.1·2.0 두 rule(2표) → 표 수가 1순위이므로 D.
    sel, _, _ = select_signals("hybrid", UNIVERSE, [R_SECTOR, R_CHANGE], [], top_n=1)
    assert sel == ["D"]


def test_hybrid_legacy_top_n_counts_as_one_vote():
    # rule 매칭이 하나도 없으면 legacy 표만 남아 결과가 legacy 와 같아야 한다(점수순 top_n).
    r_none = {"name": "r_none", "family": "f3_nxt", "stats": {"mean_net": 9.0},
              "predicate": [{"col": "nxt_gap_pct", "op": ">=", "value": 1}]}   # 컬럼 없음 → 매칭 0
    sel, names, _ = select_signals("hybrid", UNIVERSE, [r_none], [], top_n=3)
    assert sel == ["A", "B", "C"]
    assert names == {}


def test_hybrid_legacy_mean_net_competes_in_the_tiebreak():
    # legacy 표의 성적을 넘기면 동표 그룹에서 rule 성적과 직접 겨룬다.
    # 2표 그룹: A(r_sector 0.1 + legacy 5.0 → best 5.0) > D(2.0) — 성적 없이는 D 가 앞섰다.
    # 1표 그룹: B·C(legacy 5.0) > E(r_change 2.0).
    sel, _, _ = select_signals("hybrid", UNIVERSE, [R_SECTOR, R_CHANGE], [], top_n=3,
                               legacy_mean_net=5.0)
    assert sel == ["A", "D", "B"]
    # 같은 배치에서 legacy 성적이 낮으면(0.5) E 가 B 를 제친다.
    sel_low, _, _ = select_signals("hybrid", UNIVERSE, [R_SECTOR, R_CHANGE], [], top_n=3,
                                   legacy_mean_net=0.5)
    assert sel_low == ["D", "A", "E"]


# ── rules ──
def test_rules_orders_by_mean_net_then_caps():
    # 매칭: A(best 0.1), D(best 2.0), E(best 2.0). 기대값순 → D,E(2.0) 먼저, top_n=2 → [D,E]
    sel, names, _ = select_signals("rules", UNIVERSE, [R_SECTOR, R_CHANGE], [], top_n=2)
    assert sel == ["D", "E"]
    assert "A" not in names        # 선정 안 됨 → 태깅에서 제외


def test_rules_zero_match_is_no_trade():
    r_none = {"name": "r_none", "family": "f3_nxt",
              "predicate": [{"col": "nxt_gap_pct", "op": ">=", "value": 1}],  # 컬럼 없음 → NULL → 매칭 0
              "stats": {}}
    sel, names, veto = select_signals("rules", UNIVERSE, [r_none], [], top_n=3)
    assert sel == []               # 무거래
    assert names == {}


def test_rules_veto_excludes_matched():
    # E 는 R_CHANGE 매칭이지만 veto(과열)로 제외 → 후보에서 사라짐
    sel, names, veto = select_signals("rules", UNIVERSE, [R_CHANGE], [V_OVERHEAT], top_n=3)
    assert "E" not in sel
    assert sel == ["D"]            # R_CHANGE 매칭 중 E 빠지고 D 만
    assert [v["code"] for v in veto] == ["E"]


def test_veto_applies_across_all_modes():
    for mode in ("legacy", "hybrid", "rules"):
        _, _, veto = select_signals(mode, UNIVERSE, [R_CHANGE], [V_OVERHEAT], top_n=5)
        assert [v["code"] for v in veto] == ["E"], mode
