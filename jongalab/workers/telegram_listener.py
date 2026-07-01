"""텔레그램 채널 리스너 워커 (항시 실행)"""
import asyncio
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
from core.repository import get_active_sources, save_content_analysis, save_news_mentions
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
            chat = await event.get_chat()
            channel_name = chat.title if getattr(chat, 'title', None) else "Unknown"

            text, msg_link = _extract_text_and_link(event, chat)
            if not text:
                return

            logging.info(f"[{channel_name}] 새 메시지 도착")

            if len(text) < MIN_TEXT_LENGTH:
                logging.info(f"[스킵] 메시지가 너무 짧음 ({len(text)}자 < {MIN_TEXT_LENGTH}자)")
                return

            prompt = TELEGRAM_ANALYSIS_PROMPT.format(text=text)
            result = analyze_content(prompt)

            if not result:
                logging.info(f"[{channel_name}] 분석 결과 없음 - 저장하지 않습니다.")
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
            )

            if result.sentiment_score is not None and 30 <= result.sentiment_score <= 80:
                logging.info(f"[알림 스킵] 점수 {result.sentiment_score}점(30~80 구간)으로 텔레그램 전송 생략")
            else:
                send_analysis_alert(channel_name, result.title, result.content, result.sentiment_score, tickers)

        async def news_handler(event):
            """뉴스 속보 채널 전용 경량 경로: LLM 없이 종목 사전매칭만 → news_mention 적재.
            하루 1000+건이라 메시지당 LLM 분석은 하지 않는다(재료 감지 신호로만 사용)."""
            chat = await event.get_chat()
            channel_name = chat.title if getattr(chat, 'title', None) else "Unknown"

            text, msg_link = _extract_text_and_link(event, chat)
            if not text:
                return

            matches = match_companies(text)
            if not matches:
                return

            headline = text.replace("\n", " ").strip()[:500]
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
