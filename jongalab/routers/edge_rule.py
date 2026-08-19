"""Edge Ledger 라우트 — 가설 원장 조회(공개) + 등록·상태 전이(admin).

GET 은 대시보드 스코어보드가 쓰므로 공개, 변경(POST)만 개별 require_admin.

상태 축이 **둘**이다(섞으면 안 된다):
  · 원장(사람) — `candidate → live`(승격) / `→ retired`(종결) / `retired → candidate`(복귀).
    승격은 코드가 정량 게이트(평균수익·거래일 수·신뢰구간 하한)를 강제하며 미충족 시 409 +
    사유로 거부한다(force 없음 — 사전 등록 규율). **게이트를 통과하면 그대로 승격한다** —
    통과 건수를 사람이 다시 줄이는 장치는 두지 않는다(아래 promote_edge_rule 주석).
    복귀는 `registered_at` 을 밀어 **표본을 리셋**한다(같은 표본 재시험 금지).
  · 운용(자동) — `live ↔ paused`. 되돌릴 수 있는 온오프라 `workers/rule_evaluator` 가 승인
    없이 굴린다. 여기 두는 pause/resume 은 **사람이 끼어들 때만** 쓰는 수동 경로이고,
    다음 평가에서 자동 판정이 다시 덮어쓸 수 있다.
"""
from datetime import date

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from routers.admin import require_admin
from core.edge_predicate import validate_predicate, PredicateError
from core.config import EDGE_PROMO_POLICY
from core.edge_policy import ROLES, FAMILIES, rule_role, check_promotion, decision_stage
from core.repository.edge_rule import (
    create_rule,
    list_rules,
    get_rule,
    get_rule_by_name,
    set_rule_status,
    reset_for_unretire,
    get_rule_daily,
    get_latest_matched,
    get_rule_matched_history,
    ALLOWED_EXIT_LABELS,
)

router = APIRouter(prefix="/api/edge-rules", tags=["edge-rules"])

# ── 월 승격 상한은 **없다** ──
# 규율은 하나다: **게이트를 통과하면 승격한다.** 승격 건수를 사람이 줄이는 장치를 두면 통과 룰
# 사이에 순위를 매기게 되고, 그 순간 사후 재계산으로 통과 룰을 떨어뜨리는 일이 생긴다
# — 게이트를 자동화한 이유와 정면으로 충돌한다. 실탄 유량은 선정 슬롯(`TRADED_TOP_N=10`)이
# 이미 묶고 있어, live selector 를 늘려도 사는 종목 수·시드는 늘지 않고 구성만 바뀐다.
# 과적합 방어는 게이트 자신(ci_low>0 · 거래일≥10 · 평균수익>0)과 강등 감시
# (edge_policy.check_demotion)가 진다. 폐지 근거·반사실 실측: docs/history/edge-ledger.md
# ⚠️ 대신 드러난 숙제: 매칭이 슬롯을 넘을 때 hybrid 는 **점수순**으로 자르는데 그 점수는 엣지가
# 없다. rule 기대값(mean_net) 순으로 자르는 `rules` 모드 정렬을 hybrid 초과분에도 쓸지는 별건.


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
    (selector) 평균수익>0 · 거래일 수 · ci_low>0 · 일 클러스터 t(t분포 임계값).
    2026-08-04: 초과수익·대조군 우위 조건은 제거됐다(자는 절대 평균수익 하나).
    (selector·veto) 선정/집행 시점 실행 가능성.
    여기에 라우터만 시점 의존 운영 제약(상태=candidate, **판정 일정**)을 더한다.
    월 승격 상한은 2026-08-05 폐지했다(파일 상단 주석) — 통과 건수는 더 이상 제한하지 않는다.
    """
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule 을 찾을 수 없습니다.")
    if rule["status"] != "candidate":
        raise HTTPException(status_code=409, detail=f"candidate 상태만 승격할 수 있습니다(현재 {rule['status']}).")

    # 판정 일정 규율(sql/39) — 확인창까지 통과한 rule 만 승격한다. 이걸 안 막으면 stats 는
    # 매일 재계산되므로, 판정에서 탈락한 rule 이 나중에 우연히 게이트를 통과하는 날 승격할 수
    # 있어 '시험 횟수 1회' 규율이 무의미해진다(오탐 2.4% → 22% 로 되돌아감).
    # **experimental 정책에서는 면제** — 그 정책의 취지가 "확신을 기다리지 않고 올려보고 강등"
    # 이므로 판정 일정을 강제하면 앞뒤가 맞지 않는다(config.EDGE_PROMO_POLICY 주석 참조).
    if EDGE_PROMO_POLICY != "experimental":
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

    controls = [r for r in list_rules(status="live") if rule_role(r) == "benchmark"]
    gate = check_promotion(rule, controls, policy=EDGE_PROMO_POLICY)
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


@router.post("/{rule_id}/pause", dependencies=[Depends(require_admin)])
def pause_edge_rule(rule_id: int):
    """live → paused (수동). 선정에서 표를 빼되 채점은 계속하고, 되돌릴 수 있다.

    평소엔 `workers/rule_evaluator` 가 자동으로 굴린다 — 이 경로는 사람이 먼저 끼어들 때만
    쓰고, 다음 평가에서 자동 판정이 다시 덮어쓸 수 있다(영구 배제는 retire 다).
    """
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule 을 찾을 수 없습니다.")
    if rule["status"] != "live":
        raise HTTPException(
            status_code=409, detail=f"live 상태만 일시중지할 수 있습니다(현재 {rule['status']}).")
    try:
        set_rule_status(rule_id, "paused")
        return {"ok": True, "status": "paused",
                "note": "선정에서 즉시 빠집니다. 채점은 계속되며 성적이 회복되면 자동 복귀합니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rule_id}/resume", dependencies=[Depends(require_admin)])
def resume_edge_rule(rule_id: int):
    """paused → live (수동 복귀). 승격이 아니므로 게이트를 다시 보지 않는다."""
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule 을 찾을 수 없습니다.")
    if rule["status"] != "paused":
        raise HTTPException(
            status_code=409, detail=f"paused 상태만 복귀할 수 있습니다(현재 {rule['status']}).")
    try:
        set_rule_status(rule_id, "live")
        return {"ok": True, "status": "live",
                "note": "선정에 다시 참여합니다. 최근 성적이 나쁘면 다음 평가에서 자동으로 다시 내려갈 수 있습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rule_id}/unretire", dependencies=[Depends(require_admin)])
def unretire_edge_rule(rule_id: int):
    """retired → candidate 복귀 + **표본 리셋**.

    `registered_at` 을 오늘로 밀어 발견창부터 새 표본으로 다시 판정한다. 과거 표본을 이어붙여
    게이트를 다시 보면 같은 표본으로 재시험하는 꼴(optional stopping)이라 오탐률이 판정 일정
    도입 전으로 되돌아간다. 과거 채점은 `edge_rule_daily` 에 남아 참고할 수 있다.
    """
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule 을 찾을 수 없습니다.")
    if rule["status"] != "retired":
        raise HTTPException(
            status_code=409, detail=f"retired 상태만 복귀할 수 있습니다(현재 {rule['status']}).")
    today = str(date.today())
    try:
        reset_for_unretire(rule_id, today)
        return {"ok": True, "status": "candidate", "registered_at": today,
                "note": ("표본을 리셋했습니다 — 오늘부터의 새 표본으로 발견창부터 다시 판정합니다. "
                         "과거 채점 기록은 상세 화면에 남아 있습니다.")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rule_id}/retire", dependencies=[Depends(require_admin)])
def retire_edge_rule(rule_id: int):
    """live/paused/candidate → retired (가설 폐기·판정 종결). 원장 축이라 사람만 결정한다."""
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
