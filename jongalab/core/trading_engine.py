"""
종가베팅 비즈니스 로직
============================================================
모델(데이터클래스), 분석 엔진, 주문 실행기를 포함합니다.

[타임라인]
  13:00~14:30  사전 스크리닝 & 시장 분위기 파악
  14:30~15:00  수급 정밀 체크 & 매수 후보 확정
"""

import time
import logging
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.kiwoom_client import KiwoomRestClient

logger = logging.getLogger("ClosingBet")


# ============================================================
# 모델 & 상수
# ============================================================

class StrategyConfig:
    """종가베팅 전략 파라미터 (API 설정과 분리)"""

    # ---- 필터 임계값 ----
    MIN_TRADING_VALUE = 100_000_000_000      # 거래대금 최소 1,000억
    PREFERRED_TRADING_VALUE = 200_000_000_000
    MIN_MARKET_CAP = 200_000_000_000         # 시총 최소 2,000억
    TOP_N_BY_VALUE = 20

    # ---- 이동평균 정배열 기준 ----
    MA_PERIODS = [5, 10, 20]

    # ---- 수급 기준 ----
    MIN_INST_NET_BUY_AMT = 1_000_000_000     # 기관 순매수 금액 최소 10억
    MIN_FRGN_NET_BUY_AMT = 1_000_000_000
    SUPPLY_CHECK_DAYS = 5
    SUPPLY_RECENCY_WEIGHTS = [0.3, 0.5, 0.8, 1.4, 3.0]
    SUPPLY_DOUBLE_BUY_BASE_SCORE = 12
    SUPPLY_DOUBLE_BUY_AMOUNT_SCORE = 4
    SUPPLY_INST_BUY_BASE_SCORE = 8
    SUPPLY_INST_BUY_AMOUNT_SCORE = 3
    SUPPLY_FRGN_BUY_BASE_SCORE = 5
    SUPPLY_FRGN_BUY_AMOUNT_SCORE = 2
    SUPPLY_PERSONAL_SELL_SCORE = 3
    SUPPLY_PERSONAL_BUY_PENALTY = 3
    SUPPLY_SMART_PERSONAL_SELL_SCORE = 5
    SUPPLY_SMART_PERSONAL_BUY_PENALTY = 8
    SUPPLY_DOUBLE_STREAK_BONUS = [0, 0, 8, 15, 22, 30]
    SUPPLY_INST_STREAK_BONUS = [0, 0, 5, 10, 16, 22]
    SUPPLY_FRGN_STREAK_BONUS = [0, 0, 3, 6, 9, 12]
    SUPPLY_CUMULATIVE_FRGN_INST_SCORE = 20
    SUPPLY_CUMULATIVE_INST_SCORE = 12
    SUPPLY_CUMULATIVE_SMART_PERSONAL_SELL_SCORE = 15
    SUPPLY_CUMULATIVE_SMART_PERSONAL_BUY_PENALTY = 20
    SUPPLY_RECENT_DOUBLE_BUY_SCORE = 20
    SUPPLY_TODAY_DOUBLE_BUY_SCORE = 15
    SUPPLY_TODAY_INST_BUY_SCORE = 8
    SUPPLY_TODAY_SMART_PERSONAL_SELL_SCORE = 8
    SUPPLY_TODAY_DOUBLE_SELL_PENALTY = 20
    SUPPLY_FOREIGN_SIGNAL_BOOST_MARGIN = 5

    # ---- 관심 섹터 (API 동적 로드, ka90001 + ka90002) ----
    WATCHLIST_SECTORS: dict[str, list[str]] = {}
    TOP_THEME_COUNT = 8           # 상위 테마 그룹 수
    THEME_PERIOD_DAYS = "10"      # 기간수익률 기준 일수
    THEME_STOCK_BONUS = 15        # 오늘의 테마주 가산점

    EXCLUDE_KEYWORDS = ["ETF", "ETN", "KODEX", "TIGER", "KBSTAR",
                        "ARIRANG", "SOL", "HANARO", "RISE"]

    # ---- 콘텐츠 분석 가산점 ----
    CONTENT_SCORE_MAX = 10            # 콘텐츠 분석 최대 가산점

    # ---- 종합점수 구성 가중치 (주간 매매성과 기반 GPT 튜닝 대상) ----
    # score_candidate() 가 각 지표에 부여하는 가점(최대값). 최종 종합점수는 이 가점들의 최대 합으로
    # 정규화해 항상 0~100 으로 환산된다. 소수 첫째자리까지 조정 가능.
    SCORE_SUPPLY_BONUS = 40.0         # 5일 수급점수(0~100) 비율만큼 부여하는 최대 가점
    SCORE_MA_ALIGNED_BONUS = 10       # 정배열 가점
    SCORE_NEAR_HIGH_BONUS = 10        # 신고가 근처 가점
    SCORE_PREFERRED_VALUE_BONUS = 15  # 거래대금 우선 기준 충족 가점
    SCORE_MIN_VALUE_BONUS = 8         # 거래대금 최소 기준 충족 가점
    SCORE_LEADER_BONUS = 10           # 대장주 가점
    SCORE_EXTRA_SUPPLY_DAY_BONUS = 3  # 5일 초과 장기 연속 수급 1일당 가점

    def load_from_db(self):
        """DB에서 전략 설정값을 로드하여 인스턴스에 덮어씀"""
        try:
            from core.repository.strategy_config import get_strategy_config
            config = get_strategy_config()
            for key, value in config.items():
                if hasattr(self, key) and key != "WATCHLIST_SECTORS":
                    setattr(self, key, value)
            logger.info("전략 설정 DB 로드 완료")
        except Exception as e:
            logger.warning(f"전략 설정 DB 로드 실패, 기본값 사용: {e}")


class SupplyGrade(Enum):
    """5일 수급 점수 기반 등급 (calculate_supply_score 결과를 classify_supply_score로 매핑)"""
    S = "S급 수급 - 종가베팅 최우선 후보"   # score >= 85
    A = "A급 수급 - 관심권"                # score >= 70
    B = "B급 수급 - 조건부 관찰"            # score >= 55
    C = "C급 수급 - 수급 약함"              # score >= 40
    D = "D급 수급 - 제외"                  # score <  40


SUPPLY_GRADE_THRESHOLDS = {
    SupplyGrade.S: 85,
    SupplyGrade.A: 70,
    SupplyGrade.B: 55,
    SupplyGrade.C: 40,
}


@dataclass
class StockCandidate:
    code: str
    name: str
    sector: str
    current_price: int = 0
    trading_value: int = 0
    market_cap: int = 0
    change_pct: float = 0.0
    ma_aligned: bool = False
    near_high: bool = False
    supply_grade: SupplyGrade = SupplyGrade.D
    supply_score: float = 0.0  # 최근 5일 수급 정밀 점수 (0~100)
    inst_net_buy: int = 0
    frgn_net_buy: int = 0
    indv_net_buy: int = 0
    prog_net_buy: int = 0
    supply_days: int = 0
    score: float = 0.0
    is_leader: bool = False
    is_theme_stock: bool = False
    supply_history: list = field(default_factory=list)  # 최근 5일 수급 현황
    hourly_candles: list = field(default_factory=list)  # 1시간봉 캔들 데이터
    content_count: int = 0        # 오늘 관련 콘텐츠 분석 건수
    content_avg_score: float = 0  # 콘텐츠 평균 sentiment_score


@dataclass
class Position:
    code: str
    name: str
    sector: str
    avg_price: float
    quantity: int
    bought_at: str
    splits_done: int = 0


# ============================================================
# 분석 엔진
# ============================================================

class AnalysisEngine:
    def __init__(self, api: KiwoomRestClient, config: StrategyConfig):
        self.api = api
        self.cfg = config

    # ── 가격 문자열 파싱 (키움 응답은 "+53500", "-1200" 형태) ──
    @staticmethod
    def parse_price(val: str) -> int:
        if not val:
            return 0
        return int(val.replace("+", "").replace(",", ""))

    @staticmethod
    def parse_float(val: str) -> float:
        if not val:
            return 0.0
        return float(val.replace("+", "").replace(",", ""))

    # ── 기본 필터 ──
    def filter_basic(self, name: str, trading_val: int, market_cap: int) -> bool:
        if any(kw in name for kw in self.cfg.EXCLUDE_KEYWORDS):
            return False
        if market_cap > 0 and market_cap < self.cfg.MIN_MARKET_CAP:
            return False
        if trading_val < self.cfg.MIN_TRADING_VALUE:
            return False
        return True

    # ── 1시간봉 캔들 데이터 조회 ──
    def fetch_hourly_candles(self, stk_cd: str) -> list[dict]:
        """ka10080 연속조회로 1시간봉 1주일치(약 30~35개) 수집"""
        try:
            raw = self.api.get_minute_chart_pages(
                stk_cd, tic_scope="60", max_pages=3,
            )
            if not raw:
                return []

            candles = []
            for item in raw:
                cntr_tm = item.get("cntr_tm", "")
                if len(cntr_tm) < 12:
                    continue
                candles.append({
                    "time": f"{cntr_tm[:4]}-{cntr_tm[4:6]}-{cntr_tm[6:8]}T{cntr_tm[8:10]}:{cntr_tm[10:12]}",
                    "open": abs(self.parse_price(item.get("open_pric", "0"))),
                    "high": abs(self.parse_price(item.get("high_pric", "0"))),
                    "low": abs(self.parse_price(item.get("low_pric", "0"))),
                    "close": abs(self.parse_price(item.get("cur_prc", "0"))),
                    "volume": abs(self.parse_price(item.get("trde_qty", "0"))),
                })

            # API 응답은 최신순 → 오래된순으로 정렬
            candles.sort(key=lambda x: x["time"])
            return candles
        except Exception as e:
            logger.warning(f"1시간봉 조회 실패 [{stk_cd}]: {e}")
            return []

    # ── 이동평균 정배열 판단 ──
    def check_ma_alignment(self, stk_cd: str) -> tuple[bool, bool]:
        """일봉 차트(ka10081)로 정배열 + 신고가 근처 판단"""
        try:
            data = self.api.get_daily_chart(stk_cd)
            candles = data.get("stk_dt_pole_chart_qry", [])
            logger.debug(f"[{stk_cd}] 일봉 {len(candles)}개 조회")
            if not candles or len(candles) < 120:
                return False, False

            closes = [abs(self.parse_price(c.get("cur_prc", "0"))) for c in candles]
            closes = [p for p in closes if p > 0]

            if len(closes) < 120:
                return False, False

            # 이동평균 계산
            mas = {}
            for period in self.cfg.MA_PERIODS:
                if len(closes) >= period:
                    mas[period] = sum(closes[:period]) / period

            # 정배열 조건 체크
            periods = [p for p in self.cfg.MA_PERIODS if p in mas]

            # (1) 5MA > 10MA > 20MA
            ma_ordered = all(
                mas[periods[i]] > mas[periods[i + 1]]
                for i in range(len(periods) - 1)
            )

            # (2) 종가가 5일선 위
            close_above_ma5 = closes[0] > mas[5] if 5 in mas else False

            # (3) 5일선 기울기 상승 (오늘 5MA > 어제 5MA)
            if len(closes) >= 6:
                ma5_prev = sum(closes[1:6]) / 5
                ma5_rising = mas[5] > ma5_prev
            else:
                ma5_rising = False

            is_aligned = ma_ordered and close_above_ma5 and ma5_rising

            # 역배열 체크 (즉시 제외 대상)
            is_reverse = len(periods) >= 3 and all(
                mas[periods[i]] < mas[periods[i + 1]]
                for i in range(len(periods) - 1)
            )
            if is_reverse:
                return False, False

            # 52주(약 250거래일) 신고가 근처 (95% 이상)
            high_range = min(len(closes), 250)
            high_52w = max(closes[:high_range])
            near_high = closes[0] >= high_52w * 0.95

            return is_aligned, near_high

        except Exception as e:
            logger.warning(f"차트 분석 실패 [{stk_cd}]: {e}")
            return False, False

    # ── 5일 수급 점수 (슈도코드 기반 0~100점 환산) ──
    @staticmethod
    def _normalize_supply_amount(amount_won: int) -> int:
        """순매수 절대 금액을 억원 단위 구간 점수(0~5)로 변환.
        종목별 시총/거래대금 차이로 인한 금액 왜곡을 줄이기 위한 정규화."""
        abs_eok = abs(amount_won) / 100_000_000  # 원 → 억원
        if abs_eok >= 1000:
            return 5
        if abs_eok >= 500:
            return 4
        if abs_eok >= 300:
            return 3
        if abs_eok >= 100:
            return 2
        if abs_eok > 0:
            return 1
        return 0

    @staticmethod
    def _bonus_by_streak(bonuses: list[int | float], streak_days: int) -> float:
        if streak_days < 0:
            return 0.0
        if streak_days < len(bonuses):
            return float(bonuses[streak_days])
        return float(bonuses[-1]) if bonuses else 0.0

    def calculate_supply_score(self, history: list[dict]) -> float:
        """최근 5거래일 개인/외국인/기관 순매수를 종합해 0~100점으로 환산.

        history는 ka10059 응답 그대로(최신→과거). 내부에서 과거→최신 순으로 뒤집어
        오래된 날에는 낮은 가중치, 최신일에는 강한 가중치를 적용한다.

        우선순위: 외국인+기관 양매수 > 기관 단독 > 외국인 단독 > 개인 매도 동반
        """
        if not history:
            return 0.0

        days = list(reversed(history[:5]))  # 과거 → 최신
        base_weights = list(self.cfg.SUPPLY_RECENCY_WEIGHTS) or [1.0]
        if len(base_weights) < len(days):
            base_weights = [base_weights[0]] * (len(days) - len(base_weights)) + base_weights
        weights = base_weights[-len(days):]

        double_streak_bonus = self.cfg.SUPPLY_DOUBLE_STREAK_BONUS
        inst_streak_bonus = self.cfg.SUPPLY_INST_STREAK_BONUS
        frgn_streak_bonus = self.cfg.SUPPLY_FRGN_STREAK_BONUS

        max_daily_raw = (
            self.cfg.SUPPLY_DOUBLE_BUY_BASE_SCORE
            + self.cfg.SUPPLY_DOUBLE_BUY_AMOUNT_SCORE * 5
            + self.cfg.SUPPLY_INST_BUY_BASE_SCORE
            + self.cfg.SUPPLY_INST_BUY_AMOUNT_SCORE * 5
            + self.cfg.SUPPLY_FRGN_BUY_BASE_SCORE
            + self.cfg.SUPPLY_FRGN_BUY_AMOUNT_SCORE * 5
            + self.cfg.SUPPLY_PERSONAL_SELL_SCORE
            + self.cfg.SUPPLY_SMART_PERSONAL_SELL_SCORE
        )

        daily_raw = 0.0
        consec_double = consec_inst = consec_frgn = 0
        total_personal = total_frgn = total_inst = 0

        for day, weight in zip(days, weights):
            personal = day.get("indv_net_buy", 0)
            foreigner = day.get("frgn_net_buy", 0)
            institution = day.get("inst_net_buy", 0)

            total_personal += personal
            total_frgn += foreigner
            total_inst += institution

            # 1. 외국인 + 기관 양매수 (1순위)
            if foreigner > 0 and institution > 0:
                consec_double += 1
                daily_raw += self.cfg.SUPPLY_DOUBLE_BUY_BASE_SCORE * weight
                daily_raw += (
                    self._normalize_supply_amount(foreigner + institution)
                    * self.cfg.SUPPLY_DOUBLE_BUY_AMOUNT_SCORE
                    * weight
                )
            else:
                consec_double = 0

            # 2. 기관 순매수 (2순위)
            if institution > 0:
                consec_inst += 1
                daily_raw += self.cfg.SUPPLY_INST_BUY_BASE_SCORE * weight
                daily_raw += (
                    self._normalize_supply_amount(institution)
                    * self.cfg.SUPPLY_INST_BUY_AMOUNT_SCORE
                    * weight
                )
            else:
                consec_inst = 0

            # 3. 외국인 순매수
            if foreigner > 0:
                consec_frgn += 1
                daily_raw += self.cfg.SUPPLY_FRGN_BUY_BASE_SCORE * weight
                daily_raw += (
                    self._normalize_supply_amount(foreigner)
                    * self.cfg.SUPPLY_FRGN_BUY_AMOUNT_SCORE
                    * weight
                )
            else:
                consec_frgn = 0

            # 4. 개인 매도/매수 (개인 매수는 종가베팅 관점 감점)
            # personal == 0 은 ka10059 잠정치 미반영 가능성이 있어 중립 처리(가감점 없음)
            if personal < 0:
                daily_raw += self.cfg.SUPPLY_PERSONAL_SELL_SCORE * weight
            elif personal > 0:
                daily_raw -= self.cfg.SUPPLY_PERSONAL_BUY_PENALTY * weight

            # 5. 당일 수급 구조
            smart = foreigner + institution
            if smart > 0 and personal < 0:
                daily_raw += self.cfg.SUPPLY_SMART_PERSONAL_SELL_SCORE * weight
            if smart < 0 and personal > 0:
                daily_raw -= self.cfg.SUPPLY_SMART_PERSONAL_BUY_PENALTY * weight

        score_raw = daily_raw
        max_score_raw = max(max_daily_raw, 1.0) * sum(weights)

        # 6. 최신일까지 이어진 연속 매수에만 보너스를 부여한다.
        streak_raw = 0
        streak_raw += self._bonus_by_streak(double_streak_bonus, consec_double)
        streak_raw += self._bonus_by_streak(inst_streak_bonus, consec_inst)
        streak_raw += self._bonus_by_streak(frgn_streak_bonus, consec_frgn)
        score_raw += streak_raw

        max_streak_days = min(len(days), 5)
        max_score_raw += self._bonus_by_streak(double_streak_bonus, max_streak_days)
        max_score_raw += self._bonus_by_streak(inst_streak_bonus, max_streak_days)
        max_score_raw += self._bonus_by_streak(frgn_streak_bonus, max_streak_days)

        # 7. 5일 누적 수급 구조
        cumulative_raw = 0
        total_smart = total_frgn + total_inst
        if total_frgn > 0 and total_inst > 0:
            cumulative_raw += self.cfg.SUPPLY_CUMULATIVE_FRGN_INST_SCORE
        if total_inst > 0:
            cumulative_raw += self.cfg.SUPPLY_CUMULATIVE_INST_SCORE
        if total_smart > 0 and total_personal < 0:
            cumulative_raw += self.cfg.SUPPLY_CUMULATIVE_SMART_PERSONAL_SELL_SCORE
        if total_smart < 0 and total_personal > 0:
            cumulative_raw -= self.cfg.SUPPLY_CUMULATIVE_SMART_PERSONAL_BUY_PENALTY
        score_raw += cumulative_raw
        max_score_raw += (
            self.cfg.SUPPLY_CUMULATIVE_FRGN_INST_SCORE
            + self.cfg.SUPPLY_CUMULATIVE_INST_SCORE
            + self.cfg.SUPPLY_CUMULATIVE_SMART_PERSONAL_SELL_SCORE
        )

        # 8. 최근 2일과 최신일 강조 (종가베팅은 최신 수급이 핵심)
        recent_raw = 0
        if len(days) >= 2:
            d4, d5 = days[-2], days[-1]
            if (d4.get("frgn_net_buy", 0) > 0 and d4.get("inst_net_buy", 0) > 0 and
                    d5.get("frgn_net_buy", 0) > 0 and d5.get("inst_net_buy", 0) > 0):
                recent_raw += self.cfg.SUPPLY_RECENT_DOUBLE_BUY_SCORE
            max_score_raw += self.cfg.SUPPLY_RECENT_DOUBLE_BUY_SCORE
        d5 = days[-1]
        f5 = d5.get("frgn_net_buy", 0)
        i5 = d5.get("inst_net_buy", 0)
        p5 = d5.get("indv_net_buy", 0)
        if f5 > 0 and i5 > 0:
            recent_raw += self.cfg.SUPPLY_TODAY_DOUBLE_BUY_SCORE
        if i5 > 0:
            recent_raw += self.cfg.SUPPLY_TODAY_INST_BUY_SCORE
        if (f5 + i5) > 0 and p5 < 0:
            recent_raw += self.cfg.SUPPLY_TODAY_SMART_PERSONAL_SELL_SCORE
        if f5 < 0 and i5 < 0:
            recent_raw -= self.cfg.SUPPLY_TODAY_DOUBLE_SELL_PENALTY
        score_raw += recent_raw
        max_score_raw += (
            self.cfg.SUPPLY_TODAY_DOUBLE_BUY_SCORE
            + self.cfg.SUPPLY_TODAY_INST_BUY_SCORE
            + self.cfg.SUPPLY_TODAY_SMART_PERSONAL_SELL_SCORE
        )

        score = score_raw / max_score_raw * 100
        return max(0.0, min(100.0, score))

    def classify_supply_score(self, score: float) -> SupplyGrade:
        if score >= SUPPLY_GRADE_THRESHOLDS[SupplyGrade.S]:
            return SupplyGrade.S
        if score >= SUPPLY_GRADE_THRESHOLDS[SupplyGrade.A]:
            return SupplyGrade.A
        if score >= SUPPLY_GRADE_THRESHOLDS[SupplyGrade.B]:
            return SupplyGrade.B
        if score >= SUPPLY_GRADE_THRESHOLDS[SupplyGrade.C]:
            return SupplyGrade.C
        return SupplyGrade.D

    # ── 수급 분석 ──
    def analyze_supply_demand(self, stk_cd: str, current_price: int) -> dict:
        result = {
            "inst_net_buy": 0,
            "frgn_net_buy": 0,
            "indv_net_buy": 0,
            "prog_net_buy": 0,
            "supply_grade": SupplyGrade.D,
            "supply_score": 0.0,
            "supply_days": 0,
            "foreign_brokers_buying": False,
            "supply_history": [],
        }

        # (a) 장중 투자자별 매매 (ka10059) — 14:30 이후 잠정치
        try:
            inv_data = self.api.get_intraday_investor(stk_cd)
            items = inv_data.get("stk_invsr_orgn", [])
            if items:
                today = items[0]
                result["inst_net_buy"] = self.parse_price(
                    today.get("orgn", "0")) * 1_000_000
                result["frgn_net_buy"] = self.parse_price(
                    today.get("frgnr_invsr", "0")) * 1_000_000
                result["indv_net_buy"] = self.parse_price(
                    today.get("ind_invsr", "0")) * 1_000_000

                # 최근 5일 수급 현황 추출
                for item in items[:5]:
                    raw_dt = item.get("dt", "")
                    if len(raw_dt) == 8:
                        formatted_dt = f"{raw_dt[:4]}-{raw_dt[4:6]}-{raw_dt[6:]}"
                    else:
                        formatted_dt = raw_dt
                    result["supply_history"].append({
                        "date": formatted_dt,
                        "inst_net_buy": self.parse_price(item.get("orgn", "0")) * 1_000_000,
                        "frgn_net_buy": self.parse_price(item.get("frgnr_invsr", "0")) * 1_000_000,
                        "indv_net_buy": self.parse_price(item.get("ind_invsr", "0")) * 1_000_000,
                    })
            else:
                logger.debug(f"[{stk_cd}] ka10059 stk_invsr_orgn 비어있음")
        except Exception as e:
            logger.warning(f"장중투자자 조회 실패 [{stk_cd}]: {e}")

        # (b) 프로그램 매매 현황 (ka90004)
        try:
            prog_data = self.api.get_program_trade_by_stock()
            items = prog_data.get("stk_prm_trde_prst", [])
            for item in items:
                if item.get("stk_cd", "") == stk_cd:
                    result["prog_net_buy"] = self.parse_price(
                        item.get("netprps_prica", "0")) * 1_000_000
                    break
        except Exception as e:
            logger.warning(f"프로그램매매 조회 실패 [{stk_cd}]: {e}")

        # (c) 기관외국인 연속매매현황 (ka10131)
        try:
            consec_data = self.api.get_inst_foreign_consecutive()
            items = consec_data.get("orgn_frgnr_cont_trde_prst", [])
            for item in items:
                if item.get("stk_cd", "") == stk_cd:
                    result["supply_days"] = abs(self.parse_price(
                        item.get("tot_cont_netprps_dys", "0")))
                    break
        except Exception as e:
            logger.warning(f"연속매매현황 조회 실패 [{stk_cd}]: {e}")

        # (d) 거래원 체크 (ka10002) — 외국계 증권사 매수 우위
        FOREIGN_BROKERS = [
            "모간", "골드만", "메릴", "CS", "UBS", "JP모간",
            "씨티", "CLSA", "맥쿼리", "노무라", "BNP", "도이치",
            "바클레이", "크레디", "제이피"
        ]
        try:
            broker_data = self.api.get_stock_broker(stk_cd)
            buy_broker_names = [
                broker_data.get(f"buy_trde_ori_nm_{i}", "")
                for i in range(1, 6)
            ]
            foreign_count = sum(
                1 for name in buy_broker_names
                if any(fb in name for fb in FOREIGN_BROKERS)
            )
            result["foreign_brokers_buying"] = foreign_count >= 2
        except Exception as e:
            logger.warning(f"거래원 조회 실패 [{stk_cd}]: {e}")

        # (e) 5일 수급 점수 산정 + 등급 판정
        #     supply_history 기반 정밀 점수(0~100)로 S/A/B/C/D 5단계 분류.
        #     외국계 거래원 매수 우위(foreign_brokers_buying)·프로그램 순매수는
        #     5일 점수에 직접 반영되지 않으므로, 점수가 임계값 직전(35~40, 50~55,
        #     65~70, 80~85)일 때 한 단계 격상해 외국계 자금 시그널을 보정한다.
        score = self.calculate_supply_score(result["supply_history"])
        result["supply_score"] = score

        foreign_signal = result["foreign_brokers_buying"] or result["prog_net_buy"] > 0
        if foreign_signal:
            thresholds = list(SUPPLY_GRADE_THRESHOLDS.values())
            for high in sorted(thresholds, reverse=True):
                low = max(0, high - self.cfg.SUPPLY_FOREIGN_SIGNAL_BOOST_MARGIN)
                if low <= score < high:
                    score = high
                    break

        result["supply_grade"] = self.classify_supply_score(score)

        return result

    # ── 섹터 대장주 판별 ──
    def identify_sector_leaders(self, candidates: list[StockCandidate]) -> list[StockCandidate]:
        sector_map: dict[str, list[StockCandidate]] = {}
        for c in candidates:
            sector_map.setdefault(c.sector, []).append(c)

        for sector, stocks in sector_map.items():
            stocks.sort(key=lambda s: s.change_pct, reverse=True)
            if stocks:
                stocks[0].is_leader = True
                logger.info(f"[{sector}] 대장주: {stocks[0].name} ({stocks[0].change_pct:+.2f}%)")

        return candidates

    # ── 종합 스코어링 ──
    def score_candidate(self, c: StockCandidate) -> float:
        raw = 0.0

        # 5일 수급 가점 — 수급점수(0~100) 비율만큼 최대 가점 부여
        raw += c.supply_score / 100 * self.cfg.SCORE_SUPPLY_BONUS

        # 정배열 + 신고가
        if c.ma_aligned:
            raw += self.cfg.SCORE_MA_ALIGNED_BONUS
        if c.near_high:
            raw += self.cfg.SCORE_NEAR_HIGH_BONUS

        # 거래대금
        if c.trading_value >= self.cfg.PREFERRED_TRADING_VALUE:
            raw += self.cfg.SCORE_PREFERRED_VALUE_BONUS
        elif c.trading_value >= self.cfg.MIN_TRADING_VALUE:
            raw += self.cfg.SCORE_MIN_VALUE_BONUS

        # 대장주
        if c.is_leader:
            raw += self.cfg.SCORE_LEADER_BONUS

        # 오늘의 테마주 가산점
        if c.is_theme_stock:
            raw += self.cfg.THEME_STOCK_BONUS

        # 5일 초과 연속 수급 보너스
        # 5일 이내 연속성은 supply_score에 이미 반영되므로, 6~10일+ 장기 연속만 가산
        extra_days = max(c.supply_days - 5, 0)
        raw += min(extra_days, 5) * self.cfg.SCORE_EXTRA_SUPPLY_DAY_BONUS

        # 콘텐츠 분석: 언급 횟수 + 평균 감성 점수
        if c.content_count > 0:
            mention_bonus = min(c.content_count, 3) * 2  # max 6
            sentiment_bonus = (
                4 if c.content_avg_score >= 70
                else 2 if c.content_avg_score >= 50
                else 0
            )
            raw += min(mention_bonus + sentiment_bonus, self.cfg.CONTENT_SCORE_MAX)

        # 100점 만점 환산 — 각 가점의 최대 합으로 정규화(가중치 튜닝과 무관하게 항상 0~100).
        # 단조 변환이라 후보 간 순위는 보존된다.
        max_possible = (
            self.cfg.SCORE_SUPPLY_BONUS
            + self.cfg.SCORE_MA_ALIGNED_BONUS
            + self.cfg.SCORE_NEAR_HIGH_BONUS
            + self.cfg.SCORE_PREFERRED_VALUE_BONUS
            + self.cfg.SCORE_LEADER_BONUS
            + self.cfg.THEME_STOCK_BONUS
            + 5 * self.cfg.SCORE_EXTRA_SUPPLY_DAY_BONUS
            + self.cfg.CONTENT_SCORE_MAX
        )
        c.score = round(raw / max_possible * 100, 1) if max_possible else 0.0
        return c.score