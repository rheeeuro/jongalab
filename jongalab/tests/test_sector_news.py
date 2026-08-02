"""미매칭 뉴스 섹터·거시 라벨의 순수 로직 계약 고정 (DB·네트워크 무의존).

라벨은 관측 전용이라 자금에 닿지 않지만, **여기가 틀리면 검정 표본이 조용히 오염된다** —
잘못된 라벨은 몇 주 뒤 판정 시점까지 티가 안 난다. 특히:
  · 프리필터의 부분일치 함정(해운대→해운, 핵심→핵, AIM→AI). 2026-08-03 dry-run 실측 오탐
  · 유니버스 어휘 밖 섹터를 '섹터'로 남기지 않는지(조인 안 되는 라벨은 분모만 부풀린다)
  · 요청하지 않은 idx(환각)를 엉뚱한 기사에 붙이지 않는지
"""
from core.sector_news import (
    SECTORS,
    build_prompt,
    clean_headline,
    is_topical,
    parse_response,
)


# ── clean_headline: 발행처 말머리·URL 제거 ──

def test_발행처_말머리와_URL_을_걷어낸다():
    raw = "[네이버뉴스] [속보] 반도체 생산 반등  https://n.news.naver.com/x?a=1"
    assert clean_headline(raw) == "반도체 생산 반등"


def test_빈_입력은_빈_문자열():
    assert clean_headline(None) == ""
    assert clean_headline("   ") == ""


# ── is_topical: 프리필터 (화이트리스트 + 부분일치 함정 차단) ──

def test_산업_정책_거시_어휘는_통과한다():
    assert is_topical("조선 2.7조, 방산 1.7조 '역대급 실적'")
    assert is_topical("6월 생산 2.3% 증가···반도체 생산 반등")
    assert is_topical("트럼프 '하마스 완전 무장 해제 합의'")


def test_증시_무관_뉴스는_걸러진다():
    assert not is_topical("리사, 한국 팬 떼창 벅찼다…서울 단독 콘서트")
    assert not is_topical("16세 류토바, WTA 투어 첫 우승")
    assert not is_topical("한강 수영 30대男 수문 빨려 들어가 심정지")


def test_부분일치_함정을_차단한다():
    # '해운대'가 '해운'으로, '핵심'이 '핵'으로 잡히면 지역·일반 기사가 통째로 유입된다
    assert not is_topical("전재수 부산시장, 해운대 관광특구 선정")
    assert is_topical("해운업 운임 급등")
    assert not is_topical("핵심 인재 영입 경쟁 치열")      # '핵심'만으로는 통과 금지
    assert is_topical("북한 핵실험 임박")


def test_ASCII_약어는_토큰_경계를_요구한다():
    # 경계가 없으면 AI 가 AIM·AIMPOINT 안에서 잡힌다
    assert is_topical("AI 인프라 투자 2200억 달러")
    assert not is_topical("AIMPOINT, 신제품 출시")


# ── parse_response: 화이트리스트·환각 방어 ──

def _item(idx=1, scope="섹터", sector="전기/전자", sentiment=70, reason="근거"):
    return {"idx": idx, "scope": scope, "sector": sector,
            "sentiment": sentiment, "reason": reason}


def test_정상_항목을_그대로_돌려준다():
    out = parse_response({"items": [_item()]})
    assert out[1]["scope"] == "섹터"
    assert out[1]["sector"] == "전기/전자"
    assert out[1]["sentiment"] == 70


def test_유니버스_어휘_밖_섹터는_무관으로_강등된다():
    # LLM 이 '반도체'라고 답하면 daily_stock_report.sector('전기/전자')와 조인되지 않는다
    out = parse_response({"items": [_item(sector="반도체")]})
    assert out[1]["scope"] == "무관"
    assert out[1]["sector"] is None


def test_거시_무관은_섹터를_비운다():
    out = parse_response({"items": [_item(scope="거시", sector="전기/전자")]})
    assert out[1]["sector"] is None


def test_범위_밖_방향은_미판정으로_둔다():
    # 억지로 50 으로 눕히면 '중립'과 '판정 실패'가 구분되지 않는다
    assert parse_response({"items": [_item(sentiment=150)]})[1]["sentiment"] is None
    assert parse_response({"items": [_item(sentiment="높음")]})[1]["sentiment"] is None
    assert parse_response({"items": [_item(sentiment=True)]})[1]["sentiment"] is None


def test_요청에_없는_idx_는_버린다():
    out = parse_response({"items": [_item(idx=1), _item(idx=99)]}, expected={1})
    assert set(out) == {1}


def test_형식_불량은_빈_dict():
    assert parse_response(None) == {}
    assert parse_response({"items": "x"}) == {}
    assert parse_response({"items": [{"scope": "섹터"}]}) == {}   # idx 없음


# ── build_prompt: 섹터 화이트리스트가 프롬프트에 실린다 ──

def test_프롬프트에_허용_섹터가_모두_들어간다():
    prompt = build_prompt([{"idx": 0, "headline": "반도체 업황 반등"}])
    for s in SECTORS:
        assert s in prompt
    assert "0. 반도체 업황 반등" in prompt
