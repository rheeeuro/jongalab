"""텔레그램 채널 리스너 워커 (항시 실행)

경로가 두 개다 — **일반 채널**(platform=telegram)은 메시지마다 Ollama 분석(건당 100~300초,
CPU 추론이라 직렬)이고, **뉴스 채널**(platform=news)은 LLM 없이 사전매칭 후 즉시 적재한다.
같은 프로세스에서 도는 이유는 Telethon 세션 파일을 두 프로세스가 공유할 수 없기 때문이다.

그래서 LLM 호출은 `asyncio.to_thread` 로 워커 스레드에 내보내 **이벤트 루프를 막지 않는다**
(2026-07-29 채널 확장 — 이전 동기 호출은 분석 중 루프 전체를 세워서 뉴스 적재가 07~09시대에
평균 145초·최대 22분 밀렸고, news_guard 의 개장 전 악재 판정이 09:28 청산 이후로 밀릴 수 있었다).
분석 자체는 세마포어로 1건씩만 돌린다(Ollama CPU 직렬 — 동시 실행은 서로 느려질 뿐).
"""
import asyncio
import hashlib
import os
import logging
import sys
import time

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage, WebPage

from core.logging_setup import setup_logging
from core.config import TELEGRAM_API_ID, TELEGRAM_API_HASH
from core.prompts import TELEGRAM_ANALYSIS_PROMPT
from core.ai_service import analyze_content
from core.repository import (
    get_active_sources,
    mark_content_skipped,
    save_content_analysis,
    save_news_mentions,
)
from core.filters import should_save_content, validate_analysis
from core.notifications import send_analysis_alert
from core.ticker import get_tickers
from core.news_matcher import match_companies

setup_logging()


class SuicideOnOldMessageFilter(logging.Filter):
    """특정 에러 발생 시 자동 재시작 트리거 (Telethon 세션/보안 에러 대응)"""
    def filter(self, record):
        msg = record.getMessage()
        if "Server sent a very old message" in msg or "Too many messages had to be ignored consecutively" in msg:
            print(f"\n[치명적 에러 감지] {msg}", flush=True)
            print("Telethon 세션/보안 에러 발생! PM2를 통한 깨끗한 재시작을 위해 강제 종료합니다...", flush=True)
            os._exit(1)
        return True


if logging.root.handlers:
    for handler in logging.root.handlers:
        handler.addFilter(SuicideOnOldMessageFilter())
else:
    logging.getLogger().addFilter(SuicideOnOldMessageFilter())


SESSION_NAME = 'stock_session'
MIN_TEXT_LENGTH = 30

# LLM 경로 부하 제어 (2026-07-29 일반 채널 15→28개 확장)
# 실측 처리량: 건당 평균 152초(p50 111s) → 시간당 ~24건이 상한.
MAX_PENDING_ANALYSIS = 40   # 대기 큐 상한. 초과분은 분석 없이 폐기('backlog' 기록)
                            # — 쌓아두면 결과가 몇 시간 뒤에 나와 재료로서 가치가 없고 메모리만 는다.
DEDUP_TTL_SEC = 6 * 3600    # 이 시간 내 같은 본문(공백 정규화)은 재분석 안 함 — 채널 간 전달 중복 제거
DEDUP_MAX_KEYS = 5000       # 지문 캐시 상한(초과 시 만료분 정리)
QUEUE_WARN_DEPTH = 10       # 대기가 이 이상이면 경고 로그(적체 가시화 — 채널 수 조정 판단 근거)

_llm_lock = asyncio.Lock()   # Ollama 는 CPU 직렬 — 동시 1건
_pending_analysis = 0
_seen_texts: dict[str, float] = {}


def _is_duplicate_text(text: str) -> bool:
    """DEDUP_TTL_SEC 내 같은 본문을 이미 받았으면 True (아니면 지문을 기록하고 False).

    여러 채널이 같은 리서치/속보를 전달하면 원문이 동일한데, LLM 재분석은 건당 2~5분이라
    가장 값싼 절감이다. 결과도 같은 내용이라 잃는 정보가 없다.
    """
    now = time.time()
    key = hashlib.sha1(" ".join(text.split()).encode()).hexdigest()
    if now - _seen_texts.get(key, 0.0) < DEDUP_TTL_SEC:
        return True

    if len(_seen_texts) > DEDUP_MAX_KEYS:
        for k, seen_at in list(_seen_texts.items()):
            if now - seen_at >= DEDUP_TTL_SEC:
                del _seen_texts[k]
    _seen_texts[key] = now
    return False


def get_target_channels(platform: str = 'telegram'):
    """DB에서 감시할 채널 목록을 가져와 ID 타입 변환 (platform: telegram / news)"""
    try:
        rows = get_active_sources(platform)
        channels = []
        for row in rows:
            ident = row['identifier']
            if ident.startswith('-') or ident.isdigit():
                channels.append(int(ident))
            else:
                channels.append(ident)

        logging.info(f"[{platform}] 감시 대상 채널 로드 완료: {len(channels)}개")
        return channels
    except Exception as e:
        logging.error(f"[{platform}] 채널 목록 로드 실패: {e}")
        return []


def _extract_text_and_link(event, chat) -> tuple[str, str]:
    """메시지 본문(+링크 프리뷰)과 메시지 URL 을 뽑는다 (일반/뉴스 핸들러 공통)."""
    text = event.message.message or ""

    media = event.message.media
    if isinstance(media, MessageMediaWebPage) and isinstance(media.webpage, WebPage):
        wp = media.webpage
        preview_parts = []
        if wp.title:
            preview_parts.append(wp.title)
        if wp.description:
            preview_parts.append(wp.description)
        if preview_parts:
            preview_text = "\n".join(preview_parts)
            text = f"{text}\n\n{preview_text}".strip() if text else preview_text

    username = getattr(chat, 'username', None)
    if username:
        msg_link = f"https://t.me/{username}/{event.message.id}"
    else:
        cid = str(chat.id)
        if cid.startswith('-100'):
            cid = cid[4:]
        msg_link = f"https://t.me/c/{cid}/{event.message.id}"

    return text, msg_link


def analyze_and_store(channel_name: str, text: str, msg_link: str) -> None:
    """LLM 분석 → 저장 → 알림. **워커 스레드에서 실행**되므로 블로킹 호출만 담는다.

    이벤트 루프를 건드리지 않게 Telethon 객체는 받지 않고 추출된 값만 받는다.
    """
    prompt = TELEGRAM_ANALYSIS_PROMPT.format(text=text)
    result = analyze_content(prompt)

    if not result:
        logging.info(f"[{channel_name}] 분석 결과 없음 - 저장하지 않습니다.")
        return

    if result.sentiment_score == -1:
        logging.info(f"[{channel_name}] 주식 무관 판정 - 저장하지 않습니다.")
        return

    if not result.related_companies:
        logging.info(f"[{channel_name}] 관련 기업(related_companies) 없음 - 스킵합니다.")
        return

    if not validate_analysis(text, result.related_companies, result.title):
        logging.warning(f"[{channel_name}] 환각 감지 - 저장하지 않습니다.")
        return

    tickers = get_tickers(result.related_companies)

    if not should_save_content(result.sentiment_score, tickers, skip_neutral=True, allow_no_ticker=False):
        return

    save_content_analysis(
        external_id=msg_link,
        source_name=channel_name,
        title=result.title,
        content=result.content,
        score=result.sentiment_score,
        source_url=msg_link,
        related_tickers=tickers,
        platform='telegram',
        tldr=result.tldr,
        tags=result.tags,
        stocks=result.stocks,
    )

    if result.sentiment_score is not None and 30 <= result.sentiment_score <= 80:
        logging.info(f"[알림 스킵] 점수 {result.sentiment_score}점(30~80 구간)으로 텔레그램 전송 생략")
    else:
        # 원문을 인용블록으로 그대로 싣고 tldr 한 줄만 덧붙인다(요약본만 보내던 방식 대체)
        send_analysis_alert(
            channel_name,
            result.title,
            result.content,
            result.sentiment_score,
            tickers,
            original_text=text,
            tldr=result.tldr,
            source_url=msg_link,
        )


while True:
    try:
        logging.info("텔레그램 클라이언트 메모리 초기화 및 접속 시도...")
        client = TelegramClient(SESSION_NAME, TELEGRAM_API_ID, TELEGRAM_API_HASH)

        telegram_chats = get_target_channels('telegram')
        news_chats = get_target_channels('news')
        target_chats = telegram_chats + news_chats

        if not target_chats:
            logging.warning("감시할 채널이 없습니다. DB를 확인해주세요.")
            sys.exit()

        logging.info(
            f"감시 시작 — 텔레그램 {len(telegram_chats)}개 / 뉴스 {len(news_chats)}개"
        )

        async def handler(event):
            """일반 채널: 값싼 필터만 루프에서 하고, LLM 분석은 스레드로 넘긴다."""
            global _pending_analysis

            chat = await event.get_chat()
            channel_name = chat.title if getattr(chat, 'title', None) else "Unknown"

            text, msg_link = _extract_text_and_link(event, chat)
            if not text:
                return

            logging.info(f"[{channel_name}] 새 메시지 도착 (분석 대기 {_pending_analysis}건)")

            if len(text) < MIN_TEXT_LENGTH:
                logging.info(f"[스킵] 메시지가 너무 짧음 ({len(text)}자 < {MIN_TEXT_LENGTH}자)")
                return

            if _is_duplicate_text(text):
                logging.info(f"[{channel_name}] 최근 {DEDUP_TTL_SEC // 3600}시간 내 동일 본문 — 재분석 스킵")
                mark_content_skipped(msg_link, 'telegram', channel_name, None, 'duplicate')
                return

            if _pending_analysis >= MAX_PENDING_ANALYSIS:
                logging.warning(
                    f"[{channel_name}] 분석 대기 {_pending_analysis}건(상한 {MAX_PENDING_ANALYSIS}) — "
                    f"이 메시지는 분석 없이 폐기합니다. LLM 처리량 초과 상태입니다."
                )
                mark_content_skipped(msg_link, 'telegram', channel_name, None, 'backlog')
                return

            if _pending_analysis >= QUEUE_WARN_DEPTH:
                logging.warning(f"분석 적체 {_pending_analysis}건 — 해소에 약 {_pending_analysis * 152 // 60}분 예상")

            _pending_analysis += 1
            try:
                async with _llm_lock:
                    await asyncio.to_thread(analyze_and_store, channel_name, text, msg_link)
            except Exception as e:
                logging.error(f"[{channel_name}] 분석 처리 실패: {e}")
            finally:
                _pending_analysis -= 1

        async def news_handler(event):
            """뉴스 속보 채널 전용 경량 경로: LLM 없이 종목 사전매칭만 → news_mention 적재.
            하루 1000+건이라 메시지당 LLM 분석은 하지 않는다(재료 감지 신호로만 사용).

            매칭 실패분은 content_skip(platform='news', reason='no_match') 에 남긴다 —
            적재분/(적재분+no_match) 가 채널별 수집률이다(2026-07-30 추가).
            """
            chat = await event.get_chat()
            channel_name = chat.title if getattr(chat, 'title', None) else "Unknown"

            text, msg_link = _extract_text_and_link(event, chat)
            if not text:
                return

            headline = text.replace("\n", " ").strip()[:500]

            matches = match_companies(text)
            if not matches:
                # 분모 계측 — 사명이 없어 떨어진 메시지를 흔적 없이 버리면 '수집률'을 알 수 없다
                # (채널이 원래 적게 보내는지, 우리가 많이 버리는지 구분 불가). content_skip 에
                # 남겨 ① 채널별 수집률 ② 놓친 헤드라인 코퍼스(테마 계층 설계 근거)를 확보한다.
                # 정책·지역·제품 뉴스가 여기 쌓인다(예: "호남권 반도체 국가산단 후보지 지정").
                mark_content_skipped(msg_link, 'news', channel_name, headline, 'no_match')
                return

            published_at = None
            if getattr(event.message, 'date', None):
                # UTC aware → 로컬 naive (created_at·CURDATE 기준과 정합)
                published_at = event.message.date.astimezone().replace(tzinfo=None)

            rows = [{
                "ticker": m["ticker"],
                "company_name": m["name"],
                "headline": headline,
                "source_url": msg_link,
                "channel_name": channel_name,
                "published_at": published_at,
            } for m in matches]

            inserted = save_news_mentions(rows)
            if inserted:
                names = ", ".join(m["name"] for m in matches)
                logging.info(f"[뉴스][{channel_name}] {inserted}건 언급 적재: {names}")

        if telegram_chats:
            client.add_event_handler(handler, events.NewMessage(chats=telegram_chats))
        if news_chats:
            client.add_event_handler(news_handler, events.NewMessage(chats=news_chats))

        client.start()
        logging.info("텔레그램 서버 연결 성공! 메시지 감시를 시작합니다.")
        client.run_until_disconnected()

    except Exception as e:
        logging.error(f"텔레그램 연결 끊김 또는 에러 발생: {e}")
        logging.info("10초 후 서버에 자동 재접속을 시도합니다...")
        time.sleep(10)
