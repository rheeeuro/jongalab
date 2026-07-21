"""
공통 설정 모듈 - DB 설정, 환경변수, 상수를 한 곳에서 관리
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# cwd 가 jongalab/ 이므로 리포지토리 루트(.env)를 절대경로로 명시 로드한다.
# jongalab/core/config.py → parents[2] == 리포지토리 루트
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# DB 설정
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'user': os.getenv('DB_USER', 'stock_user'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('JONGALAB_DB_NAME', 'jongalab'),
    'port': int(os.getenv('DB_PORT', '3307')),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'use_unicode': True,
}

# trading DB 설정 — closing_bet 이 매수 시그널(trade_signal)을 적재하는 대상.
# (같은 MariaDB 서버, 스키마만 분리. trading 도메인이 소비한다.)
TRADING_DB_CONFIG = {**DB_CONFIG, 'database': os.getenv('TRADING_DB_NAME', 'trading')}

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# 텔레그램 API (Telethon)
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')

# AI 모델 설정 (Ollama)
OLLAMA_HOST = 'http://127.0.0.1:11434'
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'exaone3.5:7.8b')
# Ollama 호출 상한(초). 콘텐츠 1건 분석이 이 시간을 넘기면 httpx 가 읽기 타임아웃을 던진다
# (무한정 늘어지는 분석이 잡 전체를 타임아웃시키는 것을 막는 백스톱). 관측 최대 ~435s 위 + 잡
# 타임아웃(840s) 아래로 잡는다 — youtube_collector 소프트 데드라인과 합쳐 하드킬을 원천 차단.
OLLAMA_TIMEOUT = int(os.getenv('OLLAMA_TIMEOUT', '480'))

# OpenAI 설정 (일간 리포트용)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-5.4-nano')

# ── 뉴스 베토 감시 (workers/news_guard.py) ──
# 보유 종목의 밤사이 중대 악재를 OpenAI 로 판정해 news_veto_verdict 에 기록 →
# trading monitor 가 severe=1 종목을 개장 즉시 전량 매도한다.
NEWS_GUARD_POLL_SEC = int(os.getenv('NEWS_GUARD_POLL_SEC', '300'))            # 판정 폴링 주기(초)
# severe 발동 최소 확신도(0~100) — 미만이면 severe=0 으로 기록만(오탐 완충)
NEWS_GUARD_MIN_CONFIDENCE = int(os.getenv('NEWS_GUARD_MIN_CONFIDENCE', '85'))
NEWS_GUARD_MAX_HEADLINES = int(os.getenv('NEWS_GUARD_MAX_HEADLINES', '30'))   # 종목당 판정 헤드라인 상한

# 스코어/선정 로직 유효 시작일(YYYY-MM-DD, inclusive) — 이 날짜 이전은 구 로직이라
# 가중치 튜닝 백테스트 표본에서 제외한다. weight_tuner 가 분석 주 시작을 이 날짜로 클램프.
# (trading 쪽 레짐 게이트의 REGIME_MIN_DATE 와 같은 로직 변경을 가리킴 — 도메인 분리라 값만 맞춘다.)
# 2026-07-07: 거래대금 후보 풀 30→50 확대 + 테마 보너스 거래대금 상위 50 교집합 조건 반영.
SCORE_LOGIC_MIN_DATE = os.getenv('SCORE_LOGIC_MIN_DATE', '2026-07-07')

# Edge Ledger 왕복 거래비용(%) — 모든 가설 기대값은 이 값 차감 후로만 비교한다(README §5-2 비용 차감 원칙).
# 기본 0.25 = 세금 0.15 + 수수료 + 슬리피지 보수 추정. trading `fill` 실측치로 분기별 보정하고
# 보정 이력은 docs/plan/03-edge-ledger.md 에 기록한다.
EDGE_COST_PCT = float(os.getenv('EDGE_COST_PCT', '0.25'))

# 선정 레이어 모드(Phase 4). closing_bet 의 selected 판정·trade_signal 핸드오프에만 영향 —
# 점수 계산·저장·rank_no 는 모든 모드에서 불변(대조군 평가·프론트 표시용). trading 도메인 무변경.
#   legacy : 현행 점수 rank_no ≤ TRADED_TOP_N (기본값 — 데이터 게이트 통과 전까지 유지)
#   hybrid : live rule 매칭 우선 + 잔여 슬롯 점수순 (총 상한 TRADED_TOP_N)
#   rules  : live rule 매칭 합집합만(상한 초과 시 rule 기대값 순). 매칭 0 = 그날 무거래
# veto(감액·제외) rule 은 모드와 무관하게 선정 직전 적용. 롤백: 이 값을 legacy 로 되돌리면 즉시 원복.
EDGE_SELECTION_MODE = os.getenv('EDGE_SELECTION_MODE', 'legacy')

# 키움 데이터 서버 (별도 FastAPI, localhost) — core.kiwoom_client 가 호출
KIWOOM_BASE_URL = os.getenv('KIWOOM_BASE_URL', 'http://127.0.0.1:8001')

# 한국투자증권(KIS) Open API — 시장 탭 선물 시세(코스피200 야간선물) 조회용.
# core.kis_client.KisRestClient 가 사용하며, 토큰은 kis_token 테이블에 단일행 보관.
KIS_APP_KEY = os.getenv('KIS_APP_KEY', '')
KIS_SECRET_KEY = os.getenv('KIS_SECRET_KEY', '')
KIS_BASE_URL = os.getenv('KIS_BASE_URL', 'https://openapi.koreainvestment.com:9443')
# 코스피200 선물 근월물 단축코드(예: 'A01609' = 2026년 9월물). 보통은 비워두면
# kis_client.kospi200_front_month_code() 가 분기 만기 기준으로 근월물을 자동 산출한다.
# 강제 지정이 필요할 때만 .env 로 설정. 야간세션(KRX 야간거래)도 동일 근월물 코드를 쓴다.
KIS_KOSPI200_FUT_CODE = os.getenv('KIS_KOSPI200_FUT_CODE', '')
# KIS 실시간 WebSocket 접속 주소 (야간선물 실시간체결 H0MFCNT0 구독용).
KIS_WS_URL = os.getenv('KIS_WS_URL', 'ws://ops.koreainvestment.com:21000')
