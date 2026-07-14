"""롤링 엣지 게이트 — 최근 종가베팅 선정 종목의 '점수 판별력'으로 총 시드 비중을 조절.

[근거] 종가베팅 엣지는 레짐 의존적이다(2026 봄엔 고점수 종목이 익일 잘 갔으나 6월엔 역전 —
고점수가 오히려 더 밀림). 선정이 역전된 구간엔 자본을 덜 실어 손실을 줄인다(목표: 잃지 않기 1순위).
사이징은 등가중이라 조절 대상은 '개별 비중'이 아니라 **총 노출(seed)** — 역전이면 seed 자체를 축소한다.

[지표] split = 최근 REGIME_WINDOW_DAYS 거래일 selected 종목의
    (점수 상위½ 평균 next_open_ret) − (점수 하위½ 평균 next_open_ret)   단위 %p
  양수 = 점수가 승자/패자를 잘 가름(건강), 음수 = 역전.

[배수] 이진: split < REGIME_INVERT_THRESHOLD(기본 0) → REGIME_MIN_MULT / 아니면 1.0.
  근거(2026-07-14 백테스트, 4/9~7/10 60판단일): 역전 '깊이'는 다음날 성적과 무상관
  (mult 0.3 바닥일 평균 +0.36% > 약한 축소일 −0.18%) — 부호만 유효해 선형 램프를 이진으로 대체.
  거래일 < REGIME_MIN_DAYS 면 판단 보류 → 1.0(미개입). 종목-일 수가 아니라 거래일 수 기준 —
  같은 날 표본은 시장 무브로 상관되어 거래일이 실효 표본이다(edge_policy PROMO_MIN_DAYS 와 동일 논리).

next_open_ret 은 jongalab outcome_backfill 워커가 채운다(리포트일 종가→다음 거래일 시가 등락률).
읽기 전용으로 jongalab DB 를 조회한다.
"""
import logging

from core.db import get_jongalab_db
from core.config import (
    REGIME_GATE_ENABLED,
    REGIME_WINDOW_DAYS,
    REGIME_MIN_DAYS,
    REGIME_INVERT_THRESHOLD,
    REGIME_MIN_MULT,
    REGIME_MIN_DATE,
)

logger = logging.getLogger("RegimeGate")


def _recent_samples(window: int) -> tuple[list[dict], int]:
    """최근 window 거래일(next_open_ret 확정분)의 selected 종목 (score, next_open_ret) + 거래일 수."""
    with get_jongalab_db() as (conn, cursor):
        # report_date >= REGIME_MIN_DATE 만 대상 — 그 이전은 구 스코어 로직이라 판별력 비교 무의미.
        cursor.execute(
            """SELECT DISTINCT report_date FROM daily_stock_report
                WHERE selected = 1 AND next_open_ret IS NOT NULL
                  AND report_date >= %s
                ORDER BY report_date DESC LIMIT %s""",
            (REGIME_MIN_DATE, window),
        )
        dates = [r["report_date"] for r in cursor.fetchall()]
        if not dates:
            return [], 0
        ph = ",".join(["%s"] * len(dates))
        cursor.execute(
            f"""SELECT score, next_open_ret FROM daily_stock_report
                 WHERE selected = 1 AND next_open_ret IS NOT NULL
                   AND report_date IN ({ph})""",
            tuple(dates),
        )
        return cursor.fetchall(), len(dates)


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
    """점수 스프레드(%p) → 시드 배수. 이진: 역전이면 MIN_MULT, 아니면 1.0."""
    return REGIME_MIN_MULT if split < REGIME_INVERT_THRESHOLD else 1.0


def seed_multiplier() -> tuple[float, dict]:
    """총 시드에 곱할 레짐 배수(REGIME_MIN_MULT 또는 1.0) + 진단 정보를 반환.

    게이트 비활성/거래일 부족이면 1.0(미개입). 로깅·감사용 진단 dict 동봉.
    """
    if not REGIME_GATE_ENABLED:
        return 1.0, {"gated": False, "reason": "disabled"}
    try:
        samples, n_days = _recent_samples(REGIME_WINDOW_DAYS)
    except Exception as e:
        logger.warning("레짐 표본 조회 실패 — 게이트 미개입(1.0): %s", e)
        return 1.0, {"gated": False, "reason": f"query_error: {e}"}

    n = len(samples)
    if n_days < REGIME_MIN_DAYS:
        logger.info("레짐 거래일 부족(%d < %d일, %s 이후만) — 게이트 미개입(1.0)",
                    n_days, REGIME_MIN_DAYS, REGIME_MIN_DATE)
        return 1.0, {"gated": False, "reason": "insufficient_days",
                     "n": n, "n_days": n_days, "since": REGIME_MIN_DATE}

    split = _score_split(samples)
    mult = _split_to_mult(split)
    diag = {"gated": True, "n": n, "n_days": n_days, "split": round(split, 3),
            "multiplier": mult, "inverted": split < REGIME_INVERT_THRESHOLD}
    logger.info("레짐 게이트: 거래일 %d(표본 %d), 점수스프레드 %+.3f%%p → 시드배수 %.3f%s",
                n_days, n, split, mult, " (역전)" if diag["inverted"] else "")
    return mult, diag
