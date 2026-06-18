"""티커 사전 관리 라우트"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
import mysql.connector

from core.repository import get_ticker_dictionary, update_ticker, delete_ticker
from core.sector_resolver import fetch_sector_from_api
from routers.admin import require_admin

router = APIRouter(prefix="/api/ticker-dictionary", tags=["ticker-dictionary"])


class TickerDictionaryUpdate(BaseModel):
    company_name: str
    ticker_symbol: str
    status: str
    sector: Optional[str] = None


@router.get("")
def get_ticker_dict(
    status: Optional[str] = Query(None, description="상태 필터 (PENDING, ACTIVE, INACTIVE)"),
):
    """ticker dictionary 목록 조회"""
    try:
        return get_ticker_dictionary(status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolve-sector")
def resolve_sector(
    ticker: str = Query(..., description="티커 심볼"),
):
    """키움 ka10100에서 섹터를 즉시 조회 (국장 전용).
    DB에는 저장하지 않으며, 호출자가 PUT으로 저장 시 함께 캐시됨.
    """
    try:
        sector = fetch_sector_from_api(ticker)
        return {"success": True, "sector": sector}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{ticker_id}", dependencies=[Depends(require_admin)])
def update_ticker_dict(ticker_id: int, body: TickerDictionaryUpdate):
    """ticker dictionary 항목 수정"""
    if body.status not in ("PENDING", "ACTIVE", "INACTIVE"):
        raise HTTPException(status_code=400, detail="status는 PENDING, ACTIVE, INACTIVE 중 하나여야 합니다.")
    try:
        success = update_ticker(
            ticker_id, body.company_name, body.ticker_symbol,
            body.status, body.sector,
        )
    except mysql.connector.IntegrityError as e:
        if e.errno == 1062:
            raise HTTPException(status_code=409, detail=f"이미 등록된 기업명입니다: {body.company_name}")
        raise HTTPException(status_code=400, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail="해당 항목을 찾을 수 없습니다.")
    return {"success": True}


@router.delete("/{ticker_id}", dependencies=[Depends(require_admin)])
def delete_ticker_dict(ticker_id: int):
    """ticker dictionary 항목 삭제"""
    success = delete_ticker(ticker_id)
    if not success:
        raise HTTPException(status_code=404, detail="해당 항목을 찾을 수 없습니다.")
    return {"success": True}
