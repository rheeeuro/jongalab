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
    save_gap_check_results,
    get_gap_stats_by_dates,
    get_top_picks_by_dates,
)

from core.repository.sector_report import (
    save_sector_reports,
    get_sector_reports_by_date,
    get_sector_report_dates,
    get_top_themes_by_dates,
)

from core.repository.strategy_config import (
    get_strategy_config,
    update_strategy_config,
    SCORE_WEIGHT_KEYS,
)

from core.repository.trade_result import (
    get_weekly_trade_results,
)

from core.repository.weight_tuning import (
    save_proposal,
    get_proposal,
    get_latest_proposal,
    list_proposals,
    mark_applied,
    mark_rejected,
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

# 키움 토큰 저장은 별도 kiwoom 데이터 서버가 소유한다(kiwoom/core/repository/kiwoom_token.py).
# jongalab 은 토큰을 직접 다루지 않으므로 여기서 re-export 하지 않는다.
