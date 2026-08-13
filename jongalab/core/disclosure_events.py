"""DART 공시 보고서명 → 사건 타입 분류 (룰 기반, LLM 없음).

DART 의 report_nm(보고서명)은 표준화돼 있어 정규식만으로 대부분 분류된다 —
뉴스 헤드라인처럼 LLM 을 태울 이유가 없다. LLM 은 룰이 못 잡는 잔여(기타)와
뉴스 본문 해석에만 남겨둔다(후속 단계).

[분류 축]
  event_type : 사건 종류 (유상증자·공급계약·무상증자 ...). 룰 미매칭은 '기타'.
  direction  : +1 호재 / 0 중립·미상 / -1 악재
  veto       : 악재 중에서도 **선정 제외(reduce-only)** 대상인가.
               veto 는 "익일 시초가 갭하락이 구조적으로 거의 확실한" 것만 좁게 잡는다
               — 희석(증자·CB), 존속 위험(회생·상폐·불성실공시), 계약 해지, 횡령·배임.
               소송·자사주처분 같은 약한 악재는 direction=-1 로 관측만 하고 veto 하지 않는다
               (과잉 veto 는 기회비용이고, 약한 악재의 익일 효과는 아직 미검증).

[정정공시] report_nm 앞의 [기재정정]·[첨부정정] 은 is_correction 으로 분리한다.
  원 공시는 접수일에 이미 처리됐고 정정은 며칠 뒤에도 올라오므로, 정정을 veto 로 세면
  같은 악재로 엉뚱한 날 종목이 제외된다. summarize() 가 정정을 집계에서 뺀다.

순수 함수(DB·네트워크 무의존) → tests/test_disclosure_events.py 가 계약을 고정한다.
"""
import re

# 정정공시 말머리 — [기재정정]·[첨부정정]·[첨부추가] 등
_CORRECTION_RE = re.compile(r"^\s*\[(기재정정|첨부정정|첨부추가|정정)\]")

# 당사자 아님 — 종속회사·자회사·출자법인 사건은 **접수 종목의 사건이 아니다**.
# "공시는 stock_code 로 당사자가 확정된다"는 성립하지 않는다 — 지배회사가 자회사 사건을 자기
# 코드로 접수한다('유상증자결정(종속회사의주요경영사항)', '출자법인의회생절차…' 등).
# 이런 건은 event_type 은 그대로 두되 direction·veto 를 0 으로 눕혀 관측만 한다
# (자회사 사건이 모회사 주가에 미치는 영향은 그 자체로 별도 연구 대상).
# 실수집 오탐 사례: docs/history/edge-ledger.md '분류기 오탐 함정'
_NOT_SUBJECT_RE = re.compile(r"종속회사|자회사|출자법인|관계회사|타법인")
# 발행사 말머리([000000] 등)·공백 정규화용
_BRACKET_RE = re.compile(r"\[[^\]]*\]")

# ── 분류 룰: (정규식, event_type, direction, severe) — 위에서부터 첫 매칭 승 ──
# 순서가 곧 우선순위다. '해지'가 '체결'보다 위에 있어야 공급계약 해지가 호재로 새지 않는다.
#
# [direction 과 severe 는 다른 축이다]
#   direction=-1 : 악재로 **기록**한다 → disc_bad_type 후보(연구·candidate rule 이 본다)
#   severe=1     : 그중 **live veto** 로 실매매에서 제외까지 한다
# 둘을 하나로 묶으면 veto_bad_news 와 같은 함정에 빠진다 — veto 하지 않는 타입은 라벨조차
# 안 남아서 "제외했으면 이득이었나"를 영영 측정할 수 없다. 그래서 악재는 전부 기록하고,
# 실탄(live veto)은 검증된 것만 태운다. 어떤 타입이 실제로 제외되는지의 단일 소스는
# DB edge_rule.predicate 이고, 아래 상수는 그 목록을 쓰는 쪽의 파생이다.
_RULES: tuple[tuple[re.Pattern, str, int, int], ...] = (
    # ── 사후·절차 공시 (반드시 최상단) ──
    # '증권발행결과(자율공시) (제3자배정 유상증자)'·'유상증자최종발행가액확정'·'감자완료'처럼
    # 이미 며칠 전 결정이 난 건의 후속 절차다. 새 정보가 아닌데 희석 악재로 잡으면 시장이
    # 이미 소화한 악재로 뒤늦게 제외하게 된다.
    (re.compile(r"발행결과|효력발생|청약결과|납입완료|발행가액|가액확정|증자완료|감자완료"),
     "발행절차", 0, 0),
    # 권리락도 이미 결정된 무상·유상증자의 후속 절차다. 다만 '발행절차'에 묶지 않고 event_type 을
    # 떼어 두는 이유는 이 사건이 **결과 라벨을 오염시키는 유일한 사건**이기 때문이다 — 권리락일에
    # 기준가가 배정비율만큼 낮아지는데 분봉·NXT 시세는 그 조정을 소급 반영하지 않아
    # exec_leg_ret·nxt_open_ret 이 그 비율을 그대로 손실로 찍는다(core.daily_ohlc
    # `is_price_scale_shifted` 가 가격 스케일로 걸러내고, 여기 사건은 "왜 그 날 라벨이 비었나"의
    # 추적 근거로 남는다). 위치도 중요하다: 제목이 '권리락 (무상증자)'·'권리락 (유상증자)' 라
    # 아래 무상증자(호재 +1)·유상증자 룰에 먼저 걸려 **방향이 거꾸로 붙는다**
    # (실수집 사례: docs/history/edge-ledger.md '분류기 오탐 함정').
    (re.compile(r"권리락"), "권리락", 0, 0),
    # ── 존속 위험 (veto) — 실질 위험 사유만. 거래정지 전반을 잡으면 안 된다 ──
    # 거래정지의 대다수는 액면병합·주식분할·무상증자·SPAC합병 같은 **기술적 절차**이고,
    # '거래정지해제'는 오히려 정상화 신호다(넓게 잡으면 대부분이 오탐).
    # 그래서 사유가 실제 존속 위험인 것만 남긴다 — 나머지는 아래 '시장조치'로 관측만 한다.
    (re.compile(r"상장폐지|상장적격성|실질심사"), "상장위험", -1, 1),
    # 풍문·조회공시는 **방향이 정해지지 않은 사건**이다 — '풍문또는보도에대한해명'은 회사가
    # 루머를 부인·해명하는 공시라 삼성전자·SK하이닉스·케이티 같은 대형주에도 흔히 나온다.
    # 관측만 하고 제외하지 않는다.
    # 풍문이 실제로 심각하면 거래정지·실질심사가 따라붙고, 그건 위 '상장위험'이 잡는다.
    (re.compile(r"풍문|조회공시"), "풍문해명", 0, 0),
    (re.compile(r"매매거래정지|거래정지|관리종목|투자주의환기"), "시장조치", 0, 0),
    (re.compile(r"회생절차|파산신청|기업회생"), "회생파산", -1, 1),
    (re.compile(r"횡령|배임"), "횡령배임", -1, 1),
    (re.compile(r"불성실공시법인"), "불성실공시", -1, 1),
    (re.compile(r"감사(의견|보고서).*(거절|한정|부적정)|의견거절"), "감사의견", -1, 1),
    # ── 지분 희석 (veto) — 오버나이트 갭하락의 대표 원인 ──
    # ⚠️ 유상증자는 보고서명만으로 판단하면 안 된다. 제목은 거의 항상
    # '주요사항보고서(유상증자결정)'이라 **배정방식이 드러나지 않는데**, 방식에 따라 방향이
    # 정반대다: 주주배정·일반공모=희석 악재 / 제3자배정=전략적 투자 유치로 호재일 수 있다.
    #   제3자배정이 호재로 작동한 실제 사례가 있고, 제목 기반 분류는 그날 **1순위 종목**을
    #   악재로 제외할 뻔했다(docs/history/edge-ledger.md '분류기 오탐 함정').
    # → 여기서는 '유상증자미상'(veto 아님)으로 두고, 수집기가 DART piicDecsn 로 증자방식을
    #   조회해 refine_capital_increase() 로 확정한다. 조회 실패 시 미상 그대로 = veto 안 함
    #   ("확실한 것만 veto" 원칙 — 못 가리면 개입하지 않는다).
    (re.compile(r"제3자\s*배정"), "유상증자제3자", 0, 0),
    (re.compile(r"유상증자"), "유상증자미상", 0, 0),
    # 희석 계열은 direction=-1(악재 기록)이되 **severe=0** — live veto 가 아니라 candidate 로
    # 측정한다(sql/38). 근거: 같은 '희석=악재' 통설이 유상증자에서 데이터로 뒤집혔다
    # (6거래일 유상증자 8건 전부 제3자배정 = 전략적 투자). CB·BW·EB 도 대부분 사모
    # 제3자배정이라 같은 의심이 든다. 통설만으로 실탄을 태우지 않고 표본으로 판정한다.
    (re.compile(r"전환사채권?\s*발행"), "전환사채", -1, 0),
    (re.compile(r"신주인수권부사채권?\s*발행"), "신주인수권부사채", -1, 0),
    (re.compile(r"교환사채권?\s*발행"), "교환사채", -1, 0),
    (re.compile(r"감자"), "감자", -1, 0),
    # ── 계약 해지 (veto) — '체결' 룰보다 반드시 위 ──
    (re.compile(r"(공급|판매|수주|납품).*계약.*(해지|해제|취소)"), "계약해지", -1, 1),
    # ── 약한 악재 (관측만, veto 아님) ──
    (re.compile(r"소송"), "소송", -1, 0),
    (re.compile(r"자기주식\s*처분"), "자사주처분", -1, 0),
    # ── 호재 (관측만 — 알파는 표본 축적 후 별도 rule 로 검증) ──
    (re.compile(r"단일판매|공급계약\s*체결|수주"), "공급계약", 1, 0),
    (re.compile(r"무상증자"), "무상증자", 1, 0),
    (re.compile(r"자기주식\s*(취득|신탁)"), "자사주취득", 1, 0),
    (re.compile(r"현금.?현물배당|배당결정"), "배당", 1, 0),
    (re.compile(r"신규\s*시설투자"), "시설투자", 1, 0),
    (re.compile(r"특허권\s*취득"), "특허취득", 1, 0),
    # ── 중립 — 방향이 보고서명만으로 안 나오는 것들(임상 성패, 실적 증감 등) ──
    (re.compile(r"임상시험"), "임상", 0, 0),
    # '영업(잠정)실적(공정공시)' 처럼 괄호가 리터럴로 들어오므로 정규식 그룹을 쓰지 않는다.
    (re.compile(r"영업.{0,6}실적|매출액또는손익"), "실적", 0, 0),
    (re.compile(r"최대주주\s*변경"), "최대주주변경", 0, 0),
)

OTHER = "기타"

# veto 대상 타입 — sql/37 의 veto rule predicate 와 같은 목록이어야 한다.
# rule 은 DB(edge_rule.predicate)가 단일 소스이고 이 상수는 disc_bad_type 을 **쓰는** 쪽이다.
# 둘이 어긋나도 오작동은 없고 무음이 된다(양방향 fail-safe):
#   여기에만 있는 타입 → disc_bad_type 에 써지지만 rule 이 안 잡음 = 관측만
#   rule 에만 있는 타입 → disc_bad_type 에 안 써짐 = 매칭 실패 = 미개입
# 즉 드리프트의 최악은 '제외가 안 됨'이지 '엉뚱한 종목 제외'가 아니다.
# 악재 타입 전체 — 나열 순서가 곧 disc_bad_type 선정 우선순위(심각한 것 위로)다.
# '유상증자'는 _RULES 로 도달하지 않고 refine_capital_increase(증자방식 조회)로만 확정되므로
# 파생이 아니라 명시 목록으로 둔다. tests 가 _RULES 와의 정합을 고정한다.
NEGATIVE_TYPES: tuple[str, ...] = (
    # 존속 위험 — 검증 불필요한 사실(live veto)
    "상장위험", "회생파산", "횡령배임", "불성실공시", "감사의견", "계약해지",
    # 지분 희석 — 통설이고 미검증(candidate 로 측정 중)
    "유상증자", "전환사채", "신주인수권부사채", "교환사채", "감자",
    # 약한 악재 — 관측 전용
    "소송", "자사주처분",
)

# live veto 집합 — sql/38 `veto_disclosure_severe` predicate 와 같아야 한다.
# "익일 갭하락이 거의 확실"이 통설이 아니라 사실로 성립하는 것만.
SEVERE_TYPES: tuple[str, ...] = (
    "상장위험", "회생파산", "횡령배임", "불성실공시", "감사의견", "계약해지",
)

# candidate 측정 집합 — sql/38 `veto_disclosure_dilution` predicate 와 같아야 한다.
# 실매매 미개입. rule_evaluator 가 "제외했으면 이득이었나"를 매일 채점한다.
DILUTION_TYPES: tuple[str, ...] = (
    "유상증자", "전환사채", "신주인수권부사채", "교환사채", "감자",
)


def is_correction(report_nm: str) -> bool:
    """정정공시 여부 — report_nm 앞 [기재정정]·[첨부정정] 말머리."""
    return bool(_CORRECTION_RE.match(report_nm or ""))


def is_subject(report_nm: str) -> bool:
    """접수 종목이 이 사건의 **당사자**인가 — 종속회사·출자법인 건이면 False."""
    return not _NOT_SUBJECT_RE.search(report_nm or "")


def classify(report_nm: str) -> dict:
    """보고서명 1건 분류.

    반환: {"event_type", "direction": -1|0|1, "is_veto_type": 0|1,
           "is_subject": 0|1, "is_correction": 0|1}
    룰 미매칭은 event_type='기타', direction=0, veto=0 (모르는 건 개입하지 않는다).
    당사자가 아니면(종속회사·출자법인 건) event_type 은 남기되 direction·veto 를 0 으로 눕힌다.
    """
    name = report_nm or ""
    correction = 1 if is_correction(name) else 0
    subject = 1 if is_subject(name) else 0
    # 말머리 대괄호는 제거하고 본문만 매칭 — [기재정정]유상증자결정 도 유상증자로 잡히게.
    # 단 '(종속회사의주요경영사항)' 처럼 소괄호 안 단서는 살아있어야 하므로 대괄호만 지운다.
    body = _BRACKET_RE.sub(" ", name)
    for pattern, event_type, direction, veto in _RULES:
        if pattern.search(body):
            return {
                "event_type": event_type,
                "direction": direction if subject else 0,
                "is_veto_type": veto if subject else 0,
                "is_subject": subject,
                "is_correction": correction,
            }
    return {"event_type": OTHER, "direction": 0, "is_veto_type": 0,
            "is_subject": subject, "is_correction": correction}


# 유상증자 증자방식(DART piicDecsn `ic_mthn`) → 최종 분류.
# 실제 값: "주주배정" / "주주배정후 실권주 일반공모" / "제3자배정증자" / "일반공모증자".
_THIRD_PARTY_RE = re.compile(r"제3자\s*배정")
DILUTIVE_IC = "유상증자"          # 주주배정·일반공모 — 기존 주주 희석 확정 → veto
THIRD_PARTY_IC = "유상증자제3자"   # 전략적 투자 유치일 수 있음 → 관측만
UNKNOWN_IC = "유상증자미상"        # 방식 조회 실패 → 개입하지 않음


def refine_capital_increase(base: dict, ic_mthn: str | None) -> dict:
    """'유상증자미상' 분류를 증자방식으로 확정. 수집기가 piicDecsn 조회 후 호출한다.

    base: classify() 결과. ic_mthn: DART 증자방식 문자열(없으면 None).
    반환: event_type·direction·is_veto_type 만 갱신한 새 dict(원본 불변).

      주주배정·일반공모 → '유상증자'      direction -1, severe 0  (희석 기록, live veto 는 아님)
      제3자배정          → '유상증자제3자'  direction  0, severe 0  (방향 갈림 — 관측)
      조회 실패/미상     → '유상증자미상'    direction  0, severe 0  (못 가리면 개입 안 함)

    유상증자 계열이 아닌 사건은 그대로 돌려준다(호출부 분기 최소화).
    """
    if base.get("event_type") != UNKNOWN_IC:
        return base
    if not ic_mthn:
        return base
    if _THIRD_PARTY_RE.search(ic_mthn):
        return {**base, "event_type": THIRD_PARTY_IC, "direction": 0, "is_veto_type": 0}
    subject = base.get("is_subject", 1)
    return {**base, "event_type": DILUTIVE_IC, "direction": -1 if subject else 0}


def summarize(events: list[dict]) -> dict:
    """한 종목의 당일 사건 목록 → daily_stock_report 공시 라벨.

    events: stock_event 행 dict 목록([{event_type, direction, is_veto_type, is_subject,
                                       is_correction}, ...]). 비당사자 건은 classify 단계에서
    이미 direction·veto 가 0 으로 눕혀져 있어 여기서 따로 거를 필요가 없다.
    반환: {"disc_count": int, "disc_bad_type": str|None, "disc_good_type": str|None}

      disc_count     — 정정 포함 전체 건수(관측·연구용)
      disc_bad_type  — 정정 제외 **악재 전체**(direction=-1) 중 NEGATIVE_TYPES 우선순위
                       최상위(없으면 None). live veto·candidate rule 이 각자 필요한
                       타입만 predicate 의 in 목록으로 골라 쓴다.
      disc_good_type — 정정 제외 호재 중 첫 등장 타입(없으면 None). 관측 전용.
    """
    if not events:
        return {"disc_count": 0, "disc_bad_type": None, "disc_good_type": None}

    live = [e for e in events if not e.get("is_correction")]
    # disc_bad_type 은 **악재 전체**(direction=-1)에서 고른다 — live veto 대상만 쓰면
    # 검증 중인 candidate rule(희석 계열)이 매칭할 라벨이 없어 표본이 영영 안 쌓인다.
    bad = {e.get("event_type") for e in live if (e.get("direction") or 0) < 0}
    bad_type = next((t for t in NEGATIVE_TYPES if t in bad), None)
    good_type = next(
        (e.get("event_type") for e in live if (e.get("direction") or 0) > 0), None
    )
    return {
        "disc_count": len(events),
        "disc_bad_type": bad_type,
        "disc_good_type": good_type,
    }
