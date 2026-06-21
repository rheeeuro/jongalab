"""가중치 튜닝 제안 라우트 (admin 전용).

주간 워커(weight_tuner)가 만든 제안을 조회하고, 승인 시 제안 가중치를 strategy_config 에 반영한다.
승인/반려는 사람이 수행하며, 승인해야만 실제 종합점수 가중치가 바뀐다.
"""
from fastapi import APIRouter, HTTPException

from core.repository import (
    get_strategy_config,
    update_strategy_config,
    get_latest_proposal,
    get_proposal,
    list_proposals,
    mark_applied,
    mark_rejected,
    SCORE_WEIGHT_KEYS,
)

router = APIRouter(prefix="/api/weight-tuning", tags=["weight-tuning"])


@router.get("/proposals")
def get_proposals(limit: int = 20):
    """제안 목록 (최신순)."""
    try:
        return list_proposals(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proposals/latest")
def get_latest():
    """가장 최근 제안 1건."""
    try:
        return get_latest_proposal() or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: int):
    """제안 승인 — 제안 가중치를 현재 전략 설정에 덮어쓰고 적용 처리."""
    proposal = get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="제안을 찾을 수 없습니다.")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"이미 처리된 제안입니다(status={proposal['status']}).")
    try:
        config = get_strategy_config()
        proposed = proposal.get("proposed_weights") or {}
        # 종합점수 구성 가중치만 덮어쓴다(다른 전략 파라미터는 보존).
        for k in SCORE_WEIGHT_KEYS:
            if k in proposed:
                config[k] = proposed[k]
        update_strategy_config(config)
        mark_applied(proposal_id)
        return {"ok": True, "applied_weights": {k: config[k] for k in SCORE_WEIGHT_KEYS}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: int):
    """제안 반려 — 가중치는 그대로 두고 상태만 rejected 로."""
    proposal = get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="제안을 찾을 수 없습니다.")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"이미 처리된 제안입니다(status={proposal['status']}).")
    try:
        mark_rejected(proposal_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
