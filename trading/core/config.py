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
TRAIL_PCT = float(os.getenv('TRAIL_PCT', '1.0'))

# ── 매수 눌림(되돌림) 트리거 ──
# 매수 집행 워커(signal_executor)가 윈도우(KRX 15:00~15:20 / NXT 19:30~19:50) 동안 15초 폴링하며
# 종목별 장중 고점(윈도우 시작 후 갱신)을 추종한다. 현재가가 고점 대비 이 %만큼 눌리면(되돌림)
# 그 자리에서 즉시 시장가/IOC 로 매수한다(매도 트레일링 스탑의 매수 버전). 끝까지 안 눌리면
# 데드라인(15:20/19:50)에 시장가로 매수해 후보를 확보한다. 값이 작을수록 작은 눌림에도 매수(빨리 잡되
# 고점 근처), 클수록 더 깊은 눌림을 기다린다(못 잡고 데드라인 시장가로 갈 확률↑).
BUY_PULLBACK_PCT = float(os.getenv('BUY_PULLBACK_PCT', '0.5'))

# ── 하드 손절(칼손절) ──
# 시초가 변동성이 큰 정각~settle(:05) 구간을 포함해, 모니터 가동 내내 평단(avg_price) 대비
# 현재가가 이 %만큼 아래로 떨어지면 settle_plan 유무와 무관하게 즉시 전량 매도한다.
# settle(08:05/09:05)가 손실을 정리하기 전에 갭하락으로 손실이 커지는 것을 막는 안전망.
HARD_STOP_LOSS_PCT = float(os.getenv('HARD_STOP_LOSS_PCT', '2.0'))

# ── 시드 배분기 튜닝 (core.seed_allocator) ──
# 종목당 최대 투입 비율 — 시드 대비(고정금액 아님). 1.0 이상이면 사실상 무제한.
SEED_MAX_NAME_PCT = float(os.getenv('SEED_MAX_NAME_PCT', '0.5'))

# ── 롤링 엣지 게이트 (core.regime_gate) — 최근 선정 종목의 점수 판별력으로 총 시드 축소 ──
# 근거: 엣지가 레짐 의존적이라(봄엔 고점수 우세, 6월엔 역전) 역전 구간엔 자본을 덜 싣는다.
REGIME_GATE_ENABLED = os.getenv('REGIME_GATE_ENABLED', '1') == '1'
REGIME_WINDOW_DAYS = int(os.getenv('REGIME_WINDOW_DAYS', '10'))     # 최근 몇 거래일 표본
REGIME_MIN_SAMPLES = int(os.getenv('REGIME_MIN_SAMPLES', '30'))    # 이보다 적으면 게이트 미개입(1.0)
# 점수 상위½−하위½ 익일시가수익 스프레드(%p). FULL 이상=건강(1.0), INVERT 이하=역전(MIN_MULT)
REGIME_SPLIT_FULL = float(os.getenv('REGIME_SPLIT_FULL', '0.5'))
REGIME_SPLIT_INVERT = float(os.getenv('REGIME_SPLIT_INVERT', '-0.5'))
REGIME_MIN_MULT = float(os.getenv('REGIME_MIN_MULT', '0.3'))       # 역전 시 최소 시드 배수(30%)
# 표본 하한 날짜(YYYY-MM-DD, inclusive) — 이 날짜 이전 report_date 는 레짐 표본에서 제외.
# 근거: 2026-06-26 이전은 선정/스코어 로직이 달라 익일수익 판별력 비교가 무의미(=구로직). 6/29부터만 사용.
# 창(REGIME_WINDOW_DAYS)이 이 날짜를 넘어 충분히 지나면 자연히 무의미해지는 자기소멸 가드.
REGIME_MIN_DATE = os.getenv('REGIME_MIN_DATE', '2026-06-29')

# ── 선물 환경 게이트 (core.futures_gate) — 매수 시점 선물 방향으로 총 시드 축소(NXT 전용) ──
# 근거: 종가베팅 손익은 익일 갭에 좌우된다. NQ(미국기술주)+코스피200 야간선물이 둘 다 하락이면
# 갭하락 리스크가 커 노출을 줄인다(reduce-only, ≤1.0 — 상승이어도 베팅을 키우지 않는다).
# 배수는 방향 조합으로 결정: 둘다하락→BOTH_DOWN, 하나하락→ONE_DOWN, 그 외→1.0.
# ⚠️ 자체 백테스트 미검증(표본 부족·시점별 선물 이력 없음) — 통설+손실최소화 목표에 기댄 방어 게이트다.
#    매 적용마다 audit_log('futures_gate')에 그 시점 선물값을 스냅샷으로 남겨 추후 손익과 조인·재튜닝한다.
FUTURES_GATE_ENABLED = os.getenv('FUTURES_GATE_ENABLED', '1') == '1'
# 섹터 차등 감액 on/off. off 면 선물 게이트 감액 없음(현재 signal_executor 는 섹터 게이트만 사용).
FUTURES_SECTOR_GATE_ENABLED = os.getenv('FUTURES_SECTOR_GATE_ENABLED', '1') == '1'
# 적용 거래소(콤마 구분). 기본 nxt — 19:50엔 야간선물+NQ가 살아있어 익일 갭 신호가 유효하다.
FUTURES_GATE_VENUES = {v.strip() for v in os.getenv('FUTURES_GATE_VENUES', 'nxt').split(',') if v.strip()}
FUTURES_FLAT_BAND = float(os.getenv('FUTURES_FLAT_BAND', '0.1'))   # ±%p 이내 등락은 보합(하락 아님)으로 취급
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

# ── ⚠️ 매매 안전장치 ──
# 'paper': 모의(주문 미전송, 의도만 로깅·기록) / 'live': 실주문 전송. 기본값은 paper.
TRADING_MODE = os.getenv('TRADING_MODE', 'paper').lower()
# 환경변수 킬스위치 (DB kill_switch 플래그와 함께 검사 — 둘 중 하나라도 켜지면 차단)
TRADING_KILL_SWITCH = os.getenv('TRADING_KILL_SWITCH', '0') == '1'
# 키움 모의투자 도메인 사용 여부 (mockapi.kiwoom.com)
KIWOOM_USE_MOCK = os.getenv('KIWOOM_USE_MOCK', '0') == '1'
