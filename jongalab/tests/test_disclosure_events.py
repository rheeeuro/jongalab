"""공시 사건 분류·요약 계약 고정 (순수 로직, DB·네트워크 무의존).

veto_disclosure_bad 는 live rule 이라 여기서 잘못 분류되면 실매매 선정이 바로 틀어진다
(과잉 veto = 기회 상실 / 미탐 = 희석 공시를 안고 오버나이트). 실제 DART report_nm 표기를
표본으로 고정한다.
"""
import pytest

from core.disclosure_events import (
    DILUTION_TYPES, DILUTIVE_IC, NEGATIVE_TYPES, SEVERE_TYPES, THIRD_PARTY_IC,
    UNKNOWN_IC, _RULES, classify, is_correction, refine_capital_increase, summarize,
)


# (report_nm, 기대 event_type, 기대 direction, 기대 veto)
_CASES = [
    # ── 사후·절차 공시: 새 정보가 아니므로 veto 하지 않는다 (2026-07-28 실수집 오탐 회귀) ──
    ("증권발행결과(자율공시)              (제3자배정 유상증자)", "발행절차", 0, 0),
    ("증권발행결과(자율공시)(유상증자)", "발행절차", 0, 0),
    ("효력발생안내( 2026.7.15. 제출 증권신고서(채무증권) )", "발행절차", 0, 0),
    ("유상증자최종발행가액확정", "발행절차", 0, 0),
    ("유상증자신주발행가액(안내공시)", "발행절차", 0, 0),
    ("감자완료", "발행절차", 0, 0),
    # 권리락은 방향 없는 기계적 절차다 — 아래 무상증자(호재)·유상증자 룰보다 먼저 잡혀야 한다
    # (2026-08-04 알테오젠 회귀: 권리락 공시가 direction=+1 호재로 저장됐다).
    ("권리락              (무상증자)", "권리락", 0, 0),
    ("권리락              (유상증자)", "권리락", 0, 0),
    ("권리락(주식배당)", "권리락", 0, 0),
    # ── 희석 (veto) ──
    # 유상증자는 제목에 배정방식이 없어 '미상'으로 두고 piicDecsn 조회로 확정한다
    # (2026-07-27 NAVER→NVIDIA 제3자배정을 악재로 오분류한 회귀).
    ("유상증자결정", "유상증자미상", 0, 0),
    ("주요사항보고서(유상증자결정)", "유상증자미상", 0, 0),
    # 제목에 배정방식이 드러난 드문 경우는 조회 없이 바로 갈린다
    ("제3자배정 유상증자 결정", "유상증자제3자", 0, 0),
    ("전환사채권발행결정", "전환사채", -1, 0),
    ("신주인수권부사채권발행결정", "신주인수권부사채", -1, 0),
    ("교환사채권발행결정", "교환사채", -1, 0),
    ("감자결정", "감자", -1, 0),
    # ── 존속 위험 (veto) ──
    ("불성실공시법인지정예고", "불성실공시", -1, 1),
    ("불성실공시법인지정예고              (공시불이행 3건)", "불성실공시", -1, 1),
    ("횡령ㆍ배임혐의발생", "횡령배임", -1, 1),
    ("회생절차개시신청", "회생파산", -1, 1),
    ("주요사항보고서(회생절차개시신청)", "회생파산", -1, 1),
    ("파산신청", "회생파산", -1, 1),
    ("상장폐지사유발생", "상장위험", -1, 1),
    ("감사보고서제출(감사의견 거절)", "감사의견", -1, 1),
    ("감사의견거절", "감사의견", -1, 1),
    # 거래정지라도 사유가 실질 위험이면 veto (2026-07-28 감사 회귀)
    ("주권매매거래정지기간변경              (상장폐지 사유 발생)", "상장위험", -1, 1),
    ("주권매매거래정지기간변경              (상장적격성 실질심사 대상(사유발생))", "상장위험", -1, 1),
    ("기타시장안내              (상장폐지 관련 이의신청서 접수)", "상장위험", -1, 1),
    ("상장적격성실질심사관련주요개선계획(자율공시)", "상장위험", -1, 1),
    # ── 풍문·조회공시: 방향 미정이라 관측만 (대형주 해명 공시 오탐 회귀) ──
    ("풍문또는보도에대한해명", "풍문해명", 0, 0),
    ("풍문또는보도에대한해명(미확정)", "풍문해명", 0, 0),
    ("조회공시요구(풍문또는보도)에대한답변(미확정)", "풍문해명", 0, 0),
    ("주권매매거래정지              (풍문 또는 보도 관련)", "풍문해명", 0, 0),
    # ── 시장조치: 절차성 거래정지·해제·관리종목 안내는 veto 아님 (오탐 회귀) ──
    ("주권매매거래정지해제              (액면병합 주권 변경상장)", "시장조치", 0, 0),
    ("주권매매거래정지해제              (감자 주권 변경상장)", "시장조치", 0, 0),
    ("주권매매거래정지              (주식의 병합, 분할 등 전자등록 변경, 말소)", "시장조치", 0, 0),
    ("주권매매거래정지              (주식분할)", "시장조치", 0, 0),
    ("주권매매거래정지              (무상증자)", "시장조치", 0, 0),
    ("주권매매거래정지              (SPAC 합병(예비심사청구대상))", "시장조치", 0, 0),
    ("주권매매거래정지              (영업양수도)", "시장조치", 0, 0),
    ("주권매매거래정지기간변경              (개선기간 부여)", "시장조치", 0, 0),
    ("매매거래정지및정지해제(중요내용공시)", "시장조치", 0, 0),
    ("기타시장안내(관리종목지정우려종목)              (시가총액 200억원 미달)", "시장조치", 0, 0),
    # ── 계약 해지 (veto) — '체결' 룰보다 먼저 잡혀야 한다 ──
    ("단일판매ㆍ공급계약해지", "계약해지", -1, 1),
    ("단일판매ㆍ공급계약체결의 해제", "계약해지", -1, 1),
    # ── 약한 악재: 기록만, veto 아님 ──
    ("소송등의제기", "소송", -1, 0),
    ("자기주식처분결정", "자사주처분", -1, 0),
    # ── 호재: 관측 전용 ──
    ("단일판매ㆍ공급계약체결", "공급계약", 1, 0),
    ("무상증자결정", "무상증자", 1, 0),
    ("자기주식취득결정", "자사주취득", 1, 0),
    ("자기주식취득신탁계약체결결정", "자사주취득", 1, 0),
    ("현금ㆍ현물배당결정", "배당", 1, 0),
    ("신규시설투자등", "시설투자", 1, 0),
    ("특허권취득결정", "특허취득", 1, 0),
    # ── 중립 ──
    ("임상시험계획승인신청", "임상", 0, 0),
    ("최대주주변경", "최대주주변경", 0, 0),
    ("영업(잠정)실적(공정공시)", "실적", 0, 0),
    # ── 미분류: 모르는 건 개입하지 않는다 ──
    ("분기보고서(2026.06)", "기타", 0, 0),
    ("기업설명회(IR)개최(안내공시)", "기타", 0, 0),
    ("임원ㆍ주요주주특정증권등소유상황보고서", "기타", 0, 0),
]


@pytest.mark.parametrize("report_nm,event_type,direction,veto", _CASES)
def test_classify(report_nm, event_type, direction, veto):
    got = classify(report_nm)
    assert got["event_type"] == event_type
    assert got["direction"] == direction
    assert got["is_veto_type"] == veto


def test_severe_types_match_rules():
    """SEVERE_TYPES(live veto) 와 _RULES(severe=1) 가 어긋나지 않아야 한다."""
    assert set(SEVERE_TYPES) == {t for _, t, _, severe in _RULES if severe}


def test_severe_and_dilution_are_disjoint_subsets_of_negative():
    """live(확실) 와 candidate(측정) 집합은 겹치지 않고, 둘 다 악재 목록 안에 있어야 한다."""
    assert not set(SEVERE_TYPES) & set(DILUTION_TYPES)
    assert set(SEVERE_TYPES) <= set(NEGATIVE_TYPES)
    assert set(DILUTION_TYPES) <= set(NEGATIVE_TYPES)


def test_negative_types_cover_every_negative_rule():
    """direction=-1 인 룰이 NEGATIVE_TYPES 에 빠지면 disc_bad_type 에 안 실려 측정 불가."""
    from_rules = {t for _, t, d, _ in _RULES if d < 0}
    assert from_rules <= set(NEGATIVE_TYPES)
    assert DILUTIVE_IC in NEGATIVE_TYPES   # refine 으로만 생기는 타입


def test_negative_types_are_all_negative():
    """악재 목록에 호재·중립이 섞이면 안 된다(선정에서 좋은 종목을 지운다)."""
    for name in NEGATIVE_TYPES:
        if name == DILUTIVE_IC:
            continue  # refine 테스트가 담당
        matched = [c for c in _CASES if c[1] == name]
        assert matched, f"{name} 에 대한 회귀 표본이 없습니다"
        assert all(c[2] == -1 for c in matched)


def test_dilution_is_recorded_but_not_live_vetoed():
    """희석 계열은 악재로 기록(disc_bad_type)되되 live veto 집합에는 없어야 한다.

    기록이 없으면 candidate rule 이 매칭할 라벨이 없어 표본이 영영 안 쌓인다
    (veto_bad_news 가 n=0 에 갇힌 실패의 회귀 방지).
    """
    got = summarize([classify("전환사채권발행결정")])
    assert got["disc_bad_type"] == "전환사채"
    assert "전환사채" not in SEVERE_TYPES


# ── 유상증자 증자방식 확정 (2026-07-27 NAVER→NVIDIA 회귀) ──

@pytest.mark.parametrize("ic_mthn", ["제3자배정증자", "제3자 배정 증자"])
def test_refine_third_party_is_not_vetoed(ic_mthn):
    got = refine_capital_increase(classify("주요사항보고서(유상증자결정)"), ic_mthn)
    assert got["event_type"] == THIRD_PARTY_IC
    assert got["is_veto_type"] == 0
    assert got["direction"] == 0
    assert summarize([got])["disc_bad_type"] is None


@pytest.mark.parametrize("ic_mthn", ["주주배정", "주주배정후 실권주 일반공모", "일반공모증자"])
def test_refine_dilutive_is_recorded_not_live_vetoed(ic_mthn):
    got = refine_capital_increase(classify("주요사항보고서(유상증자결정)"), ic_mthn)
    assert got["event_type"] == DILUTIVE_IC
    assert got["direction"] == -1                 # 악재로 기록하고
    assert got["is_veto_type"] == 0               # live veto 는 아니다(candidate 측정)
    assert summarize([got])["disc_bad_type"] == DILUTIVE_IC


@pytest.mark.parametrize("ic_mthn", [None, ""])
def test_refine_unknown_does_not_veto(ic_mthn):
    """방식을 못 가리면 개입하지 않는다 — '확실한 것만 veto' 원칙."""
    got = refine_capital_increase(classify("주요사항보고서(유상증자결정)"), ic_mthn)
    assert got["event_type"] == UNKNOWN_IC
    assert got["is_veto_type"] == 0
    assert summarize([got])["disc_bad_type"] is None


def test_refine_keeps_not_subject_zeroed():
    """종속회사 유상증자는 방식이 희석형이어도 모회사를 제외하지 않는다."""
    got = refine_capital_increase(
        classify("유상증자결정(종속회사의주요경영사항)"), "주주배정")
    assert got["is_subject"] == 0
    assert got["direction"] == 0
    assert summarize([got])["disc_bad_type"] is None


def test_refine_ignores_non_capital_increase():
    """유상증자 계열이 아닌 사건은 손대지 않는다."""
    base = classify("주요사항보고서(전환사채권발행결정)")
    assert refine_capital_increase(base, "주주배정") == base


# ── 당사자(is_subject) — 종속회사·출자법인 건은 veto 하지 않는다 (2026-07-28 감사 회귀) ──
_NOT_SUBJECT_CASES = [
    ("유상증자결정(종속회사의주요경영사항)", "유상증자미상"),
    ("유상증자결정(자율공시)(종속회사의주요경영사항)", "유상증자미상"),
    ("출자법인의회생절차및파산절차관련사실등발생", "회생파산"),
    ("단일판매ㆍ공급계약해지(자회사의 주요경영사항)", "계약해지"),
]


@pytest.mark.parametrize("report_nm,event_type", _NOT_SUBJECT_CASES)
def test_not_subject_is_never_vetoed(report_nm, event_type):
    got = classify(report_nm)
    assert got["event_type"] == event_type   # 사건 종류는 남긴다(연구용)
    assert got["is_subject"] == 0
    assert got["is_veto_type"] == 0          # 하지만 제외하지 않는다
    assert got["direction"] == 0
    assert summarize([got])["disc_bad_type"] is None


def test_subject_flag_default_true():
    assert classify("주요사항보고서(유상증자결정)")["is_subject"] == 1
    assert classify("")["is_subject"] == 1


def test_correction_prefix():
    assert is_correction("[기재정정]유상증자결정")
    assert is_correction("[첨부정정]단일판매ㆍ공급계약체결")
    assert not is_correction("유상증자결정")
    # 정정이어도 본문 분류는 그대로 — 집계에서 제외할 뿐이다.
    got = classify("[기재정정]유상증자결정")
    assert got["event_type"] == UNKNOWN_IC   # 배정방식은 별도 조회로 확정
    assert got["is_correction"] == 1


def test_classify_blank():
    got = classify("")
    assert got == {"event_type": "기타", "direction": 0, "is_veto_type": 0,
                   "is_subject": 1, "is_correction": 0}


def _ev(report_nm: str) -> dict:
    return classify(report_nm)


def test_summarize_empty():
    assert summarize([]) == {"disc_count": 0, "disc_bad_type": None, "disc_good_type": None}


def test_summarize_picks_bad_and_good():
    events = [_ev("단일판매ㆍ공급계약체결"),
              refine_capital_increase(_ev("유상증자결정"), "주주배정"),
              _ev("분기보고서(2026.06)")]
    got = summarize(events)
    assert got["disc_count"] == 3
    assert got["disc_bad_type"] == DILUTIVE_IC
    assert got["disc_good_type"] == "공급계약"


def test_summarize_priority_severe_first():
    """여러 악재가 겹치면 NEGATIVE_TYPES 우선순위(심각한 쪽)가 disc_bad_type 이 된다."""
    got = summarize([refine_capital_increase(_ev("유상증자결정"), "주주배정"),
                     _ev("상장폐지사유발생")])
    assert got["disc_bad_type"] == "상장위험"


def test_summarize_excludes_corrections():
    """정정공시만 있으면 veto 하지 않는다 — 원 공시는 접수일에 이미 처리됐다."""
    got = summarize([refine_capital_increase(_ev("[기재정정]유상증자결정"), "주주배정")])
    assert got["disc_count"] == 1
    assert got["disc_bad_type"] is None


def test_summarize_weak_negative_is_recorded_but_no_rule_matches():
    """소송은 악재로 기록되지만 live·candidate 어느 rule 목록에도 없어 제외되지 않는다."""
    got = summarize([_ev("소송등의제기")])
    assert got["disc_bad_type"] == "소송"
    assert "소송" not in SEVERE_TYPES and "소송" not in DILUTION_TYPES
    assert got["disc_good_type"] is None
    assert got["disc_count"] == 1


def test_summarize_priority_puts_weak_negative_last():
    """약한 악재와 겹치면 심각한 쪽이 disc_bad_type 을 차지한다."""
    assert summarize([_ev("소송등의제기"), _ev("전환사채권발행결정")])["disc_bad_type"] == "전환사채"
    assert summarize([_ev("소송등의제기"), _ev("횡령ㆍ배임혐의발생")])["disc_bad_type"] == "횡령배임"
