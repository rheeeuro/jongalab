-- ============================================================
-- 국내 종목 ticker 의 '.KS' / '.KQ' 접미사 제거 → 6자리 코드만 유지
-- yfinance 의존 제거(개별 종목은 키움 REST API 로 전환)에 따른 데이터 정리.
-- 대상: ticker_dictionary, daily_stock_report, content_analysis, daily_summary
-- 멱등(idempotent): 접미사가 있는 행만 갱신하므로 재실행해도 안전.
-- ============================================================

-- 1) ticker_dictionary.ticker_symbol  (예: '005930.KS' → '005930')
UPDATE ticker_dictionary
SET ticker_symbol = SUBSTRING_INDEX(ticker_symbol, '.', 1)
WHERE ticker_symbol LIKE '%.KS' OR ticker_symbol LIKE '%.KQ';

-- 2) daily_stock_report.stock_code
UPDATE daily_stock_report
SET stock_code = SUBSTRING_INDEX(stock_code, '.', 1)
WHERE stock_code LIKE '%.KS' OR stock_code LIKE '%.KQ';

-- 3) content_analysis.related_tickers  (JSON 문자열 내 "005930.KS" → "005930")
UPDATE content_analysis
SET related_tickers = REPLACE(REPLACE(related_tickers, '.KS', ''), '.KQ', '')
WHERE related_tickers LIKE '%.KS%' OR related_tickers LIKE '%.KQ%';

-- 4) content_analysis.ticker_sectors  (related_tickers 와 1:1 대응 JSON)
UPDATE content_analysis
SET ticker_sectors = REPLACE(REPLACE(ticker_sectors, '.KS', ''), '.KQ', '')
WHERE ticker_sectors LIKE '%.KS%' OR ticker_sectors LIKE '%.KQ%';

-- 5) daily_summary.buy_ticker / sell_ticker  (국내 종목만, 해외 티커는 미변경)
UPDATE daily_summary
SET buy_ticker = SUBSTRING_INDEX(buy_ticker, '.', 1)
WHERE buy_ticker LIKE '%.KS' OR buy_ticker LIKE '%.KQ';

UPDATE daily_summary
SET sell_ticker = SUBSTRING_INDEX(sell_ticker, '.', 1)
WHERE sell_ticker LIKE '%.KS' OR sell_ticker LIKE '%.KQ';
