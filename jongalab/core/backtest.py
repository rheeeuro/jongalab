"""제안 가중치 백테스트(검증) — 승인 전 정량 근거 제공.

주간 `weight_tuner` 가 만든 가중치 제안을, 실제로 매매했던 표본(저장된 종목 지표 + 실현손익)에
**재적용**해 "제안 가중치가 승자/패자를 더 잘 가려내는가"를 수치로 보여준다. GPT 설명만 보고
승인하던 것을 근거 기반 승인으로 바꾼다.

[정확 재현이 가능한 이유]
`recompute_score()` 는 `trading_engine.AnalysisEngine.score_candidate()` 공식을 그대로 미러링한다.
저장된 `daily_stock_report` 컴포넌트(supply_score/ma_aligned/near_high/trading_value/is_leader/
prog_net_buy/is_theme_stock/supply_days/content_score)만으로 정확히 재현된다. 콘텐츠 항은 원천값이
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


def recompute_score(row: dict, w: dict) -> float:
    """저장된 종목 지표(row)에 가중치(w)를 적용해 종합점수(0~100)를 재계산.

    score_candidate() 와 동일 공식. w 에 없는 키는 전략 기본값으로 폴백한다.
    """
    def g(k):
        return w.get(k, _SC_DEFAULTS[k])

    raw = 0.0
    # 5일 수급 가점 — 수급점수(0~100) 비율만큼
    raw += float(row.get("supply_score") or 0) / 100 * g("SCORE_SUPPLY_BONUS")
    # 정배열 + 신고가
    if row.get("ma_aligned"):
        raw += g("SCORE_MA_ALIGNED_BONUS")
    if row.get("near_high"):
        raw += g("SCORE_NEAR_HIGH_BONUS")
    # 거래대금 브래킷 (임계값은 튜닝 대상이 아니라 양쪽 동일)
    tv = int(row.get("trading_value") or 0)
    if tv >= g("PREFERRED_TRADING_VALUE"):
        raw += g("SCORE_PREFERRED_VALUE_BONUS")
    elif tv >= g("MIN_TRADING_VALUE"):
        raw += g("SCORE_MIN_VALUE_BONUS")
    # 대장주
    if row.get("is_leader"):
        raw += g("SCORE_LEADER_BONUS")
    # 프로그램 양매수
    if int(row.get("prog_net_buy") or 0) > 0:
        raw += g("SCORE_PROGRAM_BUY_BONUS")
    # 테마주
    if row.get("is_theme_stock"):
        raw += g("THEME_STOCK_BONUS")
    # 5일 초과 장기 연속 수급
    extra_days = max(int(row.get("supply_days") or 0) - 5, 0)
    raw += min(extra_days, 5) * g("SCORE_EXTRA_SUPPLY_DAY_BONUS")
    # 콘텐츠 — 저장된 원천값(≤10)에 제안 상한만 다시 적용
    raw += min(float(row.get("content_score") or 0), g("CONTENT_SCORE_MAX"))
    # 뉴스 재료 — news_count 가 NEWS_HEAT_CAP 에서 SCORE_NEWS_BONUS 만점 (기본 0 → 무영향)
    cap = g("NEWS_HEAT_CAP") or 1
    raw += min(int(row.get("news_count") or 0), cap) / cap * g("SCORE_NEWS_BONUS")

    max_possible = (
        g("SCORE_SUPPLY_BONUS")
        + g("SCORE_MA_ALIGNED_BONUS")
        + g("SCORE_NEAR_HIGH_BONUS")
        + g("SCORE_PREFERRED_VALUE_BONUS")
        + g("SCORE_LEADER_BONUS")
        + g("SCORE_PROGRAM_BUY_BONUS")
        + g("THEME_STOCK_BONUS")
        + 5 * g("SCORE_EXTRA_SUPPLY_DAY_BONUS")
        + g("CONTENT_SCORE_MAX")
        + g("SCORE_NEWS_BONUS")
    )
    return round(raw / max_possible * 100, 1) if max_possible else 0.0


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
