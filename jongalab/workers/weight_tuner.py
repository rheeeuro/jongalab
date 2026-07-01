"""주간 가중치 튜너 (토요일 08:00)

지난 한 주 자동매매(종가베팅) 실현손익을 종목별로 집계하고, 각 종목이 매수일에 받았던
종합점수 지표(수급/정배열/신고가/거래대금/대장주/테마/콘텐츠)와 짝지어 winners/losers 를
구성한다. 이 데이터와 현재 종합점수 구성 가중치를 GPT 에 넘겨 '오른 종목과 떨어진 종목을
가른 지표'를 근거로 한 가중치 세부 조정안을 받는다.

제안은 자동 적용하지 않는다. 서버측에서 주간 변화폭을 ±15% 로 클램프한 뒤 backtest 로
판별력을 검증한다: **IMPROVES 면 status='pending'**(검토·승인 대상), 그 외(WORSENS/
NEUTRAL/INSUFFICIENT)는 **status='archived'**(비적용)로 저장한다 — 노이즈 과적합이라
승인 대상은 아니지만 '튜너가 돌긴 했다'를 대시보드에서 확인할 수 있게 이력·표시로 남긴다.
pending 제안만 관리자가 승인하면 strategy_config 에 반영된다(routers/weight_tuning.py).
매 실행마다 현재 가중치의 판별력(스프레드·점수↔손익 상관)을 [건강지표] 로 로깅한다 —
이 값이 양수로 돌아서면 점수 예측력이 회복된 것이라 튜닝 재개의 신호가 된다.
"""
import json
import logging
from datetime import datetime, timedelta

from core.logging_setup import setup_logging
from core.ai_service import complete_json
from core.backtest import backtest_proposal, evaluate_weights
from core.prompts import WEIGHT_TUNING_PROMPT
from core.repository import (
    get_strategy_config,
    get_weekly_trade_results,
    get_stock_report,
    save_proposal,
    SCORE_WEIGHT_KEYS,
)

setup_logging()
logger = logging.getLogger("WeightTuner")

# 분석에 의미가 있으려면 최소 표본 수 (이하이면 GPT 호출 없이 스킵 — 과적합 방지)
MIN_SAMPLES = 5
# 주간 가중치 변화폭 상한 (현재값 대비 ±15%) — 한 주 표본으로 급격히 흔들리지 않게
MAX_REL_DELTA = 0.15
# 0 근처 가중치 부트스트랩: 곱셈식(±15%) 클램프는 0에 영구 고정되므로, |현재값|<=NEAR_ZERO 이면
# 절대 스텝(주당 ±MIN_ABS_STEP)으로 움직이게 한다. 신규 가중치(SCORE_NEWS_BONUS=0)가 성과에
# 따라 0에서 자라날 수 있게 하는 장치. 기존 가중치(모두 >NEAR_ZERO)의 안전폭은 그대로 유지된다.
NEAR_ZERO = 1.0
MIN_ABS_STEP = 3.0
# 가중치별 절대 안전 범위 (백스톱)
ABS_BOUNDS = {
    "SCORE_SUPPLY_BONUS": (10.0, 80.0),
}
DEFAULT_BONUS_BOUNDS = (0.0, 40.0)


def _analysis_week(today=None):
    """분석 대상 주(월~금). 토요일 실행 가정이며, 가장 최근 금요일과 그 주 월요일을 돌려준다."""
    today = today or datetime.now().date()
    days_since_fri = (today.weekday() - 4) % 7
    friday = today - timedelta(days=days_since_fri)
    monday = friday - timedelta(days=4)
    return monday.isoformat(), friday.isoformat()


def _build_dataset(results: list[dict]) -> list[dict]:
    """실현손익 결과에 매수일 종합점수 지표를 조인해 학습용 행 목록을 만든다."""
    rows = []
    for r in results:
        rpt = get_stock_report(r["trade_date"], r["stk_cd"])
        if not rpt:
            logger.warning(f"리포트 없음 — 스킵: {r['stk_cd']} ({r['trade_date']})")
            continue
        pnl = int(r["realized_pnl"])
        rows.append({
            "stk_cd": r["stk_cd"],
            "name": rpt.get("stock_name", ""),
            "trade_date": r["trade_date"],
            "realized_pnl": pnl,
            "outcome": "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT",
            "score": round(float(rpt.get("score") or 0), 1),
            "supply_score": round(float(rpt.get("supply_score") or 0), 1),
            "ma_aligned": bool(rpt.get("ma_aligned")),
            "near_high": bool(rpt.get("near_high")),
            "trading_value": int(rpt.get("trading_value") or 0),
            "is_leader": bool(rpt.get("is_leader")),
            "is_theme_stock": bool(rpt.get("is_theme_stock")),
            "supply_days": int(rpt.get("supply_days") or 0),
            "prog_net_buy": int(rpt.get("prog_net_buy") or 0),
            "prog_buy": int(rpt.get("prog_net_buy") or 0) > 0,
            "content_score": round(float(rpt.get("content_score") or 0), 1),
            "news_count": int(rpt.get("news_count") or 0),
            "change_pct": round(float(rpt.get("change_pct") or 0), 2),
        })
    return rows


def _build_prompt(current_weights: dict, dataset: list[dict]) -> str:
    lines = []
    for d in dataset:
        lines.append(
            f"- {d['name']}({d['stk_cd']}) {d['trade_date']} | 결과={d['outcome']} "
            f"실현손익={d['realized_pnl']:,}원 | 종합점수={d['score']} 수급={d['supply_score']} "
            f"정배열={'Y' if d['ma_aligned'] else 'N'} 신고가={'Y' if d['near_high'] else 'N'} "
            f"거래대금={d['trading_value']:,} 대장주={'Y' if d['is_leader'] else 'N'} "
            f"테마={'Y' if d['is_theme_stock'] else 'N'} 연속수급일={d['supply_days']} "
            f"프로그램양매수={'Y' if d['prog_buy'] else 'N'} 콘텐츠={d['content_score']} "
            f"뉴스언급={d['news_count']}"
        )
    return WEIGHT_TUNING_PROMPT.format(
        current_weights=json.dumps(current_weights, ensure_ascii=False, indent=2),
        dataset_table="\n".join(lines),
    )


def _clamp(key: str, current: float, proposed: float) -> float:
    """현재값 대비 ±MAX_REL_DELTA + 절대 범위로 제안값을 클램프.
    단, |현재값| <= NEAR_ZERO 이면 곱셈식이 0에 고정되므로 절대 스텝(±MIN_ABS_STEP)을 쓴다."""
    delta = MIN_ABS_STEP if abs(current) <= NEAR_ZERO else abs(current) * MAX_REL_DELTA
    lo, hi = current - delta, current + delta
    val = max(lo, min(hi, proposed))
    abs_lo, abs_hi = ABS_BOUNDS.get(key, DEFAULT_BONUS_BOUNDS)
    val = max(abs_lo, min(abs_hi, val))
    # 모든 가중치는 소수 첫째자리까지
    return round(val, 1)


def run():
    week_start, week_end = _analysis_week()
    logger.info(f"주간 가중치 튜닝 시작: {week_start} ~ {week_end}")

    results = get_weekly_trade_results(week_start, week_end)
    if len(results) < MIN_SAMPLES:
        logger.info(f"표본 부족({len(results)} < {MIN_SAMPLES}) — GPT 호출 없이 종료")
        return

    dataset = _build_dataset(results)
    if len(dataset) < MIN_SAMPLES:
        logger.info(f"리포트 조인 후 표본 부족({len(dataset)} < {MIN_SAMPLES}) — 종료")
        return

    cfg = get_strategy_config()
    current_weights = {k: cfg[k] for k in SCORE_WEIGHT_KEYS}

    prompt = _build_prompt(current_weights, dataset)
    logger.info(f"GPT 가중치 조정 요청 (표본 {len(dataset)}건)")
    data = complete_json(prompt)
    if not data or "weights" not in data:
        logger.error("GPT 제안 파싱 실패 — 제안 저장 안 함")
        return

    raw = data["weights"] or {}
    proposed_weights = {}
    for k in SCORE_WEIGHT_KEYS:
        cur = float(current_weights[k])
        try:
            proposed_weights[k] = _clamp(k, cur, float(raw.get(k, cur)))
        except (TypeError, ValueError):
            proposed_weights[k] = cur  # 이상값이면 현재값 유지

    # 건강지표: 현재 가중치의 판별력(스프레드=승자평균−패자평균, 점수↔손익 순위상관)을
    # 매 실행 로그로 남긴다. 스프레드/상관이 양수로 돌아서는 순간이 '점수 예측력 회복 =
    # 튜닝 재개' 신호다(현재는 음수라 튜닝 실익 없음).
    health = evaluate_weights(dataset, current_weights)
    logger.info(
        f"[건강지표] 현재 가중치 판별력 — 스프레드(승-패)={health['spread']} "
        f"점수↔손익 상관={health['pnl_rank_corr']} "
        f"(승자평균 {health['winner_avg_score']} / 패자평균 {health['loser_avg_score']}, "
        f"표본 {len(dataset)})"
    )

    # backtest 게이팅: 제안이 실제로 판별력을 개선(IMPROVES)할 때만 'pending'(검토·승인 대상).
    # 그 외(WORSENS/NEUTRAL/INSUFFICIENT)는 노이즈 과적합 위험이 커 승인 대상에서 빼되,
    # '튜너가 돌긴 했다'를 대시보드에서 확인할 수 있게 'archived'(비적용)로 저장·표시한다.
    bt = backtest_proposal(dataset, current_weights, proposed_weights)
    improves = bt["verdict"] == "IMPROVES"
    status = "pending" if improves else "archived"

    winners = sum(1 for d in dataset if d["outcome"] == "WIN")
    losers = sum(1 for d in dataset if d["outcome"] == "LOSS")
    total_pnl = sum(d["realized_pnl"] for d in dataset)
    rationale = str(data.get("rationale", "")).strip()

    pid = save_proposal(
        week_start=week_start,
        week_end=week_end,
        sample_count=len(dataset),
        winners_count=winners,
        losers_count=losers,
        total_realized_pnl=total_pnl,
        current_weights=current_weights,
        proposed_weights=proposed_weights,
        rationale=rationale,
        dataset=dataset,
        status=status,
    )
    if improves:
        logger.info(
            f"제안 저장 완료 (id={pid}, status=pending, 승={winners} 패={losers} "
            f"실현손익={total_pnl:,}원). 대시보드에서 검토·승인 필요."
        )
    else:
        logger.info(
            f"제안 저장 완료 (id={pid}, status=archived — 비적용). 판별력 개선 없음"
            f"(verdict={bt['verdict']}, 스프레드Δ={bt['spread_delta']}, 상관Δ={bt['corr_delta']}). "
            f"승인 대상 아님(과적합 방지) — 대시보드에 '동작 여부'로만 표시."
        )


if __name__ == "__main__":
    run()
