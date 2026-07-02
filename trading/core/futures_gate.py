"""선물 환경 게이트 — 매수 시점 선물 방향으로 시드를 축소(NXT 전용, reduce-only).

[근거] 종가베팅 손익은 '익일 갭'에 좌우된다. 통설: US Tech(NQ 선물)·코스피200 야간선물이
  하락이면 다음 날 국장 갭하락 리스크가 크다 → 노출을 줄이는 편이 낫다(목표: 잃지 않기 1순위).
  단 섹터마다 지수 민감도가 다르다 — 반도체·IT는 NQ 를 거의 그대로 추종, 경기민감주(자동차·화학·
  기계·금융)는 코스피200 을 따라가고, 통신·음식료 등 방어주는 상대적으로 덜 빠진다. 그래서 하나의
  총-시드 배수 대신 **섹터별 차등 keep-factor** 로 감액한다(고베타 섹터를 더 깎고 방어주는 덜 깎음).
  배수는 항상 ≤1.0(축소 전용) — 상승이어도 베팅을 키우지 않는다.

[지표] 매수 시점(19:50 NXT)에 살아있는 두 선물의 전일대비 등락률:
  · NQ 선물(NQ=F)      — jongalab market-indices 엔드포인트(FUTURES 그룹)
  · 코스피200 야간선물  — jongalab DB kis_night_future 단일행(야간세션 중 실시간 갱신) 직접 조회
  각 등락률이 -FUTURES_FLAT_BAND %p 미만이면 '하락'으로 본다(±band 이내 보합·상승은 하락 아님).

[감액] 종목 섹터(키움 업종명, jongalab ticker_dictionary)를 클래스로 매핑하고, 클래스별 축당 민감도로:
    keep = ∏_axis (1 − MAX_CUT_axis × sensitivity)   (해당 축이 하락일 때만, 아니면 ×1),  하한 MIN_KEEP.
  seed_allocator 등가중 배분 뒤 각 종목 수량에 keep 을 곱해 감액한다(총 노출↓, 배분 로직 자체는 불변).

[안전] 두 지표 중 하나라도 취득 실패·야간선물 신선도 초과(FUTURES_STALE_SEC)면 미개입(감액 없음).
  regime_gate 와 동일하게 '불확실하면 축소하지 않는다'.

⚠️ 섹터별 민감도(_SECTOR_SENSITIVITY)는 **통설 기반 미검증 가정**이다(시점별 선물 이력 부재·손익 표본
  부족). 매 적용을 audit_log('futures_gate') 에 선물값+섹터별 keep 으로 남겨, 추후 stk_cd→섹터 조인으로
  섹터×선물 실측 회귀 후 민감도/컷을 재튜닝한다. → [[futures-gate-unverified]]
"""
import logging

import requests

from core.db import get_jongalab_db
from core.config import (
    FUTURES_GATE_ENABLED,
    FUTURES_SECTOR_GATE_ENABLED,
    FUTURES_GATE_VENUES,
    FUTURES_FLAT_BAND,
    FUTURES_NQ_MAX_CUT,
    FUTURES_IDX_MAX_CUT,
    FUTURES_SECTOR_MIN_KEEP,
    FUTURES_STALE_SEC,
    JONGALAB_BASE_URL,
    SEED_COMBINED_MIN_MULT,
)

logger = logging.getLogger("FuturesGate")

_NQ_SYMBOL = "NQ=F"
_HTTP_TIMEOUT = 5

# 섹터 클래스별 (NQ 민감도, 코스피200 야간선물 민감도) — 0~1. 통설 기반 가정(미검증).
#   tech: 반도체·IT — NQ 추종 강, 지수도 큼 / cyclical: 경기민감 — 지수 추종 강
#   financial: 금리·지수 민감 / defensive: 방어주 — 둘 다 약 / indep: 개별재료 주도 — 약 / neutral: 미분류 기본
_SECTOR_SENSITIVITY = {
    "tech":      (1.0, 0.5),
    "cyclical":  (0.3, 1.0),
    "financial": (0.2, 0.8),
    "defensive": (0.2, 0.3),
    "indep":     (0.2, 0.3),
    "neutral":   (0.4, 0.6),
}

# 키움 업종명(ticker_dictionary.sector) → 클래스. 미매핑/None 은 neutral.
_SECTOR_CLASS = {
    "전기/전자": "tech", "IT 서비스": "tech", "IT서비스": "tech",
    "운송장비/부품": "cyclical", "화학": "cyclical", "금속": "cyclical", "비금속": "cyclical",
    "기계/장비": "cyclical", "건설": "cyclical", "철강": "cyclical", "조선": "cyclical",
    "금융": "financial", "보험": "financial", "증권": "financial", "은행": "financial",
    "통신": "defensive", "음식료품": "defensive", "음식료·담배": "defensive",
    "전기가스": "defensive", "전기·가스업": "defensive", "유통": "defensive",
    "제약": "indep", "의료/정밀기기": "indep", "일반서비스": "indep", "운송/창고": "indep",
}


def _class_of(sector: str | None) -> str:
    return _SECTOR_CLASS.get((sector or "").strip(), "neutral")


def _night_future_pct() -> tuple[float | None, str]:
    """코스피200 야간선물 전일대비 %(신선하면). 신선도는 DB NOW() 기준으로 계산(tz 불일치 회피)."""
    try:
        with get_jongalab_db() as (conn, cursor):
            cursor.execute(
                "SELECT change_percent, TIMESTAMPDIFF(SECOND, updated_at, NOW()) AS age_sec "
                "FROM kis_night_future WHERE id = 1"
            )
            row = cursor.fetchone()
    except Exception as e:
        return None, f"night_query_error: {e}"
    if not row or row.get("change_percent") is None:
        return None, "night_no_row"
    age = int(row.get("age_sec") or 0)
    if age > FUTURES_STALE_SEC:
        return None, f"night_stale({age}s)"
    return float(row["change_percent"]), "ok"


def _nq_pct() -> tuple[float | None, str]:
    """나스닥100 선물 전일대비 % — jongalab market-indices(FUTURES 그룹)에서 취득."""
    try:
        resp = requests.get(f"{JONGALAB_BASE_URL}/api/market-indices", timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        futures = (resp.json() or {}).get("FUTURES") or []
    except Exception as e:
        return None, f"nq_http_error: {e}"
    for item in futures:
        if item.get("symbol") == _NQ_SYMBOL:
            pct = item.get("change_percent")
            if pct is None:
                return None, "nq_null"
            return float(pct), "ok"
    return None, "nq_not_found"


def _futures_state() -> dict:
    """매수 시점 선물 상태 — {ok, nq_pct, night_pct, nq_note, night_note}. 하나라도 없으면 ok=False."""
    nq, nq_note = _nq_pct()
    night, night_note = _night_future_pct()
    return {
        "ok": nq is not None and night is not None,
        "nq_pct": nq, "night_pct": night,
        "nq_note": nq_note, "night_note": night_note,
    }


def _bearish(pct: float | None) -> bool:
    """등락률이 보합밴드(-FUTURES_FLAT_BAND) 아래면 하락으로 센다."""
    return pct is not None and pct < -FUTURES_FLAT_BAND


def _sector_keep(sector: str | None, nq_pct: float | None, night_pct: float | None) -> float:
    """섹터 클래스 민감도로 keep-factor(≤1.0, 하한 MIN_KEEP) 계산. 하락 축에만 감액."""
    nq_s, idx_s = _SECTOR_SENSITIVITY[_class_of(sector)]
    keep = 1.0
    if _bearish(nq_pct):
        keep *= (1.0 - FUTURES_NQ_MAX_CUT * nq_s)
    if _bearish(night_pct):
        keep *= (1.0 - FUTURES_IDX_MAX_CUT * idx_s)
    return round(max(keep, FUTURES_SECTOR_MIN_KEEP), 3)


def effective_keep(keep: float, regime_mult: float) -> float:
    """레짐×선물 결합 배수 하한(SEED_COMBINED_MIN_MULT)을 반영한 실제 적용 keep(≤1.0).

    한 종목의 최종 배수 = regime_mult × keep. 이게 하한 밑으로 내려가지 않게 keep 을 끌어올린다
    (keep 은 감액만 하므로 결과는 항상 ≤1.0). regime_mult >= 하한이면 결합 배수 >= 하한이 보장된다.
    """
    if regime_mult and regime_mult > 0:
        keep = max(keep, SEED_COMBINED_MIN_MULT / regime_mult)
    return round(min(1.0, keep), 3)


def _sectors_for(stk_cds: list[str]) -> dict[str, str | None]:
    """stk_cd(6자리) → 섹터명. jongalab ticker_dictionary 캐시(키움 업종명) 읽기전용 조회."""
    codes = [c for c in {*stk_cds} if c]
    if not codes:
        return {}
    try:
        with get_jongalab_db() as (conn, cursor):
            ph = ",".join(["%s"] * len(codes))
            cursor.execute(
                f"SELECT ticker_symbol, sector FROM ticker_dictionary WHERE ticker_symbol IN ({ph})",
                tuple(codes),
            )
            return {r["ticker_symbol"]: r.get("sector") for r in cursor.fetchall()}
    except Exception as e:
        logger.warning("섹터 조회 실패 — 전 종목 neutral 처리: %s", e)
        return {}


def sector_keep_factors(venue: str, stk_cds: list[str]) -> tuple[dict[str, float], dict]:
    """NXT 매수 후보에 대한 섹터별 시드 keep-factor(≤1.0) + 진단을 반환.

    게이트 비활성/대상 거래소 아님/지표 취득 실패면 ({}, gated=False) — 감액 없음(미개입).
    성공 시 {stk_cd: keep} (감액 없어도 전 종목 1.0 로 채워 반환) + 섹터별 상세 진단(audit 스냅샷용).
    """
    if not (FUTURES_GATE_ENABLED and FUTURES_SECTOR_GATE_ENABLED):
        return {}, {"gated": False, "reason": "disabled"}
    if venue not in FUTURES_GATE_VENUES:
        return {}, {"gated": False, "reason": f"venue_skip({venue})"}

    st = _futures_state()
    if not st["ok"]:
        logger.info("선물 지표 취득 실패 — 게이트 미개입: nq=%s night=%s", st["nq_note"], st["night_note"])
        return {}, {"gated": False, "reason": "unavailable",
                    "nq_note": st["nq_note"], "night_note": st["night_note"]}

    sectors = _sectors_for(stk_cds)
    nq, night = st["nq_pct"], st["night_pct"]
    factors: dict[str, float] = {}
    detail: dict[str, dict] = {}
    for code in stk_cds:
        sec = sectors.get(code)
        keep = _sector_keep(sec, nq, night)
        factors[code] = keep
        detail[code] = {"sector": sec, "class": _class_of(sec), "keep": keep}

    diag = {
        "gated": True, "venue": venue,
        "nq_pct": round(nq, 3), "night_pct": round(night, 3),
        "nq_down": _bearish(nq), "night_down": _bearish(night),
        "flat_band": FUTURES_FLAT_BAND, "detail": detail,
    }
    logger.info("선물 섹터 게이트[%s]: NQ %+.2f%%(하락=%s) / 야간선물 %+.2f%%(하락=%s) → %d종목 keep 계산",
                venue, nq, _bearish(nq), night, _bearish(night), len(factors))
    return factors, diag
