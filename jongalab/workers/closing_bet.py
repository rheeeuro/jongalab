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

from core.kiwoom_client import KiwoomRestClient
from core.trading_engine import (
    StrategyConfig,
    SupplyGrade,
    StockCandidate,
    AnalysisEngine,
)
from core.repository.stock_report import save_stock_reports
from core.repository.sector_report import save_sector_reports
from core.repository.content import get_today_content_by_stock
from core.repository.news import get_today_news_count_by_stock, get_today_news_by_stock
from core.repository.trade_signal import push_trade_signals
from core.news_summary import summarize_news

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ClosingBet")

# 뉴스 배치 요약: 언급이 이만큼 이상인 후보만, 한 실행당 최대 이 개수만 LLM 요약(비용 절감)
NEWS_SUMMARY_MIN_COUNT = 3
MAX_NEWS_SUMMARIES = 5

# 실제 매매(trade_signal)로 핸드오프하는 상위 종목 수. 이 수 이하 rank_no 만 selected=1.
# 나머지 후보는 selected=0 으로 '저장만' 한다(엣지 연구용 유니버스). 매매 행위는 불변.
TRADED_TOP_N = 10


class ClosingBetStrategy:
    def __init__(self):
        self.strategy_cfg = StrategyConfig()
        self.strategy_cfg.load_from_db()
        self.api = KiwoomRestClient()
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
                    chg = self.engine.parse_float(info.get("flu_rt", "0"))
                    mc_raw = self.engine.parse_price(info.get("mac", "0"))
                    mc = mc_raw * 100_000_000
                    if mc >= self.strategy_cfg.MIN_MARKET_CAP:
                        # 기본정보(ka10001)엔 거래대금이 없어 일봉(ka10081)에서 별도 조회
                        time.sleep(0.3)
                        tv = self._fetch_trading_value(code)
                        candidates.append(StockCandidate(
                            code=code, name=name, sector=self._find_sector(code),
                            current_price=cp, trading_value=tv,
                            market_cap=mc, change_pct=chg,
                        ))
                        seen_codes.add(code)
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning(f"종목 조회 실패 [{code}]: {e}")

        return candidates

    def _fetch_trading_value(self, code: str) -> int:
        """일봉(ka10081) 최신 캔들의 거래대금(trde_prica, 단위 백만원)을 원 단위로 환산.
        거래대금순위 API와 동일한 단위·환산식(×1,000,000)을 사용한다."""
        try:
            data = self.api.get_daily_chart(code)
            candles = data.get("stk_dt_pole_chart_qry", [])
            if candles:
                return abs(self.engine.parse_price(candles[0].get("trde_prica", "0"))) * 1_000_000
        except Exception as e:
            logger.warning(f"거래대금 조회 실패 [{code}]: {e}")
        return 0

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

            # 프로그램 양매수(순매수 > 0)는 더 이상 필수 조건이 아니다.
            #   필터 대신 score_candidate()의 가산점(SCORE_PROGRAM_BUY_BONUS)으로 반영한다.
            #   프로그램 데이터 조회 실패 시 prog_net_buy=0 → 가산점만 미부여(제외하지 않음).

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
            stock_code_full = c.code.split("_")[0]
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

        # 뉴스 재료 반영 (오늘 관련 뉴스 언급 건수) — 사전매칭 집계, LLM 없음.
        # 종합점수 뉴스 가중치(SCORE_NEWS_BONUS)는 기본 0이라 지금은 점수 무영향(표시·튜닝 전용).
        for c in filtered:
            try:
                c.news_count = get_today_news_count_by_stock(c.code.split("_")[0])
                if c.news_count:
                    logger.info(f"[{c.name}] 뉴스 언급 {c.news_count}건")
            except Exception as e:
                logger.warning(f"뉴스 언급 조회 실패 [{c.name}]: {e}")

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

        # Phase 2 결과를 DB에 저장 — 유니버스 전체 저장(엣지 연구용), 매매는 상위만 핸드오프
        self._save_phase2_reports(filtered)

        return filtered

    # ── Phase 2 결과 저장 ──
    def _save_phase2_reports(self, candidates: list[StockCandidate]):
        """Phase 2 분석 결과를 daily_stock_report 테이블에 저장.

        점수순 정렬된 유니버스 전체를 저장한다(엣지 연구용). rank_no<=TRADED_TOP_N 만
        selected=1 로 표시하고 trade_signal 로 핸드오프한다 — 실제 매매 대상은 불변.
        LLM 뉴스 요약도 선정(top-N) 후보에만 부여해 비용을 종전과 동일하게 유지한다.
        """
        reports = []
        summarized = 0
        for i, c in enumerate(candidates, 1):
            code = c.code.split("_")[0]
            is_selected = 1 if i <= TRADED_TOP_N else 0
            news_count = getattr(c, "news_count", 0)
            if is_selected:
                news_headlines, news_summary = self._build_news_fields(
                    c, code, news_count, summarized
                )
                if news_summary:
                    summarized += 1
            else:
                # 비선정 후보: 헤드라인만(표시·연구용), LLM 요약은 생략
                news_headlines, news_summary = self._build_news_fields(
                    c, code, news_count, MAX_NEWS_SUMMARIES
                )
            reports.append({
                "stock_code": code,
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
                "news_count": news_count,
                "news_summary": news_summary,
                "news_headlines": news_headlines,
                "score": c.score,
                "rank_no": i,
                "selected": is_selected,
            })

        try:
            save_stock_reports(reports)
            logger.info(f"Phase 2 리포트 {len(reports)}건 DB 저장 완료")
        except Exception as e:
            logger.error(f"Phase 2 리포트 DB 저장 실패: {e}")

        # 매수 시그널 핸드오프 — trading 도메인(trade_signal)으로 적재.
        # trading 의 리스크 엔진·사이징이 실제 매수 종목수를 제한하므로 상위 후보를 그대로 넘긴다.
        # 유니버스 전체를 저장하더라도 핸드오프는 selected(top-N)만 — 실제 매매 대상은 불변.
        try:
            signals = [
                {"stk_cd": r["stock_code"], "stk_nm": r["stock_name"],
                 "rank_no": r["rank_no"], "score": r["score"]}
                for r in reports if r["selected"]
            ]
            n = push_trade_signals(datetime.now().strftime("%Y%m%d"), signals)
            logger.info(f"trade_signal 핸드오프 {len(signals)}건 (영향 {n}행)")
        except Exception as e:
            logger.error(f"trade_signal 핸드오프 실패(trading DB 미설정?): {e}")

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
    def _build_news_fields(c: StockCandidate, code: str, news_count: int, summarized: int):
        """뉴스 헤드라인 목록 + (조건 충족 시) 배치 LLM 재료 요약을 만든다.
        반환: (headlines: list[str] | None, summary: str | None)."""
        if news_count <= 0:
            return None, None
        headlines = None
        summary = None
        try:
            items = get_today_news_by_stock(code)
            headlines = [it["headline"] for it in items if it.get("headline")] or None
        except Exception as e:
            logger.warning(f"뉴스 헤드라인 조회 실패 [{c.name}]: {e}")
        if (news_count >= NEWS_SUMMARY_MIN_COUNT and headlines
                and summarized < MAX_NEWS_SUMMARIES):
            try:
                summary = summarize_news(c.name, code, headlines)
                if summary:
                    logger.info(f"[{c.name}] 뉴스 재료 요약 생성")
            except Exception as e:
                logger.warning(f"뉴스 요약 실패 [{c.name}]: {e}")
        return headlines, summary

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
    from core.market_calendar import exit_if_outside_window
    # cron: 0,30 8-20 * * 1-5. 휴장일·운영시간대(08:30~20시, NXT 종료까지) 밖이면 종료.
    # 운영 시작은 08:30 — cron 의 08:00 틱은 분 단위로 한 번 더 막는다(window 헬퍼는 시 단위).
    exit_if_outside_window(8, 20)
    if datetime.now().hour == 8 and datetime.now().minute < 30:
        logger.info("운영 시작(08:30) 전 — 워커를 실행하지 않고 종료합니다.")
        raise SystemExit(0)
    strategy = ClosingBetStrategy()
    strategy.run()
