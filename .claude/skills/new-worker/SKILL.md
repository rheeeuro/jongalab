---
name: new-worker
description: PM2 cron 백그라운드 워커를 스캐폴드하고 ecosystem.config.js 등록을 안내한다. 인자로 워커 이름(snake_case)을 받는다.
---

# /new-worker <name>

`workers/<name>.py` 에 새 백그라운드 잡을 만든다.

절차:
1. 기존 워커(`workers/daily_digest.py`, `workers/gap_check.py`)를 읽어 패턴 파악:
   - `dotenv` 로드 → `core/*` 임포트 → main 로직 → 로깅.
   - DB 접근은 `core/repository/*`, LLM 은 `core/ai_service` 만 사용.
2. `workers/<name>.py` 생성 (단발 실행 가능한 `if __name__ == "__main__"` 포함).
3. `ecosystem.config.js` 에 등록할 항목을 **제안**한다 (이 파일은 git 미추적이므로
   사용자에게 보여주고 직접 추가하도록 안내):
   ```js
   {
     name: "<name>",
     script: "uv",
     args: "run workers/<name>.py",
     cwd: "/home/euro/dev/jongalab/jongalab",
     interpreter: "none",
     instances: 1,
     autorestart: false,
     cron_restart: "<cron 표현식>",   // 실행 주기를 사용자에게 확인
     env: { NODE_ENV: "production" }
   }
   ```
4. 단발 테스트: `uv run --directory jongalab workers/<name>.py`
