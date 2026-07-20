---
name: run-api
description: jongalab FastAPI 서버를 필요할 때 백그라운드로 기동하고 대상 엔드포인트의 상태와 응답 shape를 확인한다. 사용자가 API 실행, 라우터 검증, 엔드포인트 테스트, 또는 Claude의 /run-api 작업을 요청할 때 사용한다.
---

# FastAPI 실행 및 확인

1. `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs`로 기존 서버를 확인한다.
2. 정상 서버가 없으면 `uv run --directory jongalab uvicorn api:app --host 127.0.0.1 --port 8000`을 지속 실행 세션으로 시작한다.
3. DB나 Ollama가 필요한 경로라면 먼저 `docker ps`로 관련 컨테이너 상태를 확인한다.
4. `/docs`와 영향받은 엔드포인트를 `curl`로 호출해 HTTP 상태와 응답 shape를 확인한다.
5. 새로 시작한 프로세스와 검증 결과를 보고한다. 기존 프로세스는 임의로 종료하지 않는다.
