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

# OpenAI 설정 (일간 리포트용)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-5.4-nano')

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
