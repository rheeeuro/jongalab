#!/usr/bin/env bash
# 키움 + KIS 액세스 토큰 일괄 재발급 (매일 1회 PM2 cron: token-refresh).
# 두 토큰은 서로 다른 서브프로젝트 환경(uv)·DB 스키마를 쓰므로 각자 디렉터리에서 실행한다.
# 하나가 실패해도 다른 하나는 진행하도록 '; ' 로 연결한다(set -e 미사용).
set +e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[refresh_tokens] 키움 토큰 재발급"
uv run --directory "$ROOT/kiwoom" workers/kiwoom_token_refresh.py

echo "[refresh_tokens] KIS 토큰 재발급"
uv run --directory "$ROOT/jongalab" workers/kis_token_refresh.py

echo "[refresh_tokens] 완료"
