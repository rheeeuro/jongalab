"""
trading 자동매매 서버 설정 — DB(트레이딩 전용) + 키움 토큰 공유 DB + 안전장치 플래그.

cwd 가 trading/ 이므로 리포지토리 루트(.env)를 절대경로로 명시 로드한다.
키움 APP_KEY/SECRET_KEY/ACCOUNT_NO 는 주문 클라이언트가 os.getenv 로 직접 읽는다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# trading/core/config.py → parents[2] == 리포지토리 루트
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ROOT_ENV)

# 공유 MariaDB 서버 (jongalab/kiwoom 와 동일 호스트·계정, 스키마만 분리)
_DB_BASE = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'user': os.getenv('DB_USER', 'stock_user'),
    'password': os.getenv('DB_PASSWORD', ''),
    'port': int(os.getenv('DB_PORT', '3307')),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'use_unicode': True,
}

# 트레이딩 전용 DB (주문/체결/포지션/시그널/리스크/감사로그)
DB_CONFIG = {**_DB_BASE, 'database': os.getenv('TRADING_DB_NAME', 'trading')}

# 키움 토큰 공유 DB (읽기 전용 — 토큰은 kiwoom 서버 워커가 매일 07:00 갱신)
KIWOOM_DB_CONFIG = {**_DB_BASE, 'database': os.getenv('KIWOOM_DB_NAME', 'kiwoom')}

# jongalab DB (읽기 전용 — 텔레그램 관리자 chat id 조회용: telegram_users)
JONGALAB_DB_CONFIG = {**_DB_BASE, 'database': os.getenv('JONGALAB_DB_NAME', 'jongalab')}

# 텔레그램 봇 토큰 (관리자 매수현황 알림). jongalab 과 동일 .env 값.
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# 대시보드 접속 비밀번호 (프론트 로그인 → 백엔드 /admin/login 검증).
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')

# 키움 데이터 서버 (시세/수급 읽기) — 주문은 trading 이 키움 REST 로 직접 호출한다
KIWOOM_BASE_URL = os.getenv('KIWOOM_BASE_URL', 'http://127.0.0.1:8001')

# ── 키움 주문/계좌 (운영/모의) — 계좌·주문은 토큰에 귀속(별도 계좌번호 불필요) ──
KIWOOM_APP_KEY = os.getenv('KIWOOM_APP_KEY', '')
KIWOOM_SECRET_KEY = os.getenv('KIWOOM_SECRET_KEY', '')

# ── 거래소 라우팅 (KRX | NXT | SOR) ──
# 16:00 매수는 KRX 마감 후라 NXT/SOR 가 필요. NXT 명시는 비-NXT 종목에서 거부되므로
# SOR(스마트 라우팅, 키움이 가용 거래소로 자동 배정)을 기본값으로 둔다. .env 로 override 가능.
BUY_EXCHANGE = os.getenv('BUY_EXCHANGE', 'SOR')
SELL_EXCHANGE = os.getenv('SELL_EXCHANGE', 'SOR')

# ── 청산 스탑선 튜닝 ──
# NXT 절반 매도 후 잔량의 스탑/저가이탈선을 시초가 대비 몇 % 아래로 둘지(>0). 시초가를 그대로
# 선으로 잡으면 절반 매도 직후 가격이 시초가에서 한 틱만 눌려도(갭상승은 추가상승 무산, 갭하락은
# 회복 기다리기 전에) 잔량이 즉시 털린다. 시초가*(1 - pct/100) 로 버퍼를 둬 잔량을 조금 더 들고 간다.
# 갭상승 스탑선·갭하락 저가이탈선 양쪽에 동일 적용.
STOP_BUFFER_PCT = float(os.getenv('STOP_BUFFER_PCT', '0.5'))

# ── 트레일링 스탑(고점 추종) ──
# 절반매도 후 잔량을 09:28 데드라인까지 들고 가며, 모니터가 매 틱 스탑선을 고점 추종으로
# 끌어올린다(단조 증가, 절대 내리지 않음): stop = max(기존 stop, 현재가*(1 - TRAIL_PCT/100)).
# 고점 대비 TRAIL_PCT% 빠지면 트레일링 스탑에 걸려 잔량을 매도해 상승분을 최대한 확보한다.
# 값이 작을수록 고점 가까이에서 청산(잦은 조기 청산), 클수록 더 들고 간다(되돌림 손실↑).
# 0.75: 2026-07-18 분봉 백테스트(라운드트립 95건, 6/18~7/16) — 1.0 대비 +0.079%p(t=3.43,
# 악화 0건), 0.5 이하는 15초 폴링 노이즈 털림이 1분봉 시뮬에 과소반영돼 비채택.
TRAIL_PCT = float(os.getenv('TRAIL_PCT', '0.75'))

# ── 하드 손절(칼손절) ──
# 시초가 변동성이 큰 정각~settle(:05) 구간을 포함해, 모니터 가동 내내 평단(avg_price) 대비
# 현재가가 이 %만큼 아래로 떨어지면 settle_plan 유무와 무관하게 즉시 전량 매도한다.
# settle(08:05/09:05)가 손실을 정리하기 전에 갭하락으로 손실이 커지는 것을 막는 안전망.
HARD_STOP_LOSS_PCT = float(os.getenv('HARD_STOP_LOSS_PCT', '2.0'))

# ── 시드 배분기 튜닝 (core.seed_allocator) ──
# 종목당 최대 투입 비율 — 시드 대비(고정금액 아님). 1.0 이상이면 사실상 무제한.
# 2026-07-10 0.5→0.25: HLB 하한가 사건 — 그리디 재투입이 저가주 한 종목에 시드 35%를
# 몰아줘 하한가 1방이 포트 -8%로 직결됐다. 하한가에선 손절이 불가하므로 노출 크기로만
# 봉쇄 가능. 최악 단일 종목 하한가 손실을 시드의 -7.5%(0.25×-30%) 수준으로 제한한다.
SEED_MAX_NAME_PCT = float(os.getenv('SEED_MAX_NAME_PCT', '0.25'))

# ── 롤링 엣지 게이트 (core.regime_gate) — 최근 선정 종목의 점수 판별력으로 총 시드 축소 ──
# 근거: 엣지가 레짐 의존적이라(봄엔 고점수 우세, 6월엔 역전) 역전 구간엔 자본을 덜 싣는다.
# 2026-07-23 기본 OFF 전환: 임계 0은 점수가 양의 엣지를 갖던 구로직(전체 스프레드 +1.13%p)에 맞춘 값인데,
#   스코어/선정 로직 변경 후(6/26 −1.14%p, 7/07 −1.55%p)로는 스프레드가 상시 음수 = "역전"이 평상시 기본값이다.
#   이는 등가중 전환의 근거(점수가 익일 손익 예측 못 함/역상관)와 같은 횡단면 현상으로, 이미 등가중이 처리했다.
#   즉 게이트는 손익 레짐이 아니라 점수-순위 역상관을 재고 있어, 수익 나는 날에도 상시 30% 컷을 낸다
#   (7/23 첫 실발동: 역전일들 실현수익 7/09 +1.73%·7/21 +5.78%). 7/14 평가도 승격 미달 candidate 였음.
#   → 관찰용 audit 로그는 signal_executor 에서 계속 남기되(사후 채점용), live 감액은 중단. 재개하려면 env=1.
REGIME_GATE_ENABLED = os.getenv('REGIME_GATE_ENABLED', '0') == '1'
REGIME_WINDOW_DAYS = int(os.getenv('REGIME_WINDOW_DAYS', '10'))     # 최근 몇 거래일 표본
# 최소 거래일 수 — 미만이면 게이트 미개입(1.0). 종목-일 표본은 같은 날 시장 무브로 상관되어
# 거래일 수가 실효 표본이다(edge_policy PROMO_MIN_DAYS 와 같은 논리). 종목-일 30개 기준이던
# 구 REGIME_MIN_SAMPLES 는 신로직 전환 직후 실효 4거래일로 최대 축소가 나가는 문제로 대체(2026-07-14).
REGIME_MIN_DAYS = int(os.getenv('REGIME_MIN_DAYS', '10'))
# 이진 배수: split(점수 상위½−하위½ 익일시가수익, %p) < INVERT_THRESHOLD 면 역전 → MIN_MULT, 아니면 1.0.
# 근거: 4/9~7/10 백테스트에서 역전 '깊이'는 다음날 성적과 무상관(강한 역전일이 오히려 나음) —
# 부호만 유효해 선형 램프(±0.5→0.3~1.0)를 이진으로 대체(2026-07-14).
REGIME_INVERT_THRESHOLD = float(os.getenv('REGIME_INVERT_THRESHOLD', '0.0'))
REGIME_MIN_MULT = float(os.getenv('REGIME_MIN_MULT', '0.3'))       # 역전 시 시드 배수(30%)
# 표본 하한 날짜(YYYY-MM-DD, inclusive) — 이 날짜 이전 report_date 는 레짐 표본에서 제외.
# 근거: 선정/스코어 로직 변경 이전 표본은 익일수익 판별력 비교가 무의미(=구로직). 최신 변경일부터만 사용.
# 창(REGIME_WINDOW_DAYS)이 이 날짜를 넘어 충분히 지나면 자연히 무의미해지는 자기소멸 가드.
# 2026-07-07: jongalab 선정 로직 변경(거래대금 후보 풀 50 + 테마 유동성 조건, SCORE_LOGIC_MIN_DATE 와 동기).
REGIME_MIN_DATE = os.getenv('REGIME_MIN_DATE', '2026-07-07')

# ── 선물 환경 게이트 (core.futures_gate) — 매수 시점 선물 방향으로 총 시드 축소(NXT 전용) ──
# 근거: 종가베팅 손익은 익일 갭에 좌우된다. NQ(미국기술주)+코스피200 야간선물이 둘 다 하락이면
# 갭하락 리스크가 커 노출을 줄인다(reduce-only, ≤1.0 — 상승이어도 베팅을 키우지 않는다).
# 배수는 방향 조합으로 결정: 둘다하락→BOTH_DOWN, 하나하락→ONE_DOWN, 그 외→1.0.
# ⚠️ 자체 백테스트 미검증(표본 부족·시점별 선물 이력 없음) — 통설+손실최소화 목표에 기댄 방어 게이트다.
#    매 적용마다 audit_log('futures_gate')에 그 시점 선물값을 스냅샷으로 남겨 추후 손익과 조인·재튜닝한다.
FUTURES_GATE_ENABLED = os.getenv('FUTURES_GATE_ENABLED', '1') == '1'
# 섹터 차등 감액 on/off. off 면 선물 게이트 감액 없음(현재 signal_executor 는 섹터 게이트만 사용).
FUTURES_SECTOR_GATE_ENABLED = os.getenv('FUTURES_SECTOR_GATE_ENABLED', '1') == '1'
# 적용 거래소(콤마 구분). 기본 krx,nxt — 코스피 축은 그 시각 살아있는 선물을 쓴다:
#   KRX(15:20)=주간선물(K200DF) / NXT(19:50)=야간선물(K200NF). NQ 축은 양쪽 공통.
FUTURES_GATE_VENUES = {v.strip() for v in os.getenv('FUTURES_GATE_VENUES', 'krx,nxt').split(',') if v.strip()}
FUTURES_FLAT_BAND = float(os.getenv('FUTURES_FLAT_BAND', '0.1'))   # ±%p 이내 등락은 보합(하락 아님)으로 취급
# 감액을 하락 '폭'에 비례시킨다: 등락률이 -FLAT_BAND 에서 0, -FULL_CUT_PCT 이상에서 최대컷(강도 1.0).
# 그 사이 선형. NQ -0.5% 같은 작은 하락은 살짝, -2%+ 급락은 최대컷. (이하이면 사실상 노이즈로 덜 반응)
FUTURES_FULL_CUT_PCT = float(os.getenv('FUTURES_FULL_CUT_PCT', '2.0'))
# 축(axis)당 최대 감액률 — 해당 축이 하락이고 섹터 민감도=1.0 일 때 깎는 비율. keep = ∏(1 − MAX_CUT×민감도).
FUTURES_NQ_MAX_CUT = float(os.getenv('FUTURES_NQ_MAX_CUT', '0.5'))    # NQ 축
FUTURES_IDX_MAX_CUT = float(os.getenv('FUTURES_IDX_MAX_CUT', '0.5'))  # 코스피200 야간선물 축
FUTURES_SECTOR_MIN_KEEP = float(os.getenv('FUTURES_SECTOR_MIN_KEEP', '0.25'))  # 종목당 keep 하한(과도 감액 방지)
# 결합 하한 — 레짐(총시드)×선물(종목별 keep)이 곱해져 과도 축소되는 걸 막는다. 한 종목의 최종 배수가
# base 등가중의 이 값 밑으로는 안 내려가게 종목 keep 을 클램프(effective_keep). 보장이 성립하려면
# REGIME_MIN_MULT >= 이 값 이어야 한다(레짐 단독 축소도 이 하한 이상 — 기본 둘 다 0.3).
SEED_COMBINED_MIN_MULT = float(os.getenv('SEED_COMBINED_MIN_MULT', '0.3'))
FUTURES_STALE_SEC = int(os.getenv('FUTURES_STALE_SEC', '900'))    # 야간선물 신선도 한계(초). 넘으면 게이트 미개입
# NQ 등락률 취득용 — jongalab market-indices 엔드포인트(야간선물은 jongalab DB 직접 조회)
JONGALAB_BASE_URL = os.getenv('JONGALAB_BASE_URL', 'http://127.0.0.1:8000')

# ── 거시 이벤트 게이트 (core.macro_gate) — 보유 창의 '예정 이벤트'(FOMC·CPI·고용)로 총 시드 축소 ──
# 선물 게이트가 '이미 실현된 방향'을 재는 것과 달리, 이건 '아직 실현 안 된 이진 이벤트 리스크'를 잰다
# (발표 전엔 선물이 보합이라 futures_gate 가 못 잡음). jongalab DB macro_event(수동 시드 캘린더) 조회.
# 근거: 2026-07-15 백테스트(4/9~7/10 63거래일) — severity 3(FOMC/CPI/고용) 이벤트 밤 선정종목
#   일평균 -0.74% vs 평일 +1.04%(Welch t=-2.27, 혼재일 제외 t=-2.13, 음수일 62% vs 25%).
#   PPI(severity 2)는 +3.6%로 감액 근거 없음 → 관찰 전용(진단 기록만).
MACRO_GATE_ENABLED = os.getenv('MACRO_GATE_ENABLED', '1') == '1'
MACRO_EVENT_KEEP = float(os.getenv('MACRO_EVENT_KEEP', '0.5'))   # sev3 이벤트 밤 시드 keep(≤1.0)
# 관찰 전용 프록시 축(지정학 쇼크 대비: VIX 레벨 / WTI·원달러 급등) — keep 을 계산해 진단에만 남기고
# 감액엔 미적용(임계 미검증). 표본이 쌓이면 승격 판단. 강도는 futures_gate 와 같은 선형 램프(LO=0~HI=1).
MACRO_VIX_LO = float(os.getenv('MACRO_VIX_LO', '25'))            # VIX 레벨 — 강도 0 시작점
MACRO_VIX_HI = float(os.getenv('MACRO_VIX_HI', '35'))            # 강도 1 도달점
MACRO_WTI_BAND = float(os.getenv('MACRO_WTI_BAND', '3.0'))       # WTI 급등 %p — 강도 0 시작점
MACRO_WTI_FULL = float(os.getenv('MACRO_WTI_FULL', '6.0'))
MACRO_FX_BAND = float(os.getenv('MACRO_FX_BAND', '1.0'))         # 원/달러 급등 %p
MACRO_FX_FULL = float(os.getenv('MACRO_FX_FULL', '2.0'))
MACRO_PROXY_MAX_CUT = float(os.getenv('MACRO_PROXY_MAX_CUT', '0.5'))  # 관찰 keep 계산용 축당 최대 감액

# ── 뉴스 베토 (core.news_veto + workers/monitor.py) — 밤사이 중대 악재 종목 개장 즉시 전량매도 ──
# jongalab workers/news_guard.py 가 보유 종목의 밤사이 뉴스(FDA 불승인·계약 파기류)를 OpenAI 로
# 판정해 jongalab DB news_veto_verdict(severe=1)에 기록하면, monitor 가 읽어 가격 무관·가장 이른
# 거래소(NXT 08시대/KRX 09:00)에서 전량 매도한다. 조회 실패·비활성 시 미개입(09:28 백스톱 유지).
NEWS_VETO_ENABLED = os.getenv('NEWS_VETO_ENABLED', '1') == '1'
NEWS_VETO_CACHE_SEC = int(os.getenv('NEWS_VETO_CACHE_SEC', '60'))  # 15초 폴링의 jongalab DB 조회 캐시 TTL

# ── ⚠️ 매매 안전장치 ──
# 'paper': 모의(주문 미전송, 의도만 로깅·기록) / 'live': 실주문 전송. 기본값은 paper.
TRADING_MODE = os.getenv('TRADING_MODE', 'paper').lower()
# 환경변수 킬스위치 (DB kill_switch 플래그와 함께 검사 — 둘 중 하나라도 켜지면 차단)
TRADING_KILL_SWITCH = os.getenv('TRADING_KILL_SWITCH', '0') == '1'
# 키움 모의투자 도메인 사용 여부 (mockapi.kiwoom.com)
KIWOOM_USE_MOCK = os.getenv('KIWOOM_USE_MOCK', '0') == '1'
