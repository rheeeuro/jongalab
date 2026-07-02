"""롤링 엣지 게이트 — 최근 종가베팅 선정 종목의 '점수 판별력'으로 총 시드 비중을 조절.

[근거] 종가베팅 엣지는 레짐 의존적이다(2026 봄엔 고점수 종목이 익일 잘 갔으나 6월엔 역전 —
고점수가 오히려 더 밀림). 선정이 역전된 구간엔 자본을 덜 실어 손실을 줄인다(목표: 잃지 않기 1순위).
사이징은 등가중이라 조절 대상은 '개별 비중'이 아니라 **총 노출(seed)** — 역전이면 seed 자체를 축소한다.

[지표] split = 최근 REGIME_WINDOW_DAYS 거래일 selected 종목의
    (점수 상위½ 평균 next_open_ret) − (점수 하위½ 평균 next_open_ret)   단위 %p
  양수 = 점수가 승자/패자를 잘 가름(건강), 음수 = 역전.

[배수] split >= REGIME_SPLIT_FULL → 1.0(정상) / split <= REGIME_SPLIT_INVERT → REGIME_MIN_MULT(역전)
  그 사이는 선형. 표본 < REGIME_MIN_SAMPLES 이면 판단 보류 → 1.0(게이트 미개입).

next_open_ret 은 jongalab outcome_backfill 워커가 채운다(리포트일 종가→다음 거래일 시가 등락률).
읽기 전용으로 jongalab DB 를 조회한다.
"""
import logging

from core.db import get_jongalab_db
from core.config import (
    REGIME_GATE_ENABLED,
    REGIME_WINDOW_DAYS,
    REGIME_MIN_SAMPLES,
    REGIME_SPLIT_FULL,
    REGIME_SPLIT_INVERT,
    REGIME_MIN_MULT,
)

logger = logging.getLogger("RegimeGate")


def _recent_samples(window: int) -> list[dict]:
    """최근 window 거래일(next_open_ret 확정분) 의 selected 종목 (score, next_open_ret)."""
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            """SELECT DISTINCT report_date FROM daily_stock_report
                WHERE selected = 1 AND next_open_ret IS NOT NULL
                ORDER BY report_date DESC LIMIT %s""",
            (window,),
        )
        dates = [r["report_date"] for r in cursor.fetchall()]
        if not dates:
            return []
        ph = ",".join(["%s"] * len(dates))
        cursor.execute(
            f"""SELECT score, next_open_ret FROM daily_stock_report
                 WHERE selected = 1 AND next_open_ret IS NOT NULL
                   AND report_date IN ({ph})""",
            tuple(dates),
        )
        return cursor.fetchall()


def _score_split(samples: list[dict]) -> float:
    """점수 상위½ 평균수익 − 하위½ 평균수익 (%p)."""
    pairs = sorted(
        ((float(s["score"] or 0), float(s["next_open_ret"])) for s in samples),
        key=lambda p: p[0],
    )
    h = len(pairs) // 2
    lo = pairs[:h]
    hi = pairs[-h:]
    lo_avg = sum(y for _, y in lo) / len(lo)
    hi_avg = sum(y for _, y in hi) / len(hi)
    return hi_avg - lo_avg


def _split_to_mult(split: float) -> float:
    """점수 스프레드(%p) → 시드 배수. INVERT..FULL 을 MIN_MULT..1.0 으로 선형 클램프."""
    if split >= REGIME_SPLIT_FULL:
        return 1.0
    if split <= REGIME_SPLIT_INVERT:
        return REGIME_MIN_MULT
    frac = (split - REGIME_SPLIT_INVERT) / (REGIME_SPLIT_FULL - REGIME_SPLIT_INVERT)
    return round(REGIME_MIN_MULT + frac * (1.0 - REGIME_MIN_MULT), 3)


def seed_multiplier() -> tuple[float, dict]:
    """총 시드에 곱할 레짐 배수(REGIME_MIN_MULT~1.0) + 진단 정보를 반환.

    게이트 비활성/표본부족이면 1.0(미개입). 로깅·감사용 진단 dict 동봉.
    """
    if not REGIME_GATE_ENABLED:
        return 1.0, {"gated": False, "reason": "disabled"}
    try:
        samples = _recent_samples(REGIME_WINDOW_DAYS)
    except Exception as e:
        logger.warning("레짐 표본 조회 실패 — 게이트 미개입(1.0): %s", e)
        return 1.0, {"gated": False, "reason": f"query_error: {e}"}

    n = len(samples)
    if n < REGIME_MIN_SAMPLES:
        logger.info("레짐 표본 부족(%d < %d) — 게이트 미개입(1.0)", n, REGIME_MIN_SAMPLES)
        return 1.0, {"gated": False, "reason": "insufficient", "n": n}

    split = _score_split(samples)
    mult = _split_to_mult(split)
    diag = {"gated": True, "n": n, "split": round(split, 3), "multiplier": mult,
            "inverted": split < 0}
    logger.info("레짐 게이트: 표본 %d, 점수스프레드 %+.3f%%p → 시드배수 %.3f%s",
                n, split, mult, " (역전)" if split < 0 else "")
    return mult, diag
