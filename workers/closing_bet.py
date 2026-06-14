"""
종가베팅 알고리즘 v2.0 — 전략 오케스트레이터
============================================================
[타임라인]
  13:00~14:30  사전 스크리닝 & 시장 분위기 파악
  14:30~15:00  수급 정밀 체크 & 매수 후보 확정
"""

import time
import logging
from datetime import datetime

from core.kiwoom_api import KiwoomConfig, KiwoomRestAPI
from core.trading_engine import (
    StrategyConfig,
    SupplyGrade,
    StockCandidate,
    AnalysisEngine,
)
from core.repository.stock_report import save_stock_reports
from core.repository.sector_report import save_sector_reports
from core.repository.content import get_today_content_by_stock

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ClosingBet")

# 키움 마켓코드 → yfinance 접미사 매핑
KIWOOM_MARKET_SUFFIX = {"001": "KS", "101": "KQ"}


class ClosingBetStrategy:
    def __init__(self):
        self.api_cfg = KiwoomConfig()
        self.strategy_cfg = StrategyConfig()
        self.strategy_cfg.load_from_db()
        self.api = KiwoomRestAPI(self.api_cfg)
        self.engine = AnalysisEngine(self.api, self.strategy_cfg)

    def run(self):
        logger.info("=" * 60)
        logger.info("종가베팅 알고리즘 v2.0 (키움 REST API)")
        logger.info("=" * 60)

        # 0. 인증 — DB 공유 토큰 사용 (없거나 만료 임박이면 자동 갱신)
        self.api.ensure_token()

        # 0-1. 관심 섹터 동적 로드 (ka90001 + ka90002)
        self._fetch_watchlist_sectors()

        # 1. Phase 1 — 사전 스크리닝 (13:00~)
        candidates = self._phase1_screening()
        logger.info(f"Phase 1 완료: {len(candidates)}개 후보")
        logger.info("Phase 1 상위 후보:")
        for i, c in enumerate(candidates[:10], 1):
            logger.info(
                f"  {i:2d}. {c.name:10s} "
                f"등락={c.change_pct:+.1f}%  "
                f"거래대금={c.trading_value/1e8:,.0f}억  섹터={c.sector}"
            )

        # 2. Phase 2 — 수급 정밀 분석 (14:30~)
        candidates = self._phase2_supply_analysis(candidates)
        logger.info(f"Phase 2 완료: {len(candidates)}개 후보")

    # ── Phase 1: 스크리닝 ──
    def _phase1_screening(self) -> list[StockCandidate]:
        candidates = []
        seen_codes = set()

        # (a) 거래대금 TOP N (코스피 + 코스닥)
        for mrkt in ["001", "101"]:
            try:
                data = self.api.get_trading_value_rank(mrkt_tp=mrkt)
                items = data.get("trde_prica_upper", [])
                for item in items[:self.strategy_cfg.TOP_N_BY_VALUE]:
                    code = item.get("stk_cd", "").split("_")[0]
                    name = item.get("stk_nm", "")
                    tv = abs(self.engine.parse_price(item.get("trde_prica", "0"))) * 1_000_000
                    cp = abs(self.engine.parse_price(item.get("cur_prc", "0")))
                    chg = self.engine.parse_float(item.get("flu_rt", "0"))

                    if code in seen_codes:
                        continue

                    # 시가총액은 거래대금순위 API에 없으므로 개별 조회
                    try:
                        info = self.api.get_stock_basic_info(code)
                        mc_raw = self.engine.parse_price(info.get("mac", "0"))
                        mc = mc_raw * 100_000_000
                        time.sleep(0.3)
                    except Exception:
                        mc = 0

                    if not self.engine.filter_basic(name, tv, mc):
                        continue

                    sector = self._find_sector(code)
                    candidates.append(StockCandidate(
                        code=code, name=name, sector=sector,
                        current_price=cp, trading_value=tv,
                        market_cap=mc, change_pct=chg,
                        market_suffix=KIWOOM_MARKET_SUFFIX.get(mrkt, "KS"),
                    ))
                    seen_codes.add(code)
            except Exception as e:
                logger.error(f"거래대금순위 조회 실패 (mrkt={mrkt}): {e}")
            time.sleep(0.3)

        # (b) 관심섹터 종목 보강
        for _, codes in self.strategy_cfg.WATCHLIST_SECTORS.items():
            for raw_code in codes:
                code = raw_code.split("_")[0]
                if code in seen_codes:
                    continue
                try:
                    info = self.api.get_stock_basic_info(code)
                    name = info.get("stk_nm", code)
                    cp = abs(self.engine.parse_price(info.get("cur_prc", "0")))
                    mc_raw = self.engine.parse_price(info.get("mac", "0"))
                    mc = mc_raw * 100_000_000
                    if mc >= self.strategy_cfg.MIN_MARKET_CAP:
                        candidates.append(StockCandidate(
                            code=code, name=name, sector=self._find_sector(code),
                            current_price=cp, market_cap=mc,
                        ))
                        seen_codes.add(code)
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning(f"종목 조회 실패 [{code}]: {e}")

        return candidates

    # ── Phase 2: 수급 분석 ──
    def _phase2_supply_analysis(self, candidates: list[StockCandidate]) -> list[StockCandidate]:
        filtered = []
        
        for c in candidates:
            is_aligned, near_high = self.engine.check_ma_alignment(c.code)
            if not is_aligned and not near_high:
                logger.debug(f"정배열 아님 → 제외: {c.name}")
                continue
            c.ma_aligned = is_aligned
            c.near_high = near_high

            supply = self.engine.analyze_supply_demand(c.code, c.current_price)
            c.inst_net_buy = supply["inst_net_buy"]
            c.frgn_net_buy = supply["frgn_net_buy"]
            c.indv_net_buy = supply["indv_net_buy"]
            c.prog_net_buy = supply["prog_net_buy"]
            c.supply_grade = supply["supply_grade"]
            c.supply_score = supply.get("supply_score", 0.0)
            c.supply_days = supply["supply_days"]
            c.supply_history = supply.get("supply_history", [])

            # 1시간봉 캔들 데이터 조회
            c.hourly_candles = self.engine.fetch_hourly_candles(c.code)
            logger.debug(f"[{c.name}] 1시간봉 {len(c.hourly_candles)}개 수집")

            filtered.append(c)
            time.sleep(0.5)

        filtered = self.engine.identify_sector_leaders(filtered)

        # 오늘의 테마주 여부 마킹
        theme_codes = set()
        for codes in self.strategy_cfg.WATCHLIST_SECTORS.values():
            theme_codes.update(code.split("_")[0] for code in codes)
        for c in filtered:
            c.is_theme_stock = c.code.split("_")[0] in theme_codes

        # 콘텐츠 분석 반영 (오늘 관련 콘텐츠 건수 + 평균 sentiment)
        for c in filtered:
            stock_code_full = f"{c.code.split('_')[0]}.{c.market_suffix}"
            try:
                contents = get_today_content_by_stock(stock_code_full)
                if contents:
                    c.content_count = len(contents)
                    scores = [ct["sentiment_score"] for ct in contents]
                    c.content_avg_score = sum(scores) / len(scores)
                    logger.info(
                        f"[{c.name}] 콘텐츠 분석 {c.content_count}건, "
                        f"평균 감성점수 {c.content_avg_score:.0f}"
                    )
            except Exception as e:
                logger.warning(f"콘텐츠 분석 조회 실패 [{c.name}]: {e}")

        for c in filtered:
            self.engine.score_candidate(c)

        filtered.sort(key=lambda x: x.score, reverse=True)

        logger.info("=" * 60)
        logger.info("Phase 2 결과 (점수순)")
        logger.info("-" * 60)
        for i, c in enumerate(filtered[:10], 1):
            logger.info(
                f"  {i:2d}. [{c.supply_grade.name}] {c.name:10s} "
                f"점수={c.score:.0f}  수급={c.supply_score:.1f}  "
                f"등락={c.change_pct:+.1f}%  "
                f"기관={c.inst_net_buy/1e8:+,.0f}억  "
                f"외인={c.frgn_net_buy/1e8:+,.0f}억  "
                f"{'★대장' if c.is_leader else ''}"
                f"{'🔥테마' if c.is_theme_stock else ''}"
            )

        # Phase 2 결과를 DB에 저장
        self._save_phase2_reports(filtered[:10])

        return filtered

    # ── Phase 2 결과 저장 ──
    def _save_phase2_reports(self, candidates: list[StockCandidate]):
        """Phase 2 분석 결과를 daily_stock_report 테이블에 저장"""
        reports = []
        for i, c in enumerate(candidates, 1):
            reports.append({
                "stock_code": f"{c.code.split('_')[0]}.{c.market_suffix}",
                "stock_name": c.name,
                "sector": c.sector,
                "current_price": c.current_price,
                "change_pct": c.change_pct,
                "trading_value": c.trading_value,
                "market_cap": c.market_cap,
                "supply_score": c.supply_score,
                "inst_net_buy": c.inst_net_buy,
                "frgn_net_buy": c.frgn_net_buy,
                "indv_net_buy": getattr(c, "indv_net_buy", 0),
                "prog_net_buy": c.prog_net_buy,
                "supply_days": c.supply_days,
                "supply_history": c.supply_history,
                "hourly_candles": c.hourly_candles,
                "ma_aligned": c.ma_aligned,
                "near_high": c.near_high,
                "is_leader": c.is_leader,
                "is_theme_stock": c.is_theme_stock,
                "content_score": self._calc_content_score(c),
                "score": c.score,
                "rank_no": i,
            })

        try:
            save_stock_reports(reports)
            logger.info(f"Phase 2 리포트 {len(reports)}건 DB 저장 완료")
        except Exception as e:
            logger.error(f"Phase 2 리포트 DB 저장 실패: {e}")

    # ── 관심 섹터 동적 로드 ──
    def _fetch_watchlist_sectors(self):
        """ka90001(테마그룹) + ka90002(테마구성종목)로 WATCHLIST_SECTORS 동적 구성 & DB 저장"""
        cfg = self.strategy_cfg
        watchlist: dict[str, list[str]] = {}
        sector_reports: list[dict] = []

        try:
            data = self.api.get_theme_groups(
                date_tp=cfg.THEME_PERIOD_DAYS,
                flu_pl_amt_tp="3",
                stex_tp="3",
            )
            themes = data.get("thema_grp", [])
            top_themes = themes[:cfg.TOP_THEME_COUNT]

            for rank, theme in enumerate(top_themes, 1):
                thema_nm = theme.get("thema_nm", "")
                thema_grp_cd = theme.get("thema_grp_cd", "")
                if not thema_nm or not thema_grp_cd:
                    continue

                stocks = []
                try:
                    stock_data = self.api.get_theme_stocks(
                        thema_grp_cd=thema_grp_cd,
                        date_tp=cfg.THEME_PERIOD_DAYS,
                        stex_tp="3",
                    )
                    stocks = stock_data.get("thema_comp_stk", [])
                    codes = [s["stk_cd"] for s in stocks if s.get("stk_cd")]
                    if codes:
                        watchlist[thema_nm] = codes
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning(f"테마 구성종목 조회 실패 [{thema_nm}]: {e}")

                sector_reports.append({
                    "thema_grp_cd": thema_grp_cd,
                    "thema_nm": thema_nm,
                    "stk_num": int(theme.get("stk_num", 0)),
                    "flu_rt": float(theme.get("flu_rt", "0").replace("+", "")),
                    "dt_prft_rt": float(theme.get("dt_prft_rt", "0").replace("+", "")),
                    "main_stk": theme.get("main_stk", ""),
                    "rising_stk_num": int(theme.get("rising_stk_num", 0)),
                    "fall_stk_num": int(theme.get("fall_stk_num", 0)),
                    "rank_no": rank,
                    "stocks": [
                        {
                            "stk_cd": s.get("stk_cd", ""),
                            "stk_nm": s.get("stk_nm", ""),
                            "cur_prc": s.get("cur_prc", "0"),
                            "flu_rt": s.get("flu_rt", "0"),
                        }
                        for s in stocks if s.get("stk_cd")
                    ],
                })

        except Exception as e:
            logger.error(f"테마그룹 조회 실패: {e}")

        # DB 저장
        if sector_reports:
            try:
                save_sector_reports(sector_reports)
                logger.info(f"주도섹터 {len(sector_reports)}개 테마 DB 저장 완료")
            except Exception as e:
                logger.error(f"주도섹터 DB 저장 실패: {e}")

        if watchlist:
            cfg.WATCHLIST_SECTORS = watchlist
            logger.info(f"관심섹터 {len(watchlist)}개 테마 로드 완료:")
            for name, codes in watchlist.items():
                logger.info(f"  {name}: {len(codes)}종목")
        else:
            logger.warning("테마 API 응답 없음 — 관심섹터 보강 없이 진행")

    @staticmethod
    def _calc_content_score(c: StockCandidate) -> float:
        """콘텐츠 분석 점수 계산 (score_candidate 로직과 동일)"""
        if c.content_count <= 0:
            return 0.0
        mention_bonus = min(c.content_count, 3) * 2
        sentiment_bonus = 4 if c.content_avg_score >= 70 else 2 if c.content_avg_score >= 50 else 0
        return min(mention_bonus + sentiment_bonus, 10)

    # ── 유틸 ──
    def _find_sector(self, code: str) -> str:
        code_base = code.split("_")[0]
        try:
            info = self.api.get_stock_detail_info(code_base)
            up_name = info.get("upName", "").strip()
            if up_name:
                return up_name
        except Exception as e:
            logger.warning(f"업종명 조회 실패 [{code_base}]: {e}")
        return "기타"

    def _wait_until(self, time_str: str):
        while True:
            now = datetime.now().strftime("%H:%M")
            if now >= time_str:
                return
            logger.info(f"대기 중... ({now} → {time_str})")
            time.sleep(30)


if __name__ == "__main__":
    from core.market_calendar import exit_if_not_trading_day
    exit_if_not_trading_day()
    strategy = ClosingBetStrategy()
    strategy.run()
