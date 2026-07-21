-- ============================================================
-- 콘텐츠 분석 타임아웃 카운터 (youtube_collector)
-- ------------------------------------------------------------
-- 목적: Ollama 분석이 OLLAMA_TIMEOUT 을 반복해서 넘기는 "느린 독성 콘텐츠"를 감지해
-- 연속 N회(MAX_ANALYSIS_TIMEOUTS) 초과 시 content_skip 에 확정 스킵(reason='analysis_timeout')
-- 시켜 매 주기 재분석 루프를 끊는다.
--
-- 왜 별도 테이블인가: 저장(content_analysis)·확정 스킵(content_skip) 전까지는 is_content_processed
-- 가 False 라 매 주기 재분석된다. 그 사이의 "타임아웃 누적 횟수"를 프로세스 간(잡은 15분마다
-- 새 프로세스)에 지속시킬 곳이 필요하다.
-- 타임아웃(httpx ReadTimeout)만 카운트한다 — 연결 실패(Ollama 다운)·파싱 실패는 세지 않아
-- 일시적 인프라 장애가 정상 콘텐츠를 영구 스킵시키지 않게 한다.
-- 성공/확정 스킵되면 is_content_processed 가 True 라 다시 진입하지 않으므로 행은 그대로 방치돼도
-- 무해하다(리셋 불필요). cleanup_content 가 함께 정리한다.
-- ============================================================
CREATE TABLE IF NOT EXISTS content_analysis_fail (
    external_id   VARCHAR(255) NOT NULL PRIMARY KEY,   -- 유튜브ID or 텔레그램Link
    platform      VARCHAR(20)  NOT NULL DEFAULT 'youtube',
    timeout_count INT          NOT NULL DEFAULT 0,      -- 누적 LLM 타임아웃 횟수
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
