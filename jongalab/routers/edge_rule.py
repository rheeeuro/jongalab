"""Edge Ledger 라우트 — 가설 원장 조회(공개) + 등록·승격·강등(admin).

GET 은 대시보드 스코어보드가 쓰므로 공개, 변경(POST)만 개별 require_admin.
승격은 코드가 정량 게이트(표본·신뢰구간 하한·대조군 우위·월 승격 상한)를 강제하며,
미충족 시 409 + 사유로 거부한다(force 없음 — 사전 등록·다중 가설 보정 규율).
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from routers.admin import require_admin
from core.edge_predicate import validate_predicate, PredicateError
from core.edge_policy import ROLES, FAMILIES, rule_role, check_promotion, decision_stage
from core.repository.edge_rule import (
    create_rule,
    list_rules,
    get_rule,
    get_rule_by_name,
    set_rule_status,
    count_promoted_in_month,
    get_rule_daily,
    get_latest_matched,
    get_rule_matched_history,
    ALLOWED_EXIT_LABELS,
)

router = APIRouter(prefix="/api/edge-rules", tags=["edge-rules"])

_MONTHLY_PROMOTE_CAP = 2  # 다중 가설 보정: live 승격 월 상한(README §5·계획 §4)


class RuleCreate(BaseModel):
    name: str
    title: str  # 카드 제목(한글) — 화면에서 가설을 구분하는 이름, 필수
    family: str  # 도메인(f1_news 등) — 역할은 role 로 분리(2026-07-09)
    role: str = "selector"  # selector / veto / benchmark
    description: str
    predicate: list
    exit_label: str = "exec_leg_ret"
    min_sample: int = 40
    registered_at: str | None = None  # 미지정 시 오늘(사전 등록일)


@router.get("")
def get_edge_rules(status: str | None = Query(None)):
    """rule 목록 + stats (공개 — 스코어보드)."""
    try:
        return list_rules(status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{rule_id}/daily")
def get_edge_rule_daily(rule_id: int, days: int = Query(60, ge=1, le=365)):
    """일별 성적 시계열 (스코어보드 차트).

    daily 는 matched(일별 매칭 종목 전체 JSON)를 제외한 스칼라만 — 광역 rule 은 하루 수십
    종목이라 60일치 matched 를 다 실으면 모바일 SSR 페이로드가 수백 KB 로 자란다.
    상세 뷰가 쓰는 최신 매칭 목록은 latest_matched 로 1일치만 별도 조회한다.
    """
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule 을 찾을 수 없습니다.")
    try:
        return {
            "rule": rule,
            "daily": get_rule_daily(rule_id, days),
            "latest_matched": get_latest_matched(rule_id),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{rule_id}/matched")
def get_edge_rule_matched(rule_id: int, days: int = Query(30, ge=1, le=90)):
    """날짜별 매칭 종목 이력 (상세 페이지 '날짜별 매칭 기록').

    daily 응답이 페이로드 때문에 의도적으로 빼는 matched(일별 매칭 종목 JSON)를
    최근 days 일(매칭 있던 날만, 최신→과거)로 제한해 별도로 내려준다.
    종목별 change_pct(당일 등락률)·selected(현행 점수 톱10 여부)를 리포트에서 조인해 붙인다.
    """
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule 을 찾을 수 없습니다.")
    try:
        return get_rule_matched_history(rule_id, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", dependencies=[Depends(require_admin)])
def post_edge_rule(body: RuleCreate):
    """신규 rule 등록 (predicate·family·role·exit_label 검증 포함). 인과 근거(description) 필수."""
    if body.family not in FAMILIES:
        raise HTTPException(status_code=400, detail=f"family 는 {sorted(FAMILIES)} 중 하나여야 합니다.")
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role 은 {list(ROLES)} 중 하나여야 합니다.")
    if body.exit_label not in ALLOWED_EXIT_LABELS:
        raise HTTPException(status_code=400, detail=f"exit_label 은 {list(ALLOWED_EXIT_LABELS)} 중 하나여야 합니다.")
    if not body.description.strip():
        raise HTTPException(status_code=400, detail="description(인과 근거)은 필수입니다.")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title(카드 제목)은 필수입니다.")
    try:
        validate_predicate(body.predicate)
    except PredicateError as e:
        raise HTTPException(status_code=400, detail=f"predicate 오류: {e}")
    if get_rule_by_name(body.name):
        raise HTTPException(status_code=409, detail=f"이미 등록된 rule 이름입니다: {body.name}")
    try:
        rule_id = create_rule(
            name=body.name, title=body.title.strip(), family=body.family,
            role=body.role, description=body.description, predicate=body.predicate,
            exit_label=body.exit_label, min_sample=body.min_sample,
            registered_at=body.registered_at,
        )
        return {"ok": True, "id": rule_id, "rule": get_rule(rule_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rule_id}/promote", dependencies=[Depends(require_admin)])
def promote_edge_rule(rule_id: int):
    """candidate → live 승격. 정량 게이트 미충족 시 409(force 불가).

    게이트 판정은 core.edge_policy.check_promotion **단일 소스**(라우터·평가기·프론트 공유):
    (selector) 거래일 수 · ci_low_exc>0 · 일 클러스터 t(초과, t분포 임계값) · live 대조군
    (role=benchmark) 우위 — 대조군 부재/미평가면 fail-closed(승격 불가).
    (selector·veto) 선정 시점 실행 가능성.
    여기에 라우터만 시점 의존 운영 제약(상태=candidate, 월 승격 상한, **판정 일정**)을 더한다.
    """
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule 을 찾을 수 없습니다.")
    if rule["status"] != "candidate":
        raise HTTPException(status_code=409, detail=f"candidate 상태만 승격할 수 있습니다(현재 {rule['status']}).")

    # 판정 일정 규율(sql/39) — 확인창까지 통과한 rule 만 승격한다. 이걸 안 막으면 stats 는
    # 매일 재계산되므로, 판정에서 탈락한 rule 이 나중에 우연히 게이트를 통과하는 날 승격할 수
    # 있어 '시험 횟수 1회' 규율이 무의미해진다(오탐 2.4% → 22% 로 되돌아감).
    decision = rule.get("decision") or {}
    verdict = decision.get("verdict")
    stage = decision_stage(rule)
    if stage != "decided":
        raise HTTPException(
            status_code=409,
            detail=(f"판정 미완료(현재 단계: {stage}) — 발견 후 확인창의 새 표본으로 확증돼야 "
                    "승격할 수 있습니다. 매일 재평가로 통과를 노리는 경로를 막는 규율입니다."),
        )
    if verdict != "confirmed":
        raise HTTPException(
            status_code=409,
            detail=(f"판정 결과 '{verdict}' — 승격 불가. 사유: "
                    + " / ".join((decision.get("confirm") or {}).get("reasons")
                                 or (decision.get("discovery") or {}).get("reasons") or ["기록 없음"])),
        )

    now = datetime.now()
    if count_promoted_in_month(now.year, now.month) >= _MONTHLY_PROMOTE_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"이번 달 승격 상한({_MONTHLY_PROMOTE_CAP}개)에 도달했습니다(다중 가설 보정 규율).",
        )

    controls = [r for r in list_rules(status="live") if rule_role(r) == "benchmark"]
    gate = check_promotion(rule, controls)
    if not gate["eligible"]:
        raise HTTPException(status_code=409, detail=" / ".join(gate["stat_reasons"] + gate["exec_reasons"]))

    stats = rule.get("stats") or {}
    try:
        set_rule_status(rule_id, "live")
        # 꼬리(worst_low_ret)는 하드 손절 정책 양립 여부를 사람이 최종 판단하도록 응답에 함께 반환.
        return {
            "ok": True, "status": "live",
            "note": "승격 완료. worst_low_ret(익일 저가 꼬리)를 하드 손절 정책과 대조해 Phase 4 시드 가중을 정하세요.",
            "worst_low_ret": stats.get("worst_low_ret"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rule_id}/retire", dependencies=[Depends(require_admin)])
def retire_edge_rule(rule_id: int):
    """live/candidate → retired (성적 붕괴 또는 폐기)."""
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule 을 찾을 수 없습니다.")
    if rule["status"] == "retired":
        raise HTTPException(status_code=409, detail="이미 retired 상태입니다.")
    try:
        set_rule_status(rule_id, "retired")
        return {"ok": True, "status": "retired"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
