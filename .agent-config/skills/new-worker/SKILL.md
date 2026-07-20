---
name: new-worker
description: 프로젝트 패턴에 맞는 단발 실행형 Python 백그라운드 워커를 만들고 적절한 스케줄러 또는 PM2 등록 방식을 제안한다. 사용자가 새 워커, cron 작업, 또는 Claude의 /new-worker 작업을 요청할 때 사용한다.
---

# 백그라운드 워커 생성

입력 이름은 snake_case로 정규화한다.

1. `jongalab/README.md`의 workers 절을 먼저 읽어 통합 스케줄러 관리 잡과 PM2 cron 잡의 구분을 확인한다.
2. 가장 비슷한 기존 워커 1~2개와 관련 `core/repository/` 코드를 읽는다.
3. `jongalab/workers/<name>.py`를 만들고 단발 실행 가능한 `if __name__ == "__main__"` 진입점을 둔다.
4. DB 접근은 `core/repository/*`, LLM은 `core/ai_service.analyze_content()`만 사용한다.
5. 실행 시간 민감도와 자금 인접 여부에 따라 `workers/scheduler.py` 또는 `ecosystem.config.js` 등록 방식을 선택한다. 실행 주기가 정해지지 않았다면 사용자에게 확인한다.
6. 주요 흐름이나 안전장치가 바뀌면 `jongalab/README.md`도 갱신한다.
7. `uv run --directory jongalab python -m py_compile workers/<name>.py`를 통과시킨 뒤 안전한 경우 단발 실행으로 검증한다.

`ecosystem.config.js`를 수정하면 프로젝트 종료 훅이 신규 PM2 앱만 등록한다. 기존 앱이나 cron 워커를 임의로 재시작하지 않는다.
