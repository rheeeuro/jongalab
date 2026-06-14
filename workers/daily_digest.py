"""일일 요약 리포트 생성 워커 (국장, 평일 7:50am)"""
import json
import logging
from datetime import datetime

from openai import OpenAI

from core.logging_setup import setup_logging
from core.config import OPENAI_API_KEY, OPENAI_MODEL
from core.prompts import DAILY_DIGEST_PROMPT
from core.ai_utils import parse_ai_json
from core.repository import get_recent_analyses, save_daily_summary
from core.notifications import send_daily_digest_alert

setup_logging()

_openai_client = OpenAI(api_key=OPENAI_API_KEY)


def generate_daily_report():
    try:
        logging.info("오늘의 데이터 조회 중...")
        rows = get_recent_analyses(hours=15)

        if not rows:
            logging.info("오늘 수집된 데이터가 없습니다. (분석 건너뜀)")
            return

        reports_text = ""
        for idx, row in enumerate(rows):
            raw_tickers = row.get('related_tickers', '[]')
            if isinstance(raw_tickers, str):
                try:
                    raw_tickers = json.loads(raw_tickers)
                except Exception:
                    raw_tickers = []
            ticker_str = ", ".join(
                f"{t['name']}({t['ticker']})" for t in raw_tickers if isinstance(t, dict)
            ) if raw_tickers else "없음"
            reports_text += f"""
        [분석 {idx+1}]
        - 출처: {row['source_name']} (점수: {row['sentiment_score']}점)
        - 제목: {row['title']}
        - 관련 티커: {ticker_str}
        - 내용 요약: {row['analysis_content'][:300]}...
        --------------------------------
        """

        prompt = DAILY_DIGEST_PROMPT.format(reports_text=reports_text)

        logging.info(f"ChatGPT 분석 시작 (모델: {OPENAI_MODEL}, 데이터 {len(rows)}건)...")

        response = _openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,
        )

        raw_content = response.choices[0].message.content
        logging.info(f"ChatGPT 원본 응답:\n{raw_content}")

        result = parse_ai_json(raw_content)

        if result is None:
            logging.error("AI 응답에서 JSON을 파싱할 수 없습니다.")
            return

        logging.info("JSON 파싱 성공!")

        save_daily_summary(
            buy_stock=result.get('buy_stock'),
            buy_ticker=result.get('buy_ticker', ''),
            buy_reason=result.get('buy_reason'),
            sell_stock=result.get('sell_stock'),
            sell_ticker=result.get('sell_ticker', ''),
            sell_reason=result.get('sell_reason'),
        )

        logging.info("리포트 생성 완료!")
        logging.info(f"매수: {result['buy_stock']} ({result['buy_reason']})")
        logging.info(f"매도: {result['sell_stock']} ({result['sell_reason']})")

        send_daily_digest_alert(
            datetime.now().strftime("%Y-%m-%d"),
            result['buy_stock'], result['buy_reason'],
            result['sell_stock'], result['sell_reason']
        )

    except Exception as e:
        logging.error(f"에러 발생: {e}")


if __name__ == "__main__":
    from core.market_calendar import exit_if_outside_window
    # cron: 50 7 * * 1-5 (07:50). 휴장일·운영시간대(07~09시) 밖이면 종료.
    exit_if_outside_window(7, 9)
    generate_daily_report()
