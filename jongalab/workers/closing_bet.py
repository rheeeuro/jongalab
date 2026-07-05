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
from core.edge_features import afternoon_ret, prog_buy_days, vol_ratio
from core.repository.stock_report import (
    save_stock_reports,
    get_recent_report_codes,
    get_prev_frgn_exhaust_map,
)
from core.repository.sector_report import save_sector_reports
from core.repository.content import get_today_content_by_stock
from core.repository.news import get_today_news_stats_by_stock, get_today_news_by_stock
from core.repository.trade_signal import push_trade_signals
from core.repository.edge_rule import list_rules
from core.edge_selection import select_signals
from core.edge_policy import family_role
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
        # 종목코드 → 뉴스 연구 라벨(get_today_news_stats_by_stock 결과).
        # StockCandidate(가드 파일)를 건드리지 않고 Phase 2 → 리포트 저장으로 전달한다.
        self._news_stats: dict[str, dict] = {}
        # 종목코드 → F5 수급 구조 피처(외국계 거래원·오후 강세·거래량 배율·프로그램 연속·외인소진율).
        # 이미 조회 중인 키움 응답에서 캡처해 저장만 한다(점수 무영향) — 위와 같은 전달 패턴.
        self._feat: dict[str, dict] = {}
        # 종목코드 → 소속 테마 당일 등락률 최대값(_fetch_watchlist_sectors 에서 구축)
        self._theme_strength: dict[str, float] = {}

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
                if code in seen_codes:
                    continue
                try:
                    info = self.api.get_stock_basic_info(code)
                    name = info.get("stk_nm", code)
                    cp = abs(self.engine.parse_price(info.get("cur_prc", "0")))
                    chg = self.engine.parse_float(info.get("flu_rt", "0"))
                    mc_raw = self.engine.parse_price(info.get("mac", "0"))
                    mc = mc_raw * 100_000_000
                    self._capture_basic_features(code, info)
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

    def _capture_basic_features(self, code: str, info: dict):
        """기본정보(ka10001) 응답에서 F5 연구 피처를 캡처 — 외인소진율(for_exh_rt)."""
        fer = info.get("for_exh_rt")
        self._feat.setdefault(code, {})["frgn_exhaust_rate"] = (
            self.engine.parse_float(fer) if fer else None
        )

    def _fetch_vol_ratio(self, code: str) -> float | None:
        """일봉(ka10081) 거래량으로 당일 ÷ 직전 20일 평균 배율. 실패 시 None(피처만 결측)."""
        try:
            data = self.api.get_daily_chart(code)
            candles = data.get("stk_dt_pole_chart_qry", [])
            vols = [
                (cd.get("dt", ""), abs(self.engine.parse_price(cd.get("trde_qty", "0"))))
                for cd in candles[:30]
            ]
            return vol_ratio(vols, datetime.now().strftime("%Y%m%d"))
        except Exception as e:
            logger.warning(f"거래량 배율 조회 실패 [{code}]: {e}")
            return None

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
            # 음전 종목 제외 — 종가베팅 전제(마감 강세)와 상충 (2026-07-03 실증: 음전 승률 최하)
            if c.change_pct < 0:
                logger.debug(f"음전 → 제외: {c.name} ({c.change_pct:+.1f}%)")
                continue

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
            feat["vol_ratio"] = self._fetch_vol_ratio(c.code)

            # 프로그램 양매수(순매수 > 0)는 더 이상 필수 조건이 아니다.
            #   필터 대신 score_candidate()의 가산점(SCORE_PROGRAM_BUY_BONUS)으로 반영한다.
            #   프로그램 데이터 조회 실패 시 prog_net_buy=0 → 가산점만 미부여(제외하지 않음).

            # 1시간봉 캔들 데이터 조회
            c.hourly_candles = self.engine.fetch_hourly_candles(c.code)
            logger.debug(f"[{c.name}] 1시간봉 {len(c.hourly_candles)}개 수집")
            feat["afternoon_ret"] = afternoon_ret(
                c.hourly_candles, c.current_price, datetime.now().strftime("%Y-%m-%d")
            )

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
        summarized = 0
        for i, c in enumerate(candidates, 1):
            code = c.code.split("_")[0]
            # LLM 뉴스 요약 예산은 점수 상위 top-N 에만 부여(비용 통제 — 선정 모드와 무관).
            # 실제 selected(핸드오프) 판정은 아래 선정 레이어(모드 스위치)가 다시 정한다.
            is_top_score = 1 if i <= TRADED_TOP_N else 0
            news_count = getattr(c, "news_count", 0)
            if is_top_score:
                news_headlines, news_ai = self._build_news_fields(
                    c, code, news_count, summarized
                )
                if news_ai:
                    summarized += 1
            else:
                # 비선정 후보: 헤드라인만(표시·연구용), LLM 요약은 생략
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
                "score": c.score,
                "rank_no": i,
                "selected": is_top_score,  # 잠정값 — 아래 선정 레이어가 모드에 따라 다시 정함
                "sector_rel_ret": (c.change_pct or 0.0) - sector_avg[c.sector or "기타"],
                "sector_leader_chg": sector_max[c.sector or "기타"],
                "foreign_brokers_buying": feat.get("foreign_brokers_buying"),
                "afternoon_ret": feat.get("afternoon_ret"),
                "vol_ratio": feat.get("vol_ratio"),
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
            })

        # 선정 레이어(모드 스위치) — selected/핸드오프 대상만 정한다. 점수·rank_no·저장은 불변.
        rule_names_by_code = self._apply_selection(reports)

        try:
            save_stock_reports(reports)
            logger.info(f"Phase 2 리포트 {len(reports)}건 DB 저장 완료")
        except Exception as e:
            logger.error(f"Phase 2 리포트 DB 저장 실패: {e}")

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

    # ── 선정 레이어 (모드 스위치) ──
    def _apply_selection(self, reports: list[dict]) -> dict[str, str]:
        """EDGE_SELECTION_MODE 에 따라 각 report 의 selected 를 확정하고, 선정 종목의
        rule_names 매핑을 반환한다. live rule 로드 실패 시 **모드 자체를 legacy 로 폴백**한다
        — rules 모드를 빈 rule 목록으로 진행하면 매칭 0=그날 무거래가 되어 '폴백'이 아니게 된다.

        점수·rank_no·저장은 이 함수가 건드리지 않는다(대조군 평가·프론트 표시 불변).
        선정 시점(13~15시)엔 NXT 스냅샷·당일 market_snapshot 이 없어 그 피처 기반 rule 은
        매칭될 수 없다 — 그런 rule 의 live 승격 자체를 edge_policy 실행 가능성 게이트가 막는다.
        family 역할(selector/veto/benchmark) 판정은 core.edge_policy.FAMILY_ROLES 단일 소스.
        """
        mode = EDGE_SELECTION_MODE
        live_rules, veto_rules = [], []
        try:
            live = list_rules(status="live")
            veto_rules = [r for r in live if family_role(r["family"]) == "veto"]
            # benchmark(control)는 선정에 쓰지 않는다 — selector 로 넣으면 predicate(selected==1)가
            # 늘 top-N 을 매칭해 rules 모드의 '무거래' 의미가 깨진다(페이퍼 기준선으로만 채점).
            live_rules = [r for r in live if family_role(r["family"]) == "selector"]
        except Exception as e:
            if mode != "legacy":
                mode = "legacy"
                logger.warning(f"live rule 로드 실패 — legacy 모드로 폴백(veto 미적용): {e}")
            else:
                logger.warning(f"veto rule 로드 실패 — veto 미적용: {e}")

        selected_codes, rule_names_by_code, veto_log = select_signals(
            mode, reports, live_rules, veto_rules, TRADED_TOP_N, market=None,
        )
        sel_set = set(selected_codes)
        for r in reports:
            r["selected"] = 1 if r["stock_code"] in sel_set else 0

        for v in veto_log:
            logger.info(f"veto 제외: {v['name']}({v['code']}) — {','.join(v['rules'])}")
        logger.info(
            f"선정 레이어(mode={mode}"
            f"{'←' + EDGE_SELECTION_MODE + ' 폴백' if mode != EDGE_SELECTION_MODE else ''}): "
            f"선정 {len(selected_codes)}건{' — 무거래' if not selected_codes else ''}, veto {len(veto_log)}건"
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
