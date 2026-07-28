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
from core.config import EDGE_SELECTION_MODE
from core.edge_features import (
    afternoon_ret, days_since_frgn_surge, dist_prior_high_pct, financials, is_bio,
    ma5_reclaim, op_earnings_yield, order_book_features, overhead_vol_ratio, poc_dist_pct,
    prog_buy_days, prog_cum_net, red_candle, red_candle_streak, round_dist_pct, vol_ratio,
)
from core.repository.stock_report import (
    save_stock_reports,
    get_recent_report_codes,
    get_prev_frgn_exhaust_map,
    get_today_prog_am_map,
)
from core.repository.sector_report import save_sector_reports
from core.repository.content import get_today_content_by_stock
from core.repository.news import get_today_news_stats_by_stock, get_today_news_by_stock
from core.repository.stock_event import get_events_by_date
from core.disclosure_events import summarize as summarize_disclosures
from core.repository.trade_signal import push_trade_signals
from core.repository.edge_rule import list_rules
from core.edge_selection import select_signals
from core.edge_policy import rule_role
from core.news_summary import summarize_news
from core.notifications import send_report_save_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ClosingBet")

# 뉴스 배치 요약: 언급이 이만큼 이상인 후보만, 한 실행당 최대 이 개수만 LLM 요약(비용 절감)
NEWS_SUMMARY_MIN_COUNT = 3
MAX_NEWS_SUMMARIES = 5

# 실제 매매(trade_signal)로 핸드오프하는 최대 종목 수.
# Phase 2 유니버스는 전체 저장하고, 선정 레이어가 음전 후보를 제외한 뒤 selected 를 확정한다.
TRADED_TOP_N = 10


class ClosingBetStrategy:
    def __init__(self):
        self.strategy_cfg = StrategyConfig()
        self.strategy_cfg.load_from_db()
        self.api = KiwoomRestClient()
        self.engine = AnalysisEngine(self.api, self.strategy_cfg)
        # 종목코드 → 뉴스 연구 라벨(get_today_news_stats_by_stock 결과).
        # StockCandidate(가드 파일)를 건드리지 않고 Phase 2 → 리포트 저장으로 전달한다.
        self._news_stats: dict[str, dict] = {}
        # 종목코드 → 당일 공시 라벨(core.disclosure_events.summarize 결과).
        # disclosure_collector 가 적재한 stock_event 를 선정 시점에 집계한 것. 위와 같은 전달 패턴.
        self._disc_stats: dict[str, dict] = {}
        # 종목코드 → F5 수급 구조 피처(외국계 거래원·오후 강세·거래량 배율·프로그램 연속·외인소진율).
        # 이미 조회 중인 키움 응답에서 캡처해 저장만 한다(점수 무영향) — 위와 같은 전달 패턴.
        self._feat: dict[str, dict] = {}
        # 종목코드 → 소속 테마 당일 등락률 최대값(_fetch_watchlist_sectors 에서 구축)
        self._theme_strength: dict[str, float] = {}
        # 종목코드 → 시장 구분(코스피/코스닥) — _find_sector 의 ka10100 응답에서 함께 캡처
        # (추가 API 콜 없음). veto_bio_kosdaq rule 이 daily_stock_report.market 으로 참조한다.
        self._market: dict[str, str] = {}
        # 종목코드 → 정오 창 실행이 저장해 둔 프로그램 누적 순매수(prog_am_net) —
        # 오후 실행이 prog_pm_net(현재 누적 − 정오 누적) 차분에 사용. 실패해도 피처만 결측.
        try:
            self._prog_am_map: dict[str, int] = get_today_prog_am_map()
        except Exception as e:
            logger.warning(f"정오 프로그램 스냅샷 로드 실패: {e}")
            self._prog_am_map = {}
        # 거래대금 순위 API에서 시장별 TOP_N_BY_VALUE 안에 들어온 종목.
        # 테마 보너스는 이 유동성 상위권과 교차할 때만 부여한다.
        self._top_value_codes: set[str] = set()
        # ETF/ETN 상장 코드 셋(_load_excluded_codes 에서 구축) — 이름 키워드(EXCLUDE_KEYWORDS)는
        # 운용사 리브랜딩(예: ARIRANG→PLUS)에 뚫리므로 코드 기반 제외가 1차, 키워드는 백업.
        self._excluded_codes: set[str] = set()

    def run(self):
        logger.info("=" * 60)
        logger.info("종가베팅 알고리즘 v2.0 (키움 REST API)")
        logger.info("=" * 60)

        # 0. 인증 — DB 공유 토큰 사용 (없거나 만료 임박이면 자동 갱신)
        self.api.ensure_token()

        # 0-1. 관심 섹터 동적 로드 (ka90001 + ka90002)
        self._fetch_watchlist_sectors()

        # 0-2. ETF/ETN 상장 코드 셋 로드 (ka10099) — 유니버스 제외용
        self._load_excluded_codes()

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

    # ── ETF/ETN 제외 코드 셋 ──
    def _load_excluded_codes(self):
        """ka10099 종목정보 리스트로 ETF/ETN 계열 상장 코드 전체를 수집한다.

        mrkt_tp — 8: ETF, 60: ETN, 70: 손실제한 ETN, 90: 변동성 ETN.
        조회 실패 시 경고만 남기고 계속한다(filter_basic 의 이름 키워드가 백업으로 동작).
        """
        for mrkt_tp, label in (("8", "ETF"), ("60", "ETN"),
                               ("70", "손실제한 ETN"), ("90", "변동성 ETN")):
            try:
                data = self.api.get_stock_list(mrkt_tp=mrkt_tp)
                codes = {item.get("code", "").split("_")[0]
                         for item in data.get("list", [])} - {""}
                self._excluded_codes |= codes
                logger.info(f"제외 코드 로드: {label} {len(codes)}개")
            except Exception as e:
                logger.warning(f"제외 코드 로드 실패 ({label}, mrkt_tp={mrkt_tp}): {e}")
            time.sleep(0.3)
        logger.info(f"ETF/ETN 제외 코드 셋: 총 {len(self._excluded_codes)}개")

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
                    self._top_value_codes.add(code)
                    tv = abs(self.engine.parse_price(item.get("trde_prica", "0"))) * 1_000_000
                    cp = abs(self.engine.parse_price(item.get("cur_prc", "0")))
                    chg = self.engine.parse_float(item.get("flu_rt", "0"))

                    if code in seen_codes:
                        continue
                    if code in self._excluded_codes:  # ETF/ETN — 개별 시총 조회 전에 제외
                        continue

                    # 시가총액은 거래대금순위 API에 없으므로 개별 조회
                    try:
                        info = self.api.get_stock_basic_info(code)
                        mc_raw = self.engine.parse_price(info.get("mac", "0"))
                        mc = mc_raw * 100_000_000
                        self._capture_basic_features(code, info)
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
                if code in seen_codes or code in self._excluded_codes:
                    continue
                try:
                    info = self.api.get_stock_basic_info(code)
                    name = info.get("stk_nm", code)
                    cp = abs(self.engine.parse_price(info.get("cur_prc", "0")))
                    chg = self.engine.parse_float(info.get("flu_rt", "0"))
                    mc_raw = self.engine.parse_price(info.get("mac", "0"))
                    mc = mc_raw * 100_000_000
                    self._capture_basic_features(code, info)
                    # 기본정보(ka10001)엔 거래대금이 없어 일봉(ka10081)에서 별도 조회 후
                    # 거래대금 순위 경로와 같은 최소 품질 필터를 적용한다.
                    time.sleep(0.3)
                    tv = self._fetch_trading_value(code)
                    if self.engine.filter_basic(name, tv, mc):
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

    def _capture_basic_features(self, code: str, info: dict):
        """기본정보(ka10001) 응답에서 연구 피처를 캡처 — 외인소진율(for_exh_rt) + 재무 스냅샷.

        재무(per/pbr/ev/roe/eps/bps/매출·영업이익·순이익)는 같은 응답에서 파생하므로
        추가 API 콜이 없다. 관측·기록 전용(점수 무영향).
        """
        fer = info.get("for_exh_rt")
        feat = self._feat.setdefault(code, {})
        feat["frgn_exhaust_rate"] = self.engine.parse_float(fer) if fer else None
        feat.update(financials(info))

    def _fetch_chart_features(self, code: str, current_price: int) -> dict:
        """일봉(ka10081) 1콜에서 차트 구조 피처를 굽는다 — vol_ratio(당일÷20일 평균 거래량)
        + dist_prior_high_pct(250일 전고점 대비 거리) + ma5_reclaim(5일선 재탈환 반전)
        + red_candle/red_candle_streak(당일 음봉·연속 음봉, 수급 눌림/지속 축)
        + overhead_vol_ratio/poc_dist_pct(매물대 볼륨프로파일 — 두터움·POC 거리).
        실패 시 빈 dict(피처만 결측)."""
        try:
            data = self.api.get_daily_chart(code)
            candles = data.get("stk_dt_pole_chart_qry", [])
            today = datetime.now().strftime("%Y%m%d")
            vols = [
                (cd.get("dt", ""), abs(self.engine.parse_price(cd.get("trde_qty", "0"))))
                for cd in candles[:30]
            ]
            highs = [
                (cd.get("dt", ""), abs(self.engine.parse_price(cd.get("high_pric", "0"))))
                for cd in candles[:251]  # 당일 + 직전 250거래일
            ]
            ohlc = [
                (
                    cd.get("dt", ""),
                    abs(self.engine.parse_price(cd.get("open_pric", "0"))),
                    abs(self.engine.parse_price(cd.get("cur_prc", "0"))),
                )
                for cd in candles[:6]  # 당일 + 직전 5봉 (전일 MA5 계산분)
            ]
            hlv_bars = [
                (
                    cd.get("dt", ""),
                    abs(self.engine.parse_price(cd.get("high_pric", "0"))),
                    abs(self.engine.parse_price(cd.get("low_pric", "0"))),
                    abs(self.engine.parse_price(cd.get("trde_qty", "0"))),
                )
                for cd in candles[:251]  # 볼륨프로파일(당일 포함 250봉)
            ]
            return {
                "vol_ratio": vol_ratio(vols, today),
                "dist_prior_high_pct": dist_prior_high_pct(highs, today, current_price),
                "ma5_reclaim": ma5_reclaim(ohlc, today, current_price),
                "red_candle": red_candle(ohlc, today, current_price),
                "red_candle_streak": red_candle_streak(ohlc, today, current_price),
                "overhead_vol_ratio": overhead_vol_ratio(hlv_bars, current_price),
                "poc_dist_pct": poc_dist_pct(hlv_bars, current_price),
            }
        except Exception as e:
            logger.warning(f"차트 피처 조회 실패 [{code}]: {e}")
            return {}

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
            # 음전 종목도 정밀분석·저장한다. rule_evaluator 의 반사실 표본으로 쓰되,
            # 실제 매매 선정은 _apply_selection 에서 change_pct >= 0 후보로 제한한다.

            # 정배열/신고가는 하드 필터에서 점수 가점으로 전환 (2026-07-03) —
            # 필터가 풀을 하루 10개 미만까지 줄여 점수가 '선정'을 못 하던 문제 해소.
            is_aligned, near_high = self.engine.check_ma_alignment(c.code)
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

            # F5 수급 구조 피처 캡처 — 이미 조회된 응답의 파생값(외국계 거래원·프로그램 연속)
            # + 거래량 배율(일봉 1콜). 저장 전용, 점수·선정에 무영향.
            feat = self._feat.setdefault(c.code, {})
            feat["foreign_brokers_buying"] = 1 if supply.get("foreign_brokers_buying") else 0
            feat["prog_buy_days"] = prog_buy_days(c.supply_history)
            feat["days_since_frgn_surge"] = days_since_frgn_surge(
                c.supply_history, datetime.now().strftime("%Y-%m-%d")
            )
            feat.update(self._fetch_chart_features(c.code, c.current_price))
            feat["round_dist_pct"] = round_dist_pct(c.current_price)

            # 프로그램 양매수(순매수 > 0)는 더 이상 필수 조건이 아니다.
            #   필터 대신 score_candidate()의 가산점(SCORE_PROGRAM_BUY_BONUS)으로 반영한다.
            #   프로그램 데이터 조회 실패 시 prog_net_buy=0 → 가산점만 미부여(제외하지 않음).

            # 1시간봉 캔들 데이터 조회
            c.hourly_candles = self.engine.fetch_hourly_candles(c.code)
            logger.debug(f"[{c.name}] 1시간봉 {len(c.hourly_candles)}개 수집")
            feat["afternoon_ret"] = afternoon_ret(
                c.hourly_candles, c.current_price, datetime.now().strftime("%Y-%m-%d")
            )

            # 호가 미시구조 스냅샷 (ka10004) — 선정 시점 호가 불균형/스프레드. 연속장 밖엔
            # 잔량 0 → 파생값 None, repository 가 마지막 세션 스냅샷 보존(PRESERVE_ON_NULL).
            # 매수는 종가라 종가 직전 마지막 세션 실행(~15시)이 근사치가 된다.
            try:
                ob = self.api.get_stock_order_book(c.code)
                feat.update(order_book_features(ob, c.current_price))
            except Exception as e:
                logger.warning(f"호가 조회 실패 [{c.code}]: {e}")

            # 프로그램 오전/오후 분해 (ka90008 스냅샷 2회 차분, 2026-07-19) —
            # "오전 프로그램 매도 → 오후 매수 전환" 통설 축. 틱 워킹은 유동 종목에서
            # 50페이지+ 라 비현실적(실측) → 30분 주기 재실행을 이용한 2점 스냅샷:
            #  · 정오 창(12:00~12:45) 실행: 현재 누적(1페이지)을 prog_am_net 으로 저장
            #    (repository 가 첫 기록 보존 — 12:30 재실행이 덮어쓰지 않음)
            #  · 오후 창(12:45~15:35) 실행: prog_pm_net = 현재 누적 − 저장된 정오 누적
            # 창 밖 실행은 스킵(키움이 당일 데이터 없으면 최근 거래일 폴백 → 오염 방지),
            # NULL 은 repository 가 기존값 보존.
            now_hms = datetime.now().strftime("%H%M%S")
            cum = None
            if "120000" <= now_hms <= "153500":
                try:
                    rows = self.api.get_program_trade_hourly(
                        c.code, max_pages=1
                    ).get("stk_tm_prm_trde_trnsn", [])
                    cum = prog_cum_net(rows)
                except Exception as e:
                    logger.warning(f"프로그램 시간별 조회 실패 [{c.code}]: {e}")
            if now_hms <= "124500":
                feat["prog_am_net"] = cum
                feat["prog_pm_net"] = None
            else:
                am = self._prog_am_map.get(c.code.split("_")[0])
                feat["prog_am_net"] = None  # 정오 캡처 보존(first-write-wins)
                feat["prog_pm_net"] = (
                    cum - am if cum is not None and am is not None else None
                )

            filtered.append(c)
            time.sleep(0.5)

        filtered = self.engine.identify_sector_leaders(filtered)

        # 오늘의 테마주 여부 마킹
        theme_codes = set()
        for codes in self.strategy_cfg.WATCHLIST_SECTORS.values():
            theme_codes.update(code.split("_")[0] for code in codes)
        for c in filtered:
            code = c.code.split("_")[0]
            c.is_theme_stock = code in theme_codes and code in self._top_value_codes

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

        # 뉴스 재료 반영 (오늘 관련 뉴스 언급 건수 + 연구 라벨) — 사전매칭 집계, LLM 없음.
        # 종합점수 뉴스 가중치(SCORE_NEWS_BONUS)는 기본 0이라 지금은 점수 무영향(표시·튜닝 전용).
        # 라벨(고유 기사·오후 건수·첫 등장·직전 7일 평균)은 daily_stock_report 에 저장돼
        # next_open_ret 과 조인한 뉴스 팩터 엣지 검증에 쓰인다.
        self._news_stats = {}
        for c in filtered:
            code = c.code.split("_")[0]
            try:
                stats = get_today_news_stats_by_stock(code)
                self._news_stats[code] = stats
                c.news_count = stats["count"]
                if c.news_count:
                    logger.info(
                        f"[{c.name}] 뉴스 언급 {c.news_count}건 "
                        f"(고유 {stats['unique_count']}·오후 {stats['pm_count']}"
                        f"{'·첫등장' if stats['first_today'] else ''})"
                    )
            except Exception as e:
                logger.warning(f"뉴스 언급 조회 실패 [{c.name}]: {e}")

        # 공시 사건 라벨 (stock_event, DART) — 후보 전체분을 한 번에 조회해 캐시.
        # 점수 무영향. disc_bad_type 만 live veto rule(veto_disclosure_bad)이 참조한다.
        # 조회 실패 시 빈 dict → disc_* NULL → veto 미개입(수집이 멎어도 선정은 정상 동작).
        self._disc_stats = {}
        try:
            codes = [c.code.split("_")[0] for c in filtered]
            events = get_events_by_date(datetime.now().date(), codes)
            for code, rows in events.items():
                self._disc_stats[code] = summarize_disclosures(rows)
            bad = {k: v["disc_bad_type"] for k, v in self._disc_stats.items()
                   if v["disc_bad_type"]}
            logger.info(f"공시 라벨: {len(events)}종목 사건 보유, 악재 타입 {len(bad)}종목"
                        + (f" — {bad}" if bad else ""))
        except Exception as e:
            logger.warning(f"공시 사건 조회 실패(veto 미적용): {e}")

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

        점수순 정렬된 유니버스 전체를 저장한다(엣지 연구용). selected 는 선정 레이어가
        음전 후보를 제외한 뒤 확정하고, selected=1 만 trade_signal 로 핸드오프한다.
        LLM 뉴스 요약도 선정(top-N) 후보에만 부여해 비용을 종전과 동일하게 유지한다.
        """
        # 섹터 상대치 파생 (F4 후발 확산형의 눈) — 유니버스 in-memory 계산, API 콜 없음.
        # 저장 시점에 구워 넣어 rule 평가기를 행 단위 단순 비교로 유지한다(시점 재현 보장).
        sector_chgs: dict[str, list[float]] = {}
        for c in candidates:
            sector_chgs.setdefault(c.sector or "기타", []).append(c.change_pct or 0.0)
        sector_avg = {s: sum(v) / len(v) for s, v in sector_chgs.items()}
        sector_max = {s: max(v) for s, v in sector_chgs.items()}

        # F5 파생 — 첫 등장(직전 14일 유니버스 부재)·외인소진율 변화(직전 리포트 거래일 대비).
        # 조회 실패 시 해당 피처만 NULL(rule 은 NULL=매칭 실패로 보수 처리) — 저장은 계속한다.
        recent_codes: set[str] | None = None
        try:
            recent_codes = get_recent_report_codes(14)
        except Exception as e:
            logger.warning(f"first_seen 파생용 최근 유니버스 조회 실패: {e}")
        prev_exhaust: dict[str, float] = {}
        try:
            prev_exhaust = get_prev_frgn_exhaust_map()
        except Exception as e:
            logger.warning(f"외인소진율 직전일 맵 조회 실패: {e}")

        reports = []
        for i, c in enumerate(candidates, 1):
            code = c.code.split("_")[0]
            is_top_score = 1 if i <= TRADED_TOP_N else 0
            news_count = getattr(c, "news_count", 0)
            # 유니버스 전체에 뉴스 헤드라인까지 저장한다.
            # LLM 요약·방향·재료유형은 selected 확정 후 실제 핸드오프 후보에만 채운다.
            news_headlines, news_ai = self._build_news_fields(
                c, code, news_count, MAX_NEWS_SUMMARIES
            )
            news_stats = self._news_stats.get(code) or {}
            feat = self._feat.get(code) or {}
            fer = feat.get("frgn_exhaust_rate")
            prev_fer = prev_exhaust.get(code)
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
                "news_unique_count": news_stats.get("unique_count", 0),
                "news_pm_count": news_stats.get("pm_count", 0),
                "news_first_today": news_stats.get("first_today", 0),
                "news_prior_avg": news_stats.get("prior_avg"),
                "news_summary": news_ai["content"] if news_ai else None,
                "news_sentiment": news_ai.get("sentiment") if news_ai else None,
                "news_catalyst": news_ai.get("catalyst") if news_ai else None,
                "news_headlines": news_headlines,
                # 공시 사건 라벨 (stock_event/DART) — disc_bad_type 만 veto rule 이 참조,
                # 나머지는 관측·연구용. 사건 없음/수집 실패는 NULL(= veto 미개입).
                **(self._disc_stats.get(code)
                   or {"disc_count": None, "disc_bad_type": None, "disc_good_type": None}),
                "score": c.score,
                "rank_no": i,
                "selected": is_top_score,  # 잠정값 — 아래 선정 레이어가 모드에 따라 다시 정함
                "sector_rel_ret": (c.change_pct or 0.0) - sector_avg[c.sector or "기타"],
                "sector_leader_chg": sector_max[c.sector or "기타"],
                "foreign_brokers_buying": feat.get("foreign_brokers_buying"),
                "afternoon_ret": feat.get("afternoon_ret"),
                "vol_ratio": feat.get("vol_ratio"),
                "dist_prior_high_pct": feat.get("dist_prior_high_pct"),
                "round_dist_pct": feat.get("round_dist_pct"),
                "ma5_reclaim": feat.get("ma5_reclaim"),
                "days_since_frgn_surge": feat.get("days_since_frgn_surge"),
                "red_candle": feat.get("red_candle"),
                "red_candle_streak": feat.get("red_candle_streak"),
                "overhead_vol_ratio": feat.get("overhead_vol_ratio"),
                "poc_dist_pct": feat.get("poc_dist_pct"),
                "prog_am_net": feat.get("prog_am_net"),
                "prog_pm_net": feat.get("prog_pm_net"),
                "prog_buy_days": feat.get("prog_buy_days"),
                "first_seen": (
                    (0 if code in recent_codes else 1) if recent_codes is not None else None
                ),
                "theme_strength": self._theme_strength.get(code),
                "frgn_exhaust_rate": fer,
                "frgn_exhaust_chg": (
                    round(fer - prev_fer, 2)
                    if fer is not None and prev_fer is not None else None
                ),
                # F7 종목 리스크 속성 — veto_bio 계열 rule 이 선정 직전 이 컬럼들로 제외한다.
                "is_bio": is_bio(code, c.name, c.sector),
                "market": self._market.get(code),  # 코스피/코스닥 (미확인 시 NULL=veto 미적용)
                # 재무 스냅샷 (ka10001 재사용) — 관측·연구용, 점수 무영향
                "fin_per": feat.get("fin_per"),
                "fin_pbr": feat.get("fin_pbr"),
                "fin_ev": feat.get("fin_ev"),
                "fin_roe": feat.get("fin_roe"),
                "fin_eps": feat.get("fin_eps"),
                "fin_bps": feat.get("fin_bps"),
                "fin_sales": feat.get("fin_sales"),
                "fin_op_profit": feat.get("fin_op_profit"),
                "fin_net_income": feat.get("fin_net_income"),
                # 파생: 영업이익÷시총(≥0.1 = "영업이익이 시총 1/10"). predicate 는 컬럼-상수만
                # 되므로 비율을 선정 시점에 미리 구움. 관측·연구용(candidate rule), 점수 무영향.
                "op_earnings_yield": op_earnings_yield(feat.get("fin_op_profit"), c.market_cap),
                # 호가 미시구조 스냅샷 (ka10004) — 관측·연구용, 점수 무영향
                "ob_imbalance": feat.get("ob_imbalance"),
                "ob_fpr_imbalance": feat.get("ob_fpr_imbalance"),
                "ob_spread_pct": feat.get("ob_spread_pct"),
            })

        # 선정 전 매매 후보 풀(음전 제외)에 뉴스 LLM 라벨을 붙여 veto 가 활용할 수 있게 한다.
        summarized = self._fill_selected_news_ai(reports, selected_only=False)

        # 선정 레이어(모드 스위치) — selected/핸드오프 대상만 정한다. 점수·rank_no·저장은 불변.
        rule_names_by_code = self._apply_selection(reports)
        self._fill_selected_news_ai(
            reports, budget=max(0, MAX_NEWS_SUMMARIES - summarized)
        )

        try:
            save_stock_reports(reports)
            logger.info(f"Phase 2 리포트 {len(reports)}건 DB 저장 완료")
        except Exception as e:
            # 저장 실패는 후속 단계를 막지 않지만(핸드오프는 계속) 조용히 넘어가면 그날 리포트가
            # 통째로 비므로 관리자에게 즉시 알린다.
            logger.error(f"Phase 2 리포트 DB 저장 실패: {e}")
            send_report_save_alert(str(e), len(reports))

        # 매수 시그널 핸드오프 — trading 도메인(trade_signal)으로 적재.
        # trading 의 리스크 엔진·사이징이 실제 매수 종목수를 제한하므로 상위 후보를 그대로 넘긴다.
        # 유니버스 전체를 저장하더라도 핸드오프는 selected 만 — rule_names 로 선정 근거를 태깅한다.
        try:
            signals = [
                {"stk_cd": r["stock_code"], "stk_nm": r["stock_name"],
                 "rank_no": r["rank_no"], "score": r["score"],
                 "rule_names": rule_names_by_code.get(r["stock_code"])}
                for r in reports if r["selected"]
            ]
            n = push_trade_signals(datetime.now().strftime("%Y%m%d"), signals)
            logger.info(f"trade_signal 핸드오프 {len(signals)}건 (영향 {n}행)")
        except Exception as e:
            logger.error(f"trade_signal 핸드오프 실패(trading DB 미설정?): {e}")

    @staticmethod
    def _fill_selected_news_ai(
        reports: list[dict], selected_only: bool = True, budget: int = MAX_NEWS_SUMMARIES
    ) -> int:
        """매매 후보에 LLM 뉴스 요약·방향·재료유형을 예산만큼 채운다."""
        if budget <= 0:
            return 0
        summarized = 0
        for r in reports:
            if summarized >= budget:
                break
            if selected_only and not r.get("selected"):
                continue
            if not selected_only and (r.get("change_pct") or 0) < 0:
                continue
            if r.get("news_summary") or r.get("news_sentiment") is not None:
                continue
            if int(r.get("news_count") or 0) < NEWS_SUMMARY_MIN_COUNT:
                continue
            headlines = r.get("news_headlines") or []
            if not headlines:
                continue
            try:
                news_ai = summarize_news(r["stock_name"], r["stock_code"], headlines)
                if not news_ai:
                    continue
                r["news_summary"] = news_ai.get("content")
                r["news_sentiment"] = news_ai.get("sentiment")
                r["news_catalyst"] = news_ai.get("catalyst")
                summarized += 1
                scope = "selected" if r.get("selected") else "후보"
                logger.info(
                    f"[{r['stock_name']}] {scope} 뉴스 재료 요약 생성 "
                    f"(방향 {news_ai.get('sentiment')}·유형 {news_ai.get('catalyst')})"
                )
            except Exception as e:
                logger.warning(f"뉴스 요약 실패 [{r.get('stock_name')}]: {e}")
        return summarized

    # ── 선정 레이어 (모드 스위치) ──
    def _apply_selection(self, reports: list[dict]) -> dict[str, str]:
        """EDGE_SELECTION_MODE 에 따라 각 report 의 selected 를 확정하고, 선정 종목의
        rule_names 매핑을 반환한다. live rule 로드 실패 시 **모드 자체를 legacy 로 폴백**한다
        — rules 모드를 빈 rule 목록으로 진행하면 매칭 0=그날 무거래가 되어 '폴백'이 아니게 된다.

        점수·rank_no·저장은 이 함수가 건드리지 않는다(대조군 평가·프론트 표시 불변).
        선정 시점(13~15시)엔 NXT 스냅샷·당일 market_snapshot 이 없어 그 피처 기반 rule 은
        매칭될 수 없다 — 그런 rule 의 live 승격 자체를 edge_policy 실행 가능성 게이트가 막는다.
        역할(selector/veto/benchmark) 판정은 core.edge_policy.rule_role 단일 소스.
        """
        mode = EDGE_SELECTION_MODE
        live_rules, veto_rules = [], []
        try:
            live = list_rules(status="live")
            veto_rules = [r for r in live if rule_role(r) == "veto"]
            # benchmark(control·측정 밴드)는 선정에 쓰지 않는다 — selector 로 넣으면 광역
            # predicate(selected==1 등)가 늘 top-N 을 매칭해 rules 모드의 '무거래' 의미가 깨진다.
            live_rules = [r for r in live if rule_role(r) == "selector"]
        except Exception as e:
            if mode != "legacy":
                mode = "legacy"
                logger.warning(f"live rule 로드 실패 — legacy 모드로 폴백(veto 미적용): {e}")
            else:
                logger.warning(f"veto rule 로드 실패 — veto 미적용: {e}")

        selection_reports = []
        trade_rank = 0
        for r in reports:
            if (r.get("change_pct") or 0) < 0:
                continue
            trade_rank += 1
            selection_reports.append({**r, "rank_no": trade_rank})
        excluded_negative = len(reports) - len(selection_reports)

        selected_codes, rule_names_by_code, veto_log = select_signals(
            mode, selection_reports, live_rules, veto_rules, TRADED_TOP_N, market=None,
        )
        sel_set = set(selected_codes)
        for r in reports:
            r["selected"] = 1 if r["stock_code"] in sel_set else 0

        for v in veto_log:
            logger.info(f"veto 제외: {v['name']}({v['code']}) — {','.join(v['rules'])}")
        logger.info(
            f"선정 레이어(mode={mode}"
            f"{'←' + EDGE_SELECTION_MODE + ' 폴백' if mode != EDGE_SELECTION_MODE else ''}): "
            f"선정 {len(selected_codes)}건{' — 무거래' if not selected_codes else ''}, "
            f"음전 연구표본 {excluded_negative}건 제외, veto {len(veto_log)}건"
        )
        return rule_names_by_code

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
                        # F4 테마 후발 피처: 소속 테마 당일 등락률의 최대값(복수 테마면 최강 테마)
                        theme_flu = float(theme.get("flu_rt", "0").replace("+", ""))
                        for rc in codes:
                            base = rc.split("_")[0]
                            prev = self._theme_strength.get(base)
                            if prev is None or theme_flu > prev:
                                self._theme_strength[base] = theme_flu
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
        """뉴스 헤드라인 목록 + (조건 충족 시) 배치 LLM 재료 요약·라벨을 만든다.
        반환: (headlines: list[str] | None,
               news_ai: {"content","sentiment","catalyst"} | None)."""
        if news_count <= 0:
            return None, None
        headlines = None
        news_ai = None
        try:
            items = get_today_news_by_stock(code)
            headlines = [it["headline"] for it in items if it.get("headline")] or None
        except Exception as e:
            logger.warning(f"뉴스 헤드라인 조회 실패 [{c.name}]: {e}")
        if (news_count >= NEWS_SUMMARY_MIN_COUNT and headlines
                and summarized < MAX_NEWS_SUMMARIES):
            try:
                news_ai = summarize_news(c.name, code, headlines)
                if news_ai:
                    logger.info(
                        f"[{c.name}] 뉴스 재료 요약 생성 "
                        f"(방향 {news_ai.get('sentiment')}·유형 {news_ai.get('catalyst')})"
                    )
            except Exception as e:
                logger.warning(f"뉴스 요약 실패 [{c.name}]: {e}")
        return headlines, news_ai

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
            # 같은 응답에서 시장 구분도 캡처(키움은 코스피를 '거래소'로 준다 → 정규화)
            market = (info.get("marketName") or "").strip()
            if market:
                self._market[code_base] = "코스피" if market == "거래소" else market
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
