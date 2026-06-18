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
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')

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

# ── ⚠️ 매매 안전장치 ──
# 'paper': 모의(주문 미전송, 의도만 로깅·기록) / 'live': 실주문 전송. 기본값은 paper.
TRADING_MODE = os.getenv('TRADING_MODE', 'paper').lower()
# 환경변수 킬스위치 (DB kill_switch 플래그와 함께 검사 — 둘 중 하나라도 켜지면 차단)
TRADING_KILL_SWITCH = os.getenv('TRADING_KILL_SWITCH', '0') == '1'
# 키움 모의투자 도메인 사용 여부 (mockapi.kiwoom.com)
KIWOOM_USE_MOCK = os.getenv('KIWOOM_USE_MOCK', '0') == '1'
