"""선물 환경 게이트 — 매수 시점 선물 방향으로 시드를 축소(KRX·NXT, reduce-only).

[근거] 종가베팅 손익은 '익일 갭'에 좌우된다. 통설: US Tech(NQ 선물)·코스피200 선물이
  하락이면 다음 날 국장 갭하락 리스크가 크다 → 노출을 줄이는 편이 낫다(목표: 잃지 않기 1순위).
  단 섹터마다 지수 민감도가 다르다 — 반도체·IT는 NQ 를 거의 그대로 추종, 경기민감주(자동차·화학·
  기계·금융)는 코스피200 을 따라가고, 통신·음식료 등 방어주는 상대적으로 덜 빠진다. 그래서 하나의
  총-시드 배수 대신 **섹터별 차등 keep-factor** 로 감액한다(고베타 섹터를 더 깎고 방어주는 덜 깎음).
  배수는 항상 ≤1.0(축소 전용) — 상승이어도 베팅을 키우지 않는다.

[지표] 두 축의 전일대비 등락률. 코스피 축은 매수 시점에 '살아있는' 선물을 거래소별로 쓴다:
  · NQ 선물(NQ=F)          — jongalab market-indices(FUTURES 그룹). 양 거래소 공통(≈24h).
  · 코스피200 선물(코스피 축):
      - KRX(15:20): 주간선물(K200DF) — 그 시각 정규장 열려 실시간. market-indices 에서 취득.
      - NXT(19:50): 야간선물(K200NF) — 야간세션(18:00~) 실시간. DB kis_night_future 직접(신선도 체크).
  각 등락률이 **그 축의 σ 로 정규화**해 -FUTURES_FLAT_Z σ 미만이면 '하락'으로 본다
  (밴드 이내 보합·상승은 하락 아님). 절대 %p 밴드를 쓰지 않는 이유는 [감액] 절 참고.
  · US 장 마감 후 최근 등락(NXT 전용) — jongalab /api/us-extended. NXT(19:50)는 미국 프리마켓이
      열려 '정규장 종가 대비 프리마켓 최근 등락'이 순방향 신호(일일 등락은 지난밤이라 이미 국장 종가에
      반영=후행). 반도체 min(SOXX,SKHY)는 tech 만, 한국 min(EWY,KORU/3)은 idx 민감도로 전 섹터에.
      KRX(15:20)는 매수 시점 미국장 완전 폐장(다크)이라 stale → 이 축 미개입(선물 축만).

[감액] 종목 섹터(키움 업종명, jongalab ticker_dictionary)를 클래스로 매핑하고, 클래스별 축당 민감도 ×
  하락 강도로:
    keep = ∏_axis (1 − MAX_CUT_axis × sensitivity × intensity_axis),  하한 MIN_KEEP.
  하락 강도는 **축의 σ 로 정규화한 z**(=|등락|/σ)에 비례한다: z=FLAT_Z 에서 0, z=FULL_Z 에서 1.
  같은 -2%p 가 축마다 전혀 다른 사건이기 때문이다 — 실측 σ 는 주간선물 6.3 / 야간선물 1.6 / NQ 0.9 %p 로
  7배 차이라, 절대 %p 눈금(구 FULL_CUT_PCT=2.0) 하나를 공유하면 주간선물 축은 하락일에 거의 항상
  최대컷(-2%와 -6%를 구분 못함)이고 NQ 축은 최대컷에 도달하지 못했다.
  seed_allocator 배분 뒤 종목 수량에 keep 을 곱해 감액한다(총 노출↓, 배분 로직 자체는 불변).

[안전] 두 지표 중 하나라도 취득 실패(NXT 야간선물은 신선도 FUTURES_STALE_SEC 초과 포함)면 미개입(감액 없음).
  '불확실하면 축소하지 않는다' — 지표를 못 읽은 것이 하락 신호는 아니다.

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
    FUTURES_FLAT_Z,
    FUTURES_FULL_Z,
    FUTURES_SD_NQ,
    FUTURES_SD_K200_DAY,
    FUTURES_SD_K200_NIGHT,
    FUTURES_SD_US_EXT,
    FUTURES_NQ_MAX_CUT,
    FUTURES_IDX_MAX_CUT,
    FUTURES_SECTOR_MIN_KEEP,
    FUTURES_STALE_SEC,
    FUTURES_US_EXT_ENABLED,
    FUTURES_US_EXT_MAX_CUT,
    JONGALAB_BASE_URL,
    SEED_COMBINED_MIN_MULT,
)

logger = logging.getLogger("FuturesGate")

_NQ_SYMBOL = "NQ=F"
_K200_DAY_SYMBOL = "K200DF"   # 코스피200 주간선물 (KRX 15:20 코스피 축)
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


def _market_futures_pct(symbol: str, prefix: str) -> tuple[float | None, str]:
    """jongalab market-indices(FUTURES 그룹)에서 symbol 의 전일대비 % 취득. prefix 는 진단 노트용."""
    try:
        resp = requests.get(f"{JONGALAB_BASE_URL}/api/market-indices", timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        futures = (resp.json() or {}).get("FUTURES") or []
    except Exception as e:
        return None, f"{prefix}_http_error: {e}"
    for item in futures:
        if item.get("symbol") == symbol:
            pct = item.get("change_percent")
            if pct is None:
                return None, f"{prefix}_null"
            return float(pct), "ok"
    return None, f"{prefix}_not_found"


def _nq_pct() -> tuple[float | None, str]:
    """나스닥100 선물 전일대비 % (양 거래소 공통 US Tech 축)."""
    return _market_futures_pct(_NQ_SYMBOL, "nq")


def _min_opt(*vals: float | None) -> float | None:
    """None 을 무시한 최소값(둘 다 None 이면 None). 여러 프록시 중 '가장 약세'를 택해 보수적으로."""
    present = [v for v in vals if v is not None]
    return min(present) if present else None


def _us_ext_signals() -> dict:
    """jongalab /api/us-extended(SOXX·SKHY·EWY·KORU) → 장 마감 후 최근 등락 두 축.

    semis_pct = min(SOXX, SKHY) extended / korea_pct = min(EWY, KORU/3) extended(3x 정규화).
    fresh: 미국장 상태가 프리마켓/정규장이어야 True(NXT 19:50 정상). 애프터/폐장이면 stale →
    소비측이 US 축 미개입. 취득 실패/부재는 None(그 축만 제외)."""
    try:
        resp = requests.get(f"{JONGALAB_BASE_URL}/api/us-extended", timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json() or {}
    except Exception as e:
        return {"semis_pct": None, "korea_pct": None, "fresh": False,
                "market_state": None, "note": f"http_error: {e}"}

    def _ext(sym: str) -> float | None:
        v = (data.get(sym) or {}).get("extended_ret")
        return float(v) if v is not None else None

    koru = _ext("KORU")
    semis = _min_opt(_ext("SOXX"), _ext("SKHY"))
    korea = _min_opt(_ext("EWY"), (koru / 3.0) if koru is not None else None)
    ms = (data.get("SOXX") or {}).get("market_state") or (data.get("EWY") or {}).get("market_state")
    fresh = bool(ms) and (str(ms).startswith("PRE") or str(ms).startswith("REGULAR"))
    return {"semis_pct": semis, "korea_pct": korea, "fresh": fresh,
            "market_state": ms, "note": "ok"}


def _kospi_future_pct(venue: str) -> tuple[float | None, str, str, float]:
    """코스피 축 선물 — 거래소별로 그 시각 살아있는 선물. 반환 (pct, note, label, σ).

    KRX(15:20): 주간선물(K200DF, market-indices 실시간) / NXT(그 외): 야간선물(DB, 신선도 체크).
    두 세션은 변동폭이 4배 차이(σ 6.3 vs 1.6)라 강도 눈금용 σ 도 함께 돌려준다.
    """
    if venue == "krx":
        pct, note = _market_futures_pct(_K200_DAY_SYMBOL, "day")
        return pct, note, "주간선물", FUTURES_SD_K200_DAY
    pct, note = _night_future_pct()
    return pct, note, "야간선물", FUTURES_SD_K200_NIGHT


def _futures_state(venue: str) -> dict:
    """매수 시점 선물 상태 — {ok, nq_pct, kospi_pct, kospi_label, kospi_sd, nq_note, kospi_note}."""
    nq, nq_note = _nq_pct()
    kospi, kospi_note, kospi_label, kospi_sd = _kospi_future_pct(venue)
    return {
        "ok": nq is not None and kospi is not None,
        "nq_pct": nq, "kospi_pct": kospi, "kospi_label": kospi_label, "kospi_sd": kospi_sd,
        "nq_note": nq_note, "kospi_note": kospi_note,
    }


def _bearish(pct: float | None, sd: float) -> bool:
    """등락률이 보합밴드(-FLAT_Z×σ) 아래면 하락으로 센다(감액 발생 여부).

    밴드가 축의 σ 에 비례하므로, 일상 변동폭이 큰 축(주간선물 σ 6.3)에서 -0.5%p 같은
    노이즈가 '하락'으로 세지 않는다 — 절대 %p 밴드(구 0.1)에선 거의 모든 음수가 하락이었다.
    """
    return pct is not None and pct < -FUTURES_FLAT_Z * sd


def _cut_intensity(pct: float | None, sd: float) -> float:
    """하락 강도 0~1 — 축의 σ 로 정규화한 z=|등락|/σ 기준(FLAT_Z 에서 0, FULL_Z 에서 1, 선형).

    같은 -2%p 가 축마다 다른 사건이라 절대 %p 로 재면 눈금이 어긋난다(실측 σ: 주간선물 6.3 /
    야간선물 1.6 / NQ 0.9 → 구 FULL_CUT 2.0 은 각각 0.32σ·1.27σ·2.17σ 로 7배 차이였고,
    주간선물 축은 하락일이면 사실상 항상 최대컷이라 -2%와 -6%를 구분하지 못했다).
    sd<=0 이면 정규화가 불가하므로 미개입(강도 0) — '불확실하면 축소하지 않는다'.
    """
    if sd <= 0 or not _bearish(pct, sd):
        return 0.0
    span = FUTURES_FULL_Z - FUTURES_FLAT_Z
    if span <= 0:
        return 1.0
    return min(1.0, ((-pct / sd) - FUTURES_FLAT_Z) / span)


def _sector_keep(sector: str | None, nq_pct: float | None, kospi_pct: float | None,
                 kospi_sd: float, us_ext: dict | None = None) -> float:
    """섹터 클래스 민감도 × 하락 강도로 keep-factor(≤1.0, 하한 MIN_KEEP) 계산.
    축별 감액 = MAX_CUT × 섹터민감도 × 하락강도(σ 정규화). 상승/보합 축은 감액 0.

    kospi_sd 는 그 시각 쓰는 코스피 선물의 σ(KRX=주간 / NXT=야간) — 두 세션의 변동폭이
    4배 차이라 같은 눈금을 쓸 수 없다.

    us_ext(NXT 전용, 신선할 때만 전달)가 있으면 US 장 마감 후 최근 등락 두 축을 추가로 곱한다:
      · 반도체(semis_pct): tech 클래스만(반도체 ADR/ETF 는 국내 반도체 직결) — 민감도 1.0
      · 한국(korea_pct): 전 섹터, 지수 민감도(idx_s) 재사용(EWY≈코스피 광역)
    """
    cls = _class_of(sector)
    nq_s, idx_s = _SECTOR_SENSITIVITY[cls]
    keep = 1.0
    keep *= (1.0 - FUTURES_NQ_MAX_CUT * nq_s * _cut_intensity(nq_pct, FUTURES_SD_NQ))
    keep *= (1.0 - FUTURES_IDX_MAX_CUT * idx_s * _cut_intensity(kospi_pct, kospi_sd))
    if us_ext:
        semis_s = 1.0 if cls == "tech" else 0.0
        keep *= (1.0 - FUTURES_US_EXT_MAX_CUT * semis_s
                 * _cut_intensity(us_ext.get("semis_pct"), FUTURES_SD_US_EXT))
        keep *= (1.0 - FUTURES_US_EXT_MAX_CUT * idx_s
                 * _cut_intensity(us_ext.get("korea_pct"), FUTURES_SD_US_EXT))
    return round(max(keep, FUTURES_SECTOR_MIN_KEEP), 3)


def gated_shares(shares: int, keep: float) -> int:
    """keep 를 정수 주식 수량에 적용 — **반올림**(내림 아님)한 감액.

    내림(int)이면 mild 한 컷(keep 0.9)도 1주짜리를 0주로 없애버린다(90% 사라 → 0주).
    반올림하면 keep>=0.5 는 최소 1주를 유지하고, 절반 넘게 깎일 때(keep<0.5)만 0 이 될 수 있다.
    keep<=1 이라 결과는 항상 원래 수량 이하(reduce-only 유지).
    """
    if keep >= 1.0:
        return shares
    return int(shares * keep + 0.5)


def effective_keep(keep: float) -> float:
    """결합 하한(SEED_COMBINED_MIN_MULT)을 반영한 실제 적용 keep(≤1.0).

    호출부가 넘기는 keep 은 선물(섹터별)×거시(공통) 곱이다. 두 게이트가 겹쳐도 한 종목의 배수가
    하한 밑으로 내려가지 않게 끌어올린다(keep 은 감액만 하므로 결과는 항상 ≤1.0).
    """
    return round(min(1.0, max(keep, SEED_COMBINED_MIN_MULT)), 3)


def _sectors_for(stk_cds: list[str]) -> dict[str, str | None]:
    """stk_cd(6자리) → 섹터명. jongalab ticker_dictionary 캐시(키움 업종명) 읽기전용 조회.

    ticker_dictionary 는 종목당 **별칭 행이 여러 개**이고 대부분 sector 가 NULL 이다(005930 은 19행 중
    2행만 채워짐). 그래서 종목별로 묶어 **채워진 값 하나**를 고른다 — 행 순서에 맡기면 NULL 행이
    마지막에 걸린 대형주가 neutral 로 떨어져 tech 민감도·US 반도체 축이 통째로 빠진다.
    """
    codes = [c for c in {*stk_cds} if c]
    if not codes:
        return {}
    try:
        with get_jongalab_db() as (conn, cursor):
            ph = ",".join(["%s"] * len(codes))
            cursor.execute(
                f"SELECT ticker_symbol, MAX(NULLIF(sector, '')) AS sector FROM ticker_dictionary "
                f"WHERE ticker_symbol IN ({ph}) GROUP BY ticker_symbol",
                tuple(codes),
            )
            return {r["ticker_symbol"]: r.get("sector") for r in cursor.fetchall()}
    except Exception as e:
        logger.warning("섹터 조회 실패 — 전 종목 neutral 처리: %s", e)
        return {}


def sector_keep_factors(venue: str, stk_cds: list[str]) -> tuple[dict[str, float], dict]:
    """매수 후보(거래소별)에 대한 섹터별 시드 keep-factor(≤1.0) + 진단을 반환.

    게이트 비활성/대상 거래소 아님/지표 취득 실패면 ({}, gated=False) — 감액 없음(미개입).
    성공 시 {stk_cd: keep} (감액 없어도 전 종목 1.0 로 채워 반환) + 섹터별 상세 진단(audit 스냅샷용).
    """
    if not (FUTURES_GATE_ENABLED and FUTURES_SECTOR_GATE_ENABLED):
        return {}, {"gated": False, "reason": "disabled"}
    if venue not in FUTURES_GATE_VENUES:
        return {}, {"gated": False, "reason": f"venue_skip({venue})"}

    st = _futures_state(venue)
    if not st["ok"]:
        logger.info("선물 지표 취득 실패 — 게이트 미개입: nq=%s %s=%s",
                    st["nq_note"], st["kospi_label"], st["kospi_note"])
        return {}, {"gated": False, "reason": "unavailable", "venue": venue,
                    "kospi_label": st["kospi_label"],
                    "nq_note": st["nq_note"], "kospi_note": st["kospi_note"]}

    # US 장 마감 후 최근 등락 축 — NXT(매수 시점 미국 프리마켓 열림) 전용, 신선할 때만.
    # KRX(15:20)는 미국장 완전 폐장이라 stale → 미개입(선물 축만).
    us_ext = None
    us_diag: dict = {"applied": False}
    if FUTURES_US_EXT_ENABLED and venue == "nxt":
        sig = _us_ext_signals()
        us_diag = {"applied": False, "semis_pct": sig["semis_pct"], "korea_pct": sig["korea_pct"],
                   "market_state": sig["market_state"], "fresh": sig["fresh"],
                   "note": sig["note"]}
        if sig["fresh"] and (sig["semis_pct"] is not None or sig["korea_pct"] is not None):
            us_ext = sig
            us_diag["applied"] = True

    sectors = _sectors_for(stk_cds)
    nq, kospi, kospi_sd = st["nq_pct"], st["kospi_pct"], st["kospi_sd"]
    factors: dict[str, float] = {}
    detail: dict[str, dict] = {}
    for code in stk_cds:
        sec = sectors.get(code)
        keep = _sector_keep(sec, nq, kospi, kospi_sd, us_ext)
        factors[code] = keep
        detail[code] = {"sector": sec, "class": _class_of(sec), "keep": keep}

    # 축별 σ·강도를 스냅샷에 남긴다 — σ 재측정으로 눈금을 다시 튜닝할 때 그날 어떤 눈금이
    # 적용됐는지가 있어야 소급 재계산이 된다(구 payload 의 flat_band 를 대체).
    axes = {
        "nq": {"pct": round(nq, 3), "sd": FUTURES_SD_NQ,
               "intensity": round(_cut_intensity(nq, FUTURES_SD_NQ), 3)},
        "kospi": {"pct": round(kospi, 3), "sd": kospi_sd,
                  "intensity": round(_cut_intensity(kospi, kospi_sd), 3)},
    }
    if us_ext:
        axes["us_semis"] = {"pct": us_ext.get("semis_pct"), "sd": FUTURES_SD_US_EXT,
                            "intensity": round(_cut_intensity(us_ext.get("semis_pct"),
                                                              FUTURES_SD_US_EXT), 3)}
        axes["us_korea"] = {"pct": us_ext.get("korea_pct"), "sd": FUTURES_SD_US_EXT,
                            "intensity": round(_cut_intensity(us_ext.get("korea_pct"),
                                                              FUTURES_SD_US_EXT), 3)}

    diag = {
        "gated": True, "venue": venue, "kospi_label": st["kospi_label"],
        "nq_pct": round(nq, 3), "kospi_pct": round(kospi, 3),
        "nq_down": _bearish(nq, FUTURES_SD_NQ), "kospi_down": _bearish(kospi, kospi_sd),
        "flat_z": FUTURES_FLAT_Z, "full_z": FUTURES_FULL_Z, "axes": axes,
        "us_ext": us_diag, "detail": detail,
    }
    logger.info("선물 섹터 게이트[%s]: NQ %+.2f%%(강도 %.2f) / %s %+.2f%%(강도 %.2f, σ %.1f)"
                " → %d종목 keep 계산",
                venue, nq, axes["nq"]["intensity"], st["kospi_label"], kospi,
                axes["kospi"]["intensity"], kospi_sd, len(factors))
    return factors, diag
