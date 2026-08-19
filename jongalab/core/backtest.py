"""제안 가중치 백테스트(검증) — 승인 전 정량 근거 제공.

주간 `weight_tuner` 가 만든 가중치 제안을, 실제로 매매했던 표본(저장된 종목 지표 + 실현손익)에
**재적용**해 "제안 가중치가 승자/패자를 더 잘 가려내는가"를 수치로 보여준다. GPT 설명만 보고
승인하던 것을 근거 기반 승인으로 바꾼다.

`score_components()` 는 이 파일의 유일한 채점 공식이고 두 곳이 함께 쓴다 —
백테스트 총점(`recompute_score`)과 **종목 상세 화면의 종합점수 게이지**(`score_breakdown`,
`/api/stock-report/{date}/{code}`). 화면이 가중치를 따로 갖고 있으면 주간 튜닝 때마다 어긋난다.

[정확 재현이 가능한 이유]
`score_components()` 는 `trading_engine.AnalysisEngine.score_candidate()` 공식을 그대로 미러링한다.
저장된 `daily_stock_report` 컴포넌트(supply_score/ma_aligned/near_high/trading_value/is_leader/
prog_net_buy/is_theme_stock/supply_days/content_score/change_pct)만으로 정확히 재현된다. 콘텐츠 항은 원천값이
항상 ≤10 이라 저장된 content_score 를 그대로 콘텐츠 항으로 쓰고 상한(CONTENT_SCORE_MAX)만 다시 적용한다.

⚠️ 엔진(`core/trading_engine.py` score_candidate)이 가드로 보호되는 민감 파일이라 직접 수정은
   금지지만, 공식이 바뀌면 이 미러도 함께 바꿔야 한다. `tests/test_backtest.py` 가 실제
   score_candidate 와 교차검증해 드리프트를 잡는다(미러가 어긋나면 테스트 실패).

[한계 — 반드시 인지]
`daily_stock_report` 는 '실제 선정된 종목'만 저장한다(탈락 후보 미저장). 따라서 이 백테스트는
'우리가 고른 종목들 사이의 순위 품질'만 측정한다 — 다른 가중치가 '더 좋은 종목을 골랐을지'는
판단할 수 없다(필요조건이지 충분조건이 아님).
"""
from core.repository.strategy_config import _DEFAULTS as _SC_DEFAULTS


def score_components(row: dict, w: dict) -> list[dict]:
    """저장된 종목 지표(row)에 가중치(w)를 적용해 **항목별 가점**을 낸다.

    항목 순서·공식은 score_candidate() 와 같다. 총점(`recompute_score`)과 화면 게이지
    (`score_breakdown`)가 이 한 함수를 함께 쓴다 — 갈라 두면 항목 합이 총점과 어긋난다.
    `raw_max` 는 그 항목이 받을 수 있는 최대 가점(정규화 분모의 구성분)이고, 과열 항은
    감점이라 `raw` 가 음수이며 `raw_max` 는 0 이다(엔진 max_possible 에 미포함).
    w 에 없는 키는 전략 기본값으로 폴백한다.
    """
    def g(k):
        return w.get(k, _SC_DEFAULTS[k])

    # 거래대금 브래킷 (임계값은 튜닝 대상이 아니라 양쪽 동일)
    tv = int(row.get("trading_value") or 0)
    if tv >= g("PREFERRED_TRADING_VALUE"):
        value_raw = float(g("SCORE_PREFERRED_VALUE_BONUS"))
    elif tv >= g("MIN_TRADING_VALUE"):
        value_raw = float(g("SCORE_MIN_VALUE_BONUS"))
    else:
        value_raw = 0.0

    # 당일 등락률 — 스윗스팟(2~12%) 가점, 과열(15%+) 감점
    change_pct = float(row.get("change_pct") or 0)
    in_band = g("CHANGE_BAND_MIN_PCT") <= change_pct < g("CHANGE_BAND_MAX_PCT")
    overheated = not in_band and change_pct >= g("OVERHEAT_CHANGE_PCT")

    # 5일 이내 연속성은 supply_score 에 이미 반영 → 6~10일+ 장기 연속만 가산
    extra_days = min(max(int(row.get("supply_days") or 0) - 5, 0), 5)
    cap = g("NEWS_HEAT_CAP") or 1

    return [
        {"key": "supply", "label": "5일 수급",
         "raw": float(row.get("supply_score") or 0) / 100 * g("SCORE_SUPPLY_BONUS"),
         "raw_max": float(g("SCORE_SUPPLY_BONUS"))},
        {"key": "ma_aligned", "label": "이동평균 정배열",
         "raw": float(g("SCORE_MA_ALIGNED_BONUS")) if row.get("ma_aligned") else 0.0,
         "raw_max": float(g("SCORE_MA_ALIGNED_BONUS"))},
        {"key": "near_high", "label": "52주 신고가 근접",
         "raw": float(g("SCORE_NEAR_HIGH_BONUS")) if row.get("near_high") else 0.0,
         "raw_max": float(g("SCORE_NEAR_HIGH_BONUS"))},
        {"key": "trading_value", "label": "거래대금",
         "raw": value_raw, "raw_max": float(g("SCORE_PREFERRED_VALUE_BONUS"))},
        {"key": "leader", "label": "섹터 대장주",
         "raw": float(g("SCORE_LEADER_BONUS")) if row.get("is_leader") else 0.0,
         "raw_max": float(g("SCORE_LEADER_BONUS"))},
        {"key": "prog_buy", "label": "프로그램 양매수",
         "raw": float(g("SCORE_PROGRAM_BUY_BONUS")) if int(row.get("prog_net_buy") or 0) > 0 else 0.0,
         "raw_max": float(g("SCORE_PROGRAM_BUY_BONUS"))},
        {"key": "theme", "label": "오늘의 테마주",
         "raw": float(g("THEME_STOCK_BONUS")) if row.get("is_theme_stock") else 0.0,
         "raw_max": float(g("THEME_STOCK_BONUS"))},
        {"key": "change_band", "label": "당일 등락 구간",
         "raw": float(g("SCORE_CHANGE_BAND_BONUS")) if in_band else 0.0,
         "raw_max": float(g("SCORE_CHANGE_BAND_BONUS"))},
        {"key": "overheat", "label": "당일 과열 감점",
         "raw": -float(g("SCORE_OVERHEAT_PENALTY")) if overheated else 0.0,
         "raw_max": 0.0},
        {"key": "supply_days", "label": "연속 수급",
         "raw": extra_days * float(g("SCORE_EXTRA_SUPPLY_DAY_BONUS")),
         "raw_max": 5 * float(g("SCORE_EXTRA_SUPPLY_DAY_BONUS"))},
        # 콘텐츠 — 저장된 원천값(≤10)에 제안 상한만 다시 적용
        {"key": "content", "label": "유튜브·텔레그램 언급",
         "raw": min(float(row.get("content_score") or 0), g("CONTENT_SCORE_MAX")),
         "raw_max": float(g("CONTENT_SCORE_MAX"))},
        # 뉴스 재료 — news_count 가 NEWS_HEAT_CAP 에서 SCORE_NEWS_BONUS 만점 (기본 0 → 무영향)
        {"key": "news", "label": "뉴스 재료",
         "raw": min(int(row.get("news_count") or 0), cap) / cap * g("SCORE_NEWS_BONUS"),
         "raw_max": float(g("SCORE_NEWS_BONUS"))},
    ]


def recompute_score(row: dict, w: dict) -> float:
    """저장된 종목 지표(row)에 가중치(w)를 적용해 종합점수(0~100)를 재계산.

    score_candidate() 와 동일 공식. w 에 없는 키는 전략 기본값으로 폴백한다.
    """
    items = score_components(row, w)
    raw = sum(i["raw"] for i in items)
    # 100점 만점 환산 분모 = 각 가점의 최대 합 (감점 항은 미포함)
    max_possible = sum(i["raw_max"] for i in items)
    # 과열 감점으로 음수가 될 수 있어 0 에서 클램프 (엔진과 동일)
    return round(max(raw, 0.0) / max_possible * 100, 1) if max_possible else 0.0


def score_breakdown(row: dict, w: dict) -> dict:
    """화면 게이지용 — 항목별 가점을 **100점 환산 점수**로 낸다(합 = 총점).

    가중치 0 인 항목(`SCORE_PROGRAM_BUY_BONUS`·`SCORE_NEWS_BONUS` 처럼 표시·튜닝 전용)은
    채울 수 없는 칸이라 제외한다. 감점 항은 `penalty` 로 따로 낸다(막대 밖 각주용).
    """
    items = score_components(row, w)
    max_possible = sum(i["raw_max"] for i in items) or 1.0

    def to100(v: float) -> float:
        return round(v / max_possible * 100, 1)

    penalty = next((i for i in items if i["key"] == "overheat" and i["raw"] < 0), None)
    return {
        "items": [
            {"key": i["key"], "label": i["label"],
             "points": to100(i["raw"]), "max_points": to100(i["raw_max"])}
            for i in items
            if i["raw_max"] > 0
        ],
        "penalty": (
            {"key": penalty["key"], "label": penalty["label"], "points": to100(penalty["raw"])}
            if penalty else None
        ),
        "total": recompute_score(row, w),
    }


def _avg(xs: list) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _ranks(vals: list) -> list:
    """오름차순 1-based 순위 (동점은 평균순위)."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-based 평균순위
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman(pairs: list):
    """Spearman 순위상관 (-1~1). n<2 이거나 한쪽이 전부 동점이면 None."""
    if len(pairs) < 2:
        return None
    rx = _ranks([p[0] for p in pairs])
    ry = _ranks([p[1] for p in pairs])
    mx, my = _avg(rx), _avg(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    if dx == 0 or dy == 0:
        return None
    return round(num / ((dx * dy) ** 0.5), 3)


def evaluate_weights(samples: list, weights: dict) -> dict:
    """표본 전체를 weights 로 재채점하고 판별력 지표를 계산.

    spread = 승자 평균점수 − 패자 평균점수 (양수·클수록 승자를 더 높게 평가 = 좋음).
    pnl_rank_corr = 재계산 점수와 실현손익의 순위상관 (-1~1, 클수록 좋음).
    """
    scored = [{**s, "_score": recompute_score(s, weights)} for s in samples]
    win = [r["_score"] for r in scored if (r.get("realized_pnl") or 0) > 0]
    loss = [r["_score"] for r in scored if (r.get("realized_pnl") or 0) < 0]
    has_both = bool(win) and bool(loss)
    return {
        "winner_avg_score": round(_avg(win), 1) if win else None,
        "loser_avg_score": round(_avg(loss), 1) if loss else None,
        "spread": round(_avg(win) - _avg(loss), 1) if has_both else None,
        "pnl_rank_corr": _spearman([(r["_score"], r.get("realized_pnl") or 0) for r in scored]),
        "scores": [
            {"stk_cd": r.get("stk_cd"), "name": r.get("name"), "outcome": r.get("outcome"),
             "realized_pnl": r.get("realized_pnl"), "score": r["_score"]}
            for r in scored
        ],
    }


def backtest_proposal(samples: list, current_weights: dict, proposed_weights: dict) -> dict:
    """현재 vs 제안 가중치로 표본을 재채점해 판별력 개선 여부를 판정.

    verdict: IMPROVES(스프레드↑) / WORSENS(스프레드↓) / NEUTRAL(동일) / INSUFFICIENT(승·패 한쪽뿐).
    """
    cur = evaluate_weights(samples, current_weights)
    prop = evaluate_weights(samples, proposed_weights)

    spread_delta = (round(prop["spread"] - cur["spread"], 1)
                    if cur["spread"] is not None and prop["spread"] is not None else None)
    corr_delta = (round((prop["pnl_rank_corr"] or 0) - (cur["pnl_rank_corr"] or 0), 3)
                  if cur["pnl_rank_corr"] is not None and prop["pnl_rank_corr"] is not None else None)

    if spread_delta is not None and spread_delta != 0:
        verdict = "IMPROVES" if spread_delta > 0 else "WORSENS"
    elif corr_delta is not None and corr_delta != 0:
        verdict = "IMPROVES" if corr_delta > 0 else "WORSENS"
    elif spread_delta is not None or corr_delta is not None:
        verdict = "NEUTRAL"
    else:
        verdict = "INSUFFICIENT"

    return {
        "sample_count": len(samples),
        "current": cur,
        "proposed": prop,
        "spread_delta": spread_delta,
        "corr_delta": corr_delta,
        "verdict": verdict,
        "note": "표본은 실제 선정·매매된 종목뿐 — '선정 종목 내 순위 품질'만 측정합니다(탈락 후보 미반영).",
    }
