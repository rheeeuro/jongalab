"""news_veto_judge 순수 로직 테스트 — LLM 응답 검증·확신도 게이트·뉴스 창 계산.

돈이 걸린 판정(severe=1 → trading 개장 즉시 전량매도)이라, LLM 출력의 형식 불량이
절대 '발동'으로 새지 않는 것을 고정한다. DB·네트워크 없이 monkeypatch 로 검증.
"""
from datetime import datetime

import pytest

from core import news_veto_judge as judge
from core.config import NEWS_GUARD_MIN_CONFIDENCE


# ── validate_verdict ──

def test_validate_ok_normalizes_fields():
    out = judge.validate_verdict({
        "severe": True, "confidence": 92, "category": "임상실패",
        "reason": "FDA 승인 반려", "evidence": ["헤드라인1", "헤드라인2", "3", "4"],
    })
    assert out == {"severe": True, "confidence": 92, "category": "임상실패",
                   "reason": "FDA 승인 반려", "evidence": ["헤드라인1", "헤드라인2", "3"]}


def test_validate_string_severe_coerced():
    out = judge.validate_verdict({"severe": "true", "confidence": "88", "category": "계약파기"})
    assert out["severe"] is True and out["confidence"] == 88


@pytest.mark.parametrize("data", [
    None,                                      # LLM 실패(parse None)
    "not a dict",
    {},                                        # severe 없음
    {"severe": "maybe", "confidence": 90},     # severe 불량
    {"severe": True},                          # confidence 없음 — 확신도 없는 severe 금지
    {"severe": True, "confidence": "높음"},     # confidence 불량
])
def test_validate_rejects_malformed(data):
    assert judge.validate_verdict(data) is None


def test_validate_clamps_confidence_and_category():
    out = judge.validate_verdict({"severe": False, "confidence": 999, "category": "듣도보도못한분류"})
    assert out["confidence"] == 100
    assert out["category"] == "해당없음"


# ── is_actionable (확신도 게이트) ──

def test_actionable_requires_confidence_gate():
    base = {"severe": True, "category": "임상실패", "reason": "", "evidence": []}
    assert judge.is_actionable({**base, "confidence": NEWS_GUARD_MIN_CONFIDENCE}) is True
    assert judge.is_actionable({**base, "confidence": NEWS_GUARD_MIN_CONFIDENCE - 1}) is False, \
        "확신도 미달 severe 는 발동하지 않는다(기록만)"


def test_actionable_requires_severe():
    assert judge.is_actionable({"severe": False, "confidence": 100,
                                "category": "해당없음", "reason": "", "evidence": []}) is False
    assert judge.is_actionable(None) is False


# ── judge_headlines (complete_json 경유) ──

ROWS = [{"headline": "테스트제약, FDA 승인 반려", "channel_name": "속보채널",
         "created_at": datetime(2026, 7, 15, 6, 30)}]


def test_judge_headlines_passes_validated_verdict(monkeypatch):
    monkeypatch.setattr(judge, "complete_json",
                        lambda prompt, **kw: {"severe": True, "confidence": 95,
                                              "category": "임상실패", "reason": "r", "evidence": []})
    out = judge.judge_headlines("테스트제약", "000001", ROWS)
    assert out["severe"] is True and out["confidence"] == 95


def test_judge_headlines_none_on_llm_failure(monkeypatch):
    monkeypatch.setattr(judge, "complete_json", lambda prompt, **kw: None)
    assert judge.judge_headlines("테스트제약", "000001", ROWS) is None


def test_judge_headlines_none_on_garbage(monkeypatch):
    monkeypatch.setattr(judge, "complete_json", lambda prompt, **kw: {"severe": "글쎄"})
    assert judge.judge_headlines("테스트제약", "000001", ROWS) is None


def test_judge_headlines_empty_rows():
    assert judge.judge_headlines("테스트제약", "000001", []) is None


# ── news_window_start (전거래일 15:00) ──

def test_window_start_weekday(monkeypatch):
    monkeypatch.setattr(judge, "is_trading_day", lambda dt: dt.weekday() < 5)
    # 수요일 아침 → 화요일 15:00
    assert judge.news_window_start(datetime(2026, 7, 15, 7, 0)) == datetime(2026, 7, 14, 15, 0)


def test_window_start_skips_weekend(monkeypatch):
    monkeypatch.setattr(judge, "is_trading_day", lambda dt: dt.weekday() < 5)
    # 월요일 아침 → 금요일 15:00 (주말 뉴스가 전부 창에 들어온다)
    assert judge.news_window_start(datetime(2026, 7, 13, 7, 0)) == datetime(2026, 7, 10, 15, 0)
