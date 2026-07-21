"""YouTube 콘텐츠 수집 워커 (15분마다 실행)"""
import logging
import time

import feedparser
from youtube_transcript_api import YouTubeTranscriptApi

from core.logging_setup import setup_logging
from core.config import OLLAMA_MODEL
from core.prompts import YOUTUBE_ANALYSIS_PROMPT
from core.ai_service import analyze_content, AnalysisTimeout
from core.repository import (
    get_active_sources,
    is_content_processed,
    mark_content_skipped,
    bump_analysis_timeout,
    save_content_analysis,
)
from core.filters import should_save_content, validate_analysis
from core.notifications import send_analysis_alert
from core.ticker import get_tickers

setup_logging()

# 소프트 데드라인: 스케줄러 하드 타임아웃(840s) 안에서 새 영상 처리를 clean 하게 멈추는 컷오프.
# 이 시각을 넘겨 "새로" 시작하지 않으면, 방금 시작한 1건이 최악(OLLAMA_TIMEOUT=480s)까지 끌어도
# 300 + 480 = 780 < 840 이라 하드킬(SIGKILL)이 원천적으로 불가능하다. 초과 시 남은 영상은 다음
# 주기(is_content_processed 게이트)가 이어받으므로 유실 없이 하드킬만 피한다.
RUN_BUDGET_SEC = 300
# 같은 영상이 연속 이 횟수만큼 LLM 타임아웃나면(느린 독성 콘텐츠) content_skip 에 확정 스킵해
# 매 주기 재분석 루프를 끊는다. 타임아웃만 카운트 — 연결·파싱 실패는 세지 않는다(sql/31 참고).
MAX_ANALYSIS_TIMEOUTS = 3


class StockYoutubeAgent:
    def __init__(self):
        self.ytt_api = YouTubeTranscriptApi()

    def get_transcript(self, video_id: str) -> str | None:
        """YouTube 영상의 자막을 가져옴"""
        try:
            transcript_list = self.ytt_api.list(video_id)
            transcript = transcript_list.find_transcript(['ko', 'en'])
            fetched = transcript.fetch()
            text = " ".join([snippet.text for snippet in fetched.snippets])
            logging.info(f"자막 가져오기 성공: {len(text)}자")
            return text
        except Exception as e:
            logging.warning(f"자막 가져오기 실패 ({video_id}): {e}")
            return None

    def run_once(self):
        logging.info("에이전트 실행 시작 (uv)")

        target_channels = get_active_sources('youtube')
        logging.info(f"모니터링 대상 채널: {len(target_channels)}개")

        start = time.monotonic()
        for channel in target_channels:
            elapsed = time.monotonic() - start
            if elapsed > RUN_BUDGET_SEC:
                logging.info(
                    f"예산 소진({elapsed:.0f}s > {RUN_BUDGET_SEC}s) — 남은 채널은 다음 주기에 처리"
                )
                break

            name = channel['name']
            c_id = channel['identifier']
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={c_id}"

            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue

            latest_video = feed.entries[0]
            video_id = latest_video.yt_videoid
            video_title = latest_video.title

            if is_content_processed(video_id):
                continue

            logging.info(f"새 영상 발견 [{name}]: {video_title}")
            script_text = self.get_transcript(video_id)

            if not script_text:
                # 자막은 늦게 생성될 수 있고 재시도가 싸다(피드 조회뿐) — 스킵 확정하지 않는다
                logging.warning("자막이 없어 분석하지 않음")
                continue

            prompt = YOUTUBE_ANALYSIS_PROMPT.format(title=video_title, content=script_text[:3000])
            try:
                result = analyze_content(prompt, raise_on_timeout=True)
            except AnalysisTimeout:
                # 느린 콘텐츠 — 연속 MAX 회 초과 시 확정 스킵해 매 주기 재분석 루프를 끊는다.
                n = bump_analysis_timeout(video_id)
                if n >= MAX_ANALYSIS_TIMEOUTS:
                    logging.warning(f"연속 {n}회 분석 타임아웃 — 확정 스킵(analysis_timeout)")
                    mark_content_skipped(video_id, 'youtube', name, video_title, 'analysis_timeout')
                else:
                    logging.warning(f"분석 타임아웃({n}/{MAX_ANALYSIS_TIMEOUTS}) — 다음 주기 재시도")
                continue

            if not result:
                # 일시적 실패(LLM 오류/파싱 실패) — 다음 주기에 재시도
                logging.warning("AI 분석 결과가 없어 저장하지 않음")
                continue

            # 아래 스킵들은 확정 판정 — 기록해 두지 않으면 15분마다 같은 영상을
            # 재분석(Ollama 수 분/건)해 잡 타임아웃의 원인이 된다.
            if result.sentiment_score == -1:
                mark_content_skipped(video_id, 'youtube', name, video_title, 'irrelevant')
                continue

            if not result.related_companies:
                logging.info("관련 기업(related_companies) 없음 - 스킵합니다.")
                mark_content_skipped(video_id, 'youtube', name, video_title, 'no_companies')
                continue

            analysis_text = f"{video_title}\n{script_text}"
            if not validate_analysis(analysis_text, result.related_companies, video_title):
                logging.warning("환각 감지 - 저장하지 않습니다.")
                mark_content_skipped(video_id, 'youtube', name, video_title, 'hallucination')
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"

            tickers = get_tickers(result.related_companies)

            if not should_save_content(result.sentiment_score, tickers, skip_neutral=False, allow_no_ticker=False):
                mark_content_skipped(video_id, 'youtube', name, video_title, 'no_ticker')
                continue

            save_content_analysis(
                external_id=video_id,
                source_name=name,
                title=video_title,
                content=result.content,
                score=result.sentiment_score,
                source_url=video_url,
                related_tickers=tickers,
                platform='youtube',
                tldr=result.tldr,
                tags=result.tags,
                stocks=result.stocks,
            )

            if result.sentiment_score is not None and 30 <= result.sentiment_score <= 80:
                logging.info(f"[알림 스킵] 점수 {result.sentiment_score}점(30~80 구간)으로 텔레그램 전송 생략")
            else:
                send_analysis_alert(name, video_title, result.content, result.sentiment_score, tickers)
            time.sleep(2)

        logging.info("에이전트 실행 종료")


if __name__ == "__main__":
    agent = StockYoutubeAgent()
    agent.run_once()
