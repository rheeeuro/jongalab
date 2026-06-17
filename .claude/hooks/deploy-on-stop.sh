#!/usr/bin/env bash
# Stop: 이번 턴에 누적된 코드 변경(.claude/.pending-changes)을 분류해서
#   - 프론트 변경 → npm run build 후 jongalab-fe 재시작
#   - api.py/routers/core 변경 → jongalab-be 재시작
#   - core 공유 변경 / telegram_listener 변경 → jongalab-telegram 재시작
#   - cron 워커 변경 → 재시작하지 않음(다음 cron 실행 때 자동 반영) — 안내만
# pm2 가 없거나 해당 앱이 online 이 아니면 조용히 건너뛴다.
# 빌드 실패 시 stop 을 막아(decision:block) Claude 가 이어서 고치게 한다.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PENDING="$ROOT/.claude/.pending-changes"

# 무한 루프 방지: 이미 stop 훅으로 재진입한 상태면 block 하지 않는다.
STOP_ACTIVE=$(python3 -c '
import json,sys
try: print("1" if json.load(sys.stdin).get("stop_hook_active") else "0")
except Exception: print("0")
' 2>/dev/null || echo "0")

[ -s "$PENDING" ] || { rm -f "$PENDING"; exit 0; }

# 변경 파일 중복 제거
mapfile -t FILES < <(sort -u "$PENDING")

NEED_WEB=0; NEED_API=0; NEED_TG=0; NEED_KIWOOM=0; NEED_TAPI=0; NEED_TWEB=0; NEED_TMON=0
declare -A CRON_HIT=()

for f in "${FILES[@]}"; do
  # ── jongalab (메인 앱) ──
  case "$f" in
    */jongalab/frontend/*)                        NEED_WEB=1 ;;
  esac
  case "$f" in
    */jongalab/api.py|*/jongalab/routers/*.py)    NEED_API=1 ;;
  esac
  case "$f" in
    */jongalab/core/*.py)                         NEED_API=1; NEED_TG=1 ;;   # core 는 api·telegram 공유
    */jongalab/workers/telegram_listener.py)      NEED_TG=1 ;;
    */jongalab/workers/youtube_collector.py)      CRON_HIT[jongalab-collector]=1 ;;
    */jongalab/workers/daily_digest.py)           CRON_HIT[jongalab-daily-report]=1 ;;
    */jongalab/workers/gap_check.py)              CRON_HIT[jongalab-gap-check]=1 ;;
    */jongalab/workers/closing_bet.py)            CRON_HIT[jongalab-closing-bet]=1 ;;
  esac
  # ── kiwoom (데이터 전용 서버) ──
  case "$f" in
    */kiwoom/api.py|*/kiwoom/core/*.py)           NEED_KIWOOM=1 ;;
    */kiwoom/workers/kiwoom_token_refresh.py)     CRON_HIT[kiwoom-token-refresh]=1 ;;
  esac
  # ── trading (자동매매 집행 전용 도메인) ──
  case "$f" in
    */trading/frontend/*)                         NEED_TWEB=1 ;;
    */trading/api.py|*/trading/core/*.py)         NEED_TAPI=1; NEED_TMON=1 ;;  # core 는 모니터도 공유
    */trading/workers/monitor.py)                 NEED_TMON=1 ;;               # 상시 워커 → 재시작
    */trading/workers/signal_executor.py)         CRON_HIT[trading-signal-executor]=1 ;;
    */trading/workers/settle.py)                  CRON_HIT[trading-settle-nxt]=1; CRON_HIT[trading-settle-krx]=1 ;;
    */trading/workers/reconcile.py)               CRON_HIT[trading-reconcile]=1 ;;
  esac
done

rm -f "$PENDING"   # 소비 완료

command -v pm2 >/dev/null 2>&1 || exit 0   # pm2 없으면 종료

# pm2 앱이 online 인지 확인
is_online() {
  pm2 jlist 2>/dev/null | python3 -c '
import json,sys
name=sys.argv[1]
try: apps=json.load(sys.stdin)
except Exception: sys.exit(1)
for a in apps:
    if a.get("name")==name and a.get("pm2_env",{}).get("status")=="online":
        sys.exit(0)
sys.exit(1)
' "$1"
}

NOTES=()
BUILD_FAILED=""

# 1) 프론트: 빌드 후 재시작
if [ "$NEED_WEB" = "1" ]; then
  echo "🛠  frontend 변경 감지 → npm run build" >&2
  BUILD_OUT=$(cd "$ROOT/jongalab/frontend" && npm run build 2>&1)
  if [ $? -ne 0 ]; then
    BUILD_FAILED="$BUILD_OUT"
  else
    if is_online jongalab-fe; then
      pm2 restart jongalab-fe >/dev/null 2>&1 && NOTES+=("✅ jongalab-fe 빌드+재시작")
    else
      NOTES+=("ℹ️ jongalab-fe 빌드 성공(앱이 online 아님 — 재시작 생략)")
    fi
  fi
fi

# 2) 백엔드 API
if [ "$NEED_API" = "1" ]; then
  if is_online jongalab-be; then
    pm2 restart jongalab-be >/dev/null 2>&1 && NOTES+=("✅ jongalab-be 재시작")
  else
    NOTES+=("ℹ️ jongalab-be 변경됨(앱이 online 아님 — 재시작 생략)")
  fi
fi

# 2-1) 키움 데이터 API (별도 서버)
if [ "$NEED_KIWOOM" = "1" ]; then
  if is_online kiwoom-api; then
    pm2 restart kiwoom-api >/dev/null 2>&1 && NOTES+=("✅ kiwoom-api 재시작")
  else
    NOTES+=("ℹ️ kiwoom-api 변경됨(앱이 online 아님 — 재시작 생략)")
  fi
fi

# 2-2) 트레이딩 집행 API (별도 서버)
if [ "$NEED_TAPI" = "1" ]; then
  if is_online trading-api; then
    pm2 restart trading-api >/dev/null 2>&1 && NOTES+=("✅ trading-api 재시작")
  else
    NOTES+=("ℹ️ trading-api 변경됨(앱이 online 아님 — 재시작 생략)")
  fi
fi

# 2-2b) 트레이딩 모니터 (상시 워커)
if [ "$NEED_TMON" = "1" ]; then
  if is_online trading-monitor; then
    pm2 restart trading-monitor >/dev/null 2>&1 && NOTES+=("✅ trading-monitor 재시작")
  else
    NOTES+=("ℹ️ trading-monitor 변경됨(앱이 online 아님 — 재시작 생략)")
  fi
fi

# 2-3) 트레이딩 대시보드: 빌드 후 재시작 (node_modules 미설치면 건너뜀)
if [ "$NEED_TWEB" = "1" ]; then
  if [ ! -d "$ROOT/trading/frontend/node_modules" ]; then
    NOTES+=("ℹ️ trading-fe 변경됨(node_modules 없음 — npm install 전이라 빌드 생략)")
  else
    echo "🛠  trading/frontend 변경 감지 → npm run build" >&2
    TBUILD_OUT=$(cd "$ROOT/trading/frontend" && npm run build 2>&1)
    if [ $? -ne 0 ]; then
      BUILD_FAILED="${BUILD_FAILED}${BUILD_FAILED:+$'\n'}[trading-fe] $TBUILD_OUT"
    elif is_online trading-fe; then
      pm2 restart trading-fe >/dev/null 2>&1 && NOTES+=("✅ trading-fe 빌드+재시작")
    else
      NOTES+=("ℹ️ trading-fe 빌드 성공(앱이 online 아님 — 재시작 생략)")
    fi
  fi
fi

# 3) 텔레그램 리스너(상시)
if [ "$NEED_TG" = "1" ]; then
  if is_online jongalab-telegram; then
    pm2 restart jongalab-telegram >/dev/null 2>&1 && NOTES+=("✅ jongalab-telegram 재시작")
  else
    NOTES+=("ℹ️ jongalab-telegram 변경됨(앱이 online 아님 — 재시작 생략)")
  fi
fi

# 4) cron 워커: 재시작 금지(다음 cron 실행 때 새 프로세스로 자동 반영)
for app in "${!CRON_HIT[@]}"; do
  NOTES+=("⏰ $app 변경됨 — cron 워커라 재시작 안 함(다음 스케줄 실행 때 자동 반영)")
done

# 빌드 실패 처리: stop 을 막아 Claude 가 이어서 고치게 한다(루프 방지 가드 포함)
if [ -n "$BUILD_FAILED" ]; then
  if [ "$STOP_ACTIVE" = "1" ]; then
    echo "❌ frontend 빌드 실패(재진입 상태라 차단하지 않음):" >&2
    echo "$BUILD_FAILED" | tail -30 >&2
    exit 0
  fi
  REASON=$(printf '프론트 빌드(npm run build) 실패로 jongalab-fe 을 재시작하지 못했습니다. 아래 오류를 고치세요:\n%s' "$(echo "$BUILD_FAILED" | tail -30)")
  python3 -c 'import json,sys; print(json.dumps({"decision":"block","reason":sys.argv[1]}))' "$REASON"
  exit 0
fi

# 정상 요약
[ ${#NOTES[@]} -gt 0 ] && printf '%s\n' "${NOTES[@]}" >&2
exit 0
