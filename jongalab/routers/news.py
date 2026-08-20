"""뉴스 라우트 — 재료 집계(news_mention) + 재료 지속성 라벨 + 헤드라인 스트림(sec_news).

두 계층이 한 라우터에 있다. `/heat`·`/materials`·`/{ticker}` 는 **집계 계층**(news_mention,
소스 게이트 `_source_filter(kind)` 적용 — heat 은 건수라 count, 종목별 헤드라인은 text)이고, `/stream` 만 **표시 계층**(sec_news)이다 —
왜 나눴는지는 sql/49 주석. 새 엔드포인트를 붙일 땐 어느 쪽인지 먼저 정할 것.
"""
from datetime import datetime

from fastapi import APIRouter, Query

from core.news_material_judge import is_price_report
from core.repository import count_news_by_stock, get_news_heat, get_sec_news_day, get_today_news_by_stock
from core.repository.stock_report import get_news_material_rows

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/heat")
def get_news_heat_ranking(
    hours: int = Query(24, ge=1, le=168, description="집계 윈도우 (시간, date 미지정 시)"),
    limit: int = Query(20, ge=1, le=100, description="상위 종목 수"),
    date: str | None = Query(None, description="특정 날짜 하루 집계 YYYY-MM-DD (뉴스 탭)"),
    min_count: int = Query(1, ge=1, le=100, description="이 건수 미만 종목 제외 (노이즈 하한)"),
    min_surprise: float = Query(0.0, ge=0, le=100, description="이 배수 미만 종목 제외"),
    sort: str = Query("surprise", pattern="^(surprise|count)$", description="정렬축"),
):
    """뉴스가 몰린 종목 순위 — 기본은 **자기 기저 대비 배수(surprise) 정렬**.

    건수 정렬은 그것만 쓰면 시총 랭킹이 되어(대형주 상단 고정) 카드가 정보를 주지 못한다.
    그래서 `sort=count` 는 **`min_surprise` 와 함께** 쓰는 조합을 전제로 한다 —
    "평소보다 늘어난 종목만 남기고, 그 안에서 건수 순"(뉴스 탭 사이드 랭킹). 상세는
    core.repository.news.get_news_heat 주석 참조. 유니버스 종목이면 재료 라벨도 함께 온다.
    `date` 를 주면 그 날짜 하루 집계(뉴스 탭 날짜 이동), 없으면 최근 `hours` 시간(홈 카드).
    """
    try:
        return {
            "success": True,
            "data": get_news_heat(
                hours=hours,
                limit=limit,
                date=date,
                min_count=min_count,
                min_surprise=min_surprise,
                sort=sort,
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/stream")
def get_news_headline_stream(
    date: str | None = Query(None, description="날짜 YYYY-MM-DD (기본: 오늘)"),
    limit: int = Query(40, ge=1, le=100, description="한 페이지 기사 수"),
    offset: int = Query(0, ge=0, description="건너뛸 기사 수 (더 보기)"),
    q: str | None = Query(None, max_length=50, description="제목 검색어"),
    ticker: str | None = Query(None, max_length=20, description="이 종목 칩이 붙은 기사만"),
    hide_price: bool = Query(True, description="시세 기사 제외 (화면 기본값과 같다)"),
):
    """그 날 **증권 섹션 기사**를 최신순 반환 (뉴스 탭 헤드라인 스트림).

    소스는 `sec_news`(네이버 증권 섹션 목록)다. 2026-08-05 이전엔 news_mention(텔레그램
    종합 속보 채널)을 읽었는데, 그 채널은 주식 전용이 아니라 저장 여부가 사명 매칭 하나로만
    갈렸다 — 실측 14일 5,674기사 중 4.1%가 `70대 남성 사망`(남성 004270)·`한화, 삼성 4-1
    제압`(한화 000880) 류의 오탐이었다. 모집단이 원인이라 모집단을 바꿨다(sql/49).
    집계(`/heat`·`/materials`·`/{ticker}`)는 그대로 news_mention 을 읽는다 — 이 교체는
    화면만 건드리고 라벨·rule·veto 표본에는 닿지 않는다.

    각 기사에 `is_price_report`("급등/상한가/특징주" 류인가)를 실어 화면이 시세 기사를
    구분할 수 있게 하고, **제외 자체는 여기서 한다**(`hide_price`, 기본 True). 화면이
    받은 페이지에서 걸러내면 총계(그 날 전체)·'더 보기' 카운터·실제 표시 건수가 서로 다른
    수가 되기 때문이다. `total` 은 **지금 조건으로 나열되는 기사 수**이고, 숨긴 시세 기사
    수는 `price_total` 로 따로 준다. 판별은 후속 재료 채점과 **같은 함수**.

    `q`(제목 검색)·`ticker`(종목 칩) 필터도 총계에 함께 반영된다 — 하루 545건을 '더 보기'로만
    훑는 것 외에 방법이 없던 문제(2026-08-20 점검)를 여기서 받는다.
    """
    try:
        report_date = date or datetime.now().strftime("%Y-%m-%d")
        rows = get_sec_news_day(report_date, q=q, ticker=ticker)
        for it in rows:
            it["is_price_report"] = is_price_report(it.get("headline") or "")
        price_total = sum(1 for it in rows if it["is_price_report"])
        listed = [it for it in rows if not it["is_price_report"]] if hide_price else rows
        total = len(listed)
        page = listed[offset:offset + limit]
        return {
            "success": True,
            "data": page,
            "total": total,
            "price_total": price_total,
            "has_more": offset + len(page) < total,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/materials")
def get_news_materials(
    date: str | None = Query(None, description="리포트 날짜 YYYY-MM-DD (기본: 오늘)"),
):
    """그 날 뉴스가 있던 유니버스 종목의 재료 라벨 목록 (뉴스 화면용).

    비선정 후보도 포함한다 — 뉴스 화면의 축은 '오늘 뜬 재료'이고 매매 선정 여부와 다르다.
    라벨은 candidate rule 표본(관찰 전용)이므로 화면은 '미검증' 톤으로 노출해야 한다.
    """
    try:
        report_date = date or datetime.now().strftime("%Y-%m-%d")
        return {"success": True, "data": get_news_material_rows(report_date)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# 주의: "/heat"·"/materials" 보다 뒤에 등록해야 한다 (FastAPI 는 등록 순서대로 매칭).
@router.get("/{ticker}")
def get_today_news(
    ticker: str,
    limit: int = Query(15, ge=1, le=50, description="최대 헤드라인 수"),
    days: int = Query(1, ge=1, le=7, description="집계 윈도우 (일, 1=오늘)"),
):
    """특정 종목의 뉴스 헤드라인 목록 (최신순, 종목 상세 페이지용).

    각 항목에 `is_price_report`(그날 시세를 옮긴 기사인가)를 실어 화면이 재료 기사를 먼저
    보여주고 시세 기사는 접을 수 있게 한다 — 실측 21%가 "급등/상한가/특징주" 류라 재료가 묻힌다.
    판별 규칙은 후속 재료 채점과 **같은 함수**를 쓴다(화면과 채점의 기준이 갈리면 안 된다).
    """
    try:
        items = get_today_news_by_stock(ticker, limit=limit, days=days)
        for it in items:
            it["is_price_report"] = is_price_report(it.get("headline") or "")
        # total 은 limit 이전 총건수 — 화면이 "15건"을 총계처럼 내지 않게 한다.
        return {
            "success": True,
            "data": items,
            "total": count_news_by_stock(ticker, days=days),
            "days": days,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
