"""상장종목 사전 시딩 워커 (주 1회 + 등록 시 즉시 1회).

뉴스 헤드라인 사전매칭(core.news_matcher)이 전 상장사를 커버하도록, 키움 ka10099(종목정보
리스트, 코스피/코스닥)를 ticker_dictionary 에 ACTIVE 로 업서트한다. ETF/ETN 등 지수상품은
매칭 노이즈만 되므로 제외한다.

기존 온라인 검색(core.ticker.get_tickers) 경로는 그대로 두고, 이 워커는 사전 커버리지만 높인다.
"""
import logging
import re
import sys

from core.logging_setup import setup_logging
from core.kiwoom_client import KiwoomRestClient
from core.repository import bulk_upsert_active_tickers

setup_logging()
logger = logging.getLogger("NewsTickerSeed")

# 매칭 노이즈가 되는 지수상품 사명 키워드 (종가베팅 EXCLUDE_KEYWORDS 와 동일 취지)
EXCLUDE_KEYWORDS = ["ETF", "ETN", "KODEX", "TIGER", "KBSTAR", "ARIRANG",
                    "SOL", "HANARO", "RISE", "PLUS", "ACE"]
MARKETS = {"0": "코스피", "10": "코스닥"}
_CODE_RE = re.compile(r"(\d{6})")


def _is_excluded(name: str) -> bool:
    upper = name.upper()
    return any(kw in upper for kw in EXCLUDE_KEYWORDS)


def _normalize_code(raw: str) -> str | None:
    m = _CODE_RE.search(raw or "")
    return m.group(1) if m else None


def run() -> int:
    api = KiwoomRestClient()
    rows: list[dict] = []
    seen: set[str] = set()

    for mrkt_tp, label in MARKETS.items():
        try:
            data = api.get_stock_list(mrkt_tp=mrkt_tp)
        except Exception as e:
            logger.error(f"[{label}] 종목리스트 조회 실패: {e}")
            continue

        items = data.get("list") or []
        kept = 0
        for it in items:
            name = (it.get("name") or "").strip()
            code = _normalize_code(it.get("code") or "")
            if not name or not code or code in seen:
                continue
            if _is_excluded(name):
                continue
            seen.add(code)
            rows.append({"company_name": name, "ticker_symbol": code})
            kept += 1
        logger.info(f"[{label}] {len(items)}개 중 {kept}개 채택")

    if not rows:
        logger.warning("시딩할 종목이 없음 — 키움 응답 확인 필요")
        return 1

    affected = bulk_upsert_active_tickers(rows)
    logger.info(f"종목 사전 시딩 완료: {len(rows)}개 업서트 (영향 {affected}행)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
