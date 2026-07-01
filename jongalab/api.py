"""
Stock Agent API — FastAPI 진입점
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routers.admin import router as admin_router, require_admin
from routers.contents import router as contents_router
from routers.news import router as news_router
from routers.market import router as market_router
from routers.source import router as source_router
from routers.stock_report import router as stock_report_router
from routers.strategy_config import router as strategy_config_router
from routers.weight_tuning import router as weight_tuning_router
from routers.telegram_user import router as telegram_user_router
from routers.ticker import router as ticker_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(contents_router)
app.include_router(news_router)
app.include_router(market_router)
# admin 전용 라우터 — 토큰 인증 필수(설정/소스/텔레그램 유저). 공개 페이지는 사용하지 않음.
app.include_router(source_router, dependencies=[Depends(require_admin)])
app.include_router(stock_report_router)
app.include_router(strategy_config_router, dependencies=[Depends(require_admin)])
app.include_router(weight_tuning_router, dependencies=[Depends(require_admin)])
app.include_router(telegram_user_router, dependencies=[Depends(require_admin)])
# ticker-dictionary 는 GET(목록/resolve)이 공개 sitemap 등에서 쓰이므로 라우터 단위로 막지 않고,
# 변경(PUT/DELETE)에만 ticker.py 에서 개별 require_admin 을 건다.
app.include_router(ticker_router)


@app.get("/")
def read_root():
    return {"status": "ok", "service": "Stock Agent API"}
