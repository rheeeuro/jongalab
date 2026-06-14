"""
kiwoom 데이터 서버 설정 — DB 설정만 필요(토큰 저장 공유 DB).
키움 APP_KEY/SECRET_KEY 는 core.kiwoom_api.KiwoomConfig 가 os.getenv 로 직접 읽는다.

cwd 가 kiwoom/ 이므로 리포지토리 루트(.env)를 절대경로로 명시 로드한다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# kiwoom/core/config.py → parents[2] == 리포지토리 루트
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ROOT_ENV)

# DB 설정 (jongalab 과 동일 MariaDB 서버, kiwoom_token 은 전용 kiwoom DB 에 보관)
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'user': os.getenv('DB_USER', 'stock_user'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('KIWOOM_DB_NAME', 'kiwoom'),
    'port': int(os.getenv('DB_PORT', '3307')),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'use_unicode': True,
}
