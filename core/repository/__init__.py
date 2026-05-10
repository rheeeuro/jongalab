"""
repository 패키지 — 기존 import 호환을 위한 재-export

사용법 (기존과 동일):
    from core.repository import get_contents_paginated, save_content_analysis
"""

from core.repository.content import (
    get_contents_paginated,
    get_contents_by_ticker,
    is_content_processed,
    save_content_analysis,
    get_recent_analyses,
    get_today_content_by_stock,
    get_content_by_stock_and_date,
    get_mention_stats,
)

from core.repository.daily_summary import (
    save_daily_summary,
    get_latest_daily_summary,
    get_daily_summary_by_date,
    get_daily_summary_list,
)

from core.repository.source import (
    get_active_sources,
    get_youtube_sources,
    get_sources,
    source_exists,
    create_source,
    update_source,
    delete_source,
)

from core.repository.stock_report import (
    save_stock_reports,
    get_stock_report,
    get_stock_report_history,
    get_stock_reports_by_date,
    get_stock_report_dates,
)

from core.repository.sector_report import (
    save_sector_reports,
    get_sector_reports_by_date,
    get_sector_report_dates,
)

from core.repository.strategy_config import (
    get_strategy_config,
    update_strategy_config,
)

from core.repository.telegram_user import (
    get_telegram_users,
    get_active_chat_ids,
    telegram_user_exists,
    create_telegram_user,
    update_telegram_user,
    delete_telegram_user,
    VALID_ROLES,
)

from core.repository.ticker import (
    lookup_ticker,
    lookup_name_by_ticker,
    save_ticker,
    get_ticker_dictionary,
    update_ticker,
    delete_ticker,
)

from core.repository.kiwoom_token import (
    get_token as get_kiwoom_token,
    save_token as save_kiwoom_token,
    clear_token as clear_kiwoom_token,
)
