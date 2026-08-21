"""Edge Ledger 텔레그램 알림(core/notifications.send_edge_rule_alert) 계약 고정.

알림에는 성격이 다른 줄이 섞인다 — **이미 바꿨다**(자동 승격 · live↔paused 전이)와
**승인해 달라**(누적 게이트가 막은 승격 승인 대기 · 집행 설계 필요). 이 둘이 한 메시지에서
구분되지 않으면 사후 보고가 승인 대기로 읽혀(반대도 마찬가지) 사람이 잘못 판단한다.
전송은 하지 않고 조립된 본문만 검사한다.
"""
import core.notifications as N


def _capture(monkeypatch):
    box = {}
    monkeypatch.setattr(N, "_send_telegram_admin", lambda m: (box.setdefault("msg", m), 1)[1])
    return box


def _tr(name, to, alpha, **kw):
    return {"name": name, "family": "f5_supply", "role": "selector",
            "from": "live" if to == "paused" else "paused", "to": to,
            "reason": f"테스트 사유({to})", "alpha": alpha, "beta": 0.7,
            "down_day_mean": -1.2, "down_day_n": 7,
            "n": 80, "mean_net": 0.5, "mean_net_days": 0.4, **kw}


def test_nothing_to_report_sends_nothing(monkeypatch):
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [], [])
    assert "msg" not in box


def test_transition_alone_still_sends(monkeypatch):
    # 승격 후보가 없는 날에도 전이만으로 알림이 나가야 한다(전이는 이미 반영된 사실이다).
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [_tr("r_pause", "paused", -0.3)], [])
    assert "r_pause" in box["msg"]


def test_paused_and_resumed_are_separate_sections(monkeypatch):
    """내려간 줄과 올라온 줄이 한 섹션에 섞이면 방향을 오독한다."""
    box = _capture(monkeypatch)
    N.send_edge_rule_alert(
        [], [_tr("r_pause", "paused", -0.3), _tr("r_resume", "live", 0.4)], [])
    msg = box["msg"]
    assert "자동 일시중지" in msg and "자동 복귀" in msg
    # 각 이름이 자기 섹션 안에 있어야 한다
    pause_sec, resume_sec = msg.split("▶️")
    assert "r_pause" in pause_sec and "r_pause" not in resume_sec
    assert "r_resume" in resume_sec and "r_resume" not in pause_sec


def test_transition_is_reported_not_requested(monkeypatch):
    """자동 전이는 승인 요청이 아니다 — 안내가 '후보일 뿐'으로 나가면 반대로 읽힌다."""
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [_tr("r", "paused", -0.3)], [])
    msg = box["msg"]
    assert "자동 반영된 결과 보고" in msg and "승인 불필요" in msg
    assert "후보일 뿐입니다" not in msg
    # 영구 종결과 헷갈리지 않게 못 박는다. 판정 탈락은 2026-08-21 부터 자동이므로 문구가
    # 그 범위를 좁혀서 말한다 — '전부 사람이 결정한다'로 남으면 자동 종결과 모순된다.
    assert "판정 탈락 **외의** 종결" in msg and "관리자만 결정" in msg


def _promo(name, **kw):
    return {"name": name, "family": "f1_news", "role": "selector", "n": 30,
            "mean_net": 1.2, "ci_low": 0.3, "stage": "discovery", **kw}


def test_pending_promotion_keeps_its_approval_wording(monkeypatch):
    """누적 게이트가 막은 승격은 **승인 대기**다 — 사후 보고 문구가 붙으면 이미 올라간 것으로 읽힌다."""
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([_promo("p", reason="신뢰구간 하한 미충족: ci_low=-0.02")], [], [])
    msg = box["msg"]
    assert "승격 승인 대기" in msg and "관리자 승인이 필요합니다" in msg
    assert "이미 반영된 결과 보고" not in msg


def test_auto_promotion_is_reported_not_requested(monkeypatch):
    """자동 승격은 승인 요청이 아니다 — '승인이 필요합니다'가 붙으면 버튼을 찾게 된다."""
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [], [], [_promo("auto")])
    msg = box["msg"]
    assert "자동 승격" in msg and "이미 반영됨" in msg
    assert "이미 반영된 결과 보고" in msg and "승인 불필요" in msg
    assert "승인이 필요합니다" not in msg
    # 승격이 자동이 된 뒤에도 (판정 탈락 외의) 종결은 사람 몫이라는 걸 못 박는다
    assert "판정 탈락 **외의** 종결" in msg and "관리자만 결정" in msg


def test_auto_promotion_alone_still_sends(monkeypatch):
    # 자동 승격만 있는 날에도 알림이 나가야 한다(사후 보고라도 사람이 알아야 한다).
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [], [], [_promo("auto")])
    assert "auto" in box["msg"]


def test_auto_and_pending_promotions_are_separate_sections(monkeypatch):
    """올라간 줄과 막힌 줄이 한 섹션에 섞이면 무엇을 승인해야 하는지 알 수 없다."""
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([_promo("held", reason="ci_low 미충족")], [], [], [_promo("up")])
    msg = box["msg"]
    auto_sec, pending_sec = msg.split("🟢")
    assert "up" in auto_sec and "held" not in auto_sec
    assert "held" in pending_sec and "up" not in pending_sec


def test_reason_carries_the_streak_confirmation(monkeypatch):
    """사유 줄이 빠지면 '하루짜리 신호가 아니다'라는 근거가 사라진다(구 잡음 알림과 같아진다)."""
    box = _capture(monkeypatch)
    tr = _tr("r", "paused", -0.19)
    tr["reason"] = "최근 10거래일 매수 종목 시장조정수익(alpha) -0.19% < 0 — 2표본일 연속"
    N.send_edge_rule_alert([], [tr], [])
    assert "2표본일 연속" in box["msg"]


def test_concentration_warning_still_flags_sign_conflict(monkeypatch):
    # 종목-일 가중과 일 등가중의 부호가 갈리면 쏠림 — 판단 재료라 전이 줄에도 남아야 한다.
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [_tr("r", "paused", -0.3, mean_net=1.09,
                                    mean_net_days=-0.40)], [])
    assert "⚠️쏠림" in box["msg"]


def test_veto_line_marks_that_negative_is_normal(monkeypatch):
    # veto 의 mean_net 은 '제외한' 종목 성적이라 음수가 정상 — 부호 방향을 줄에 못 박는다.
    box = _capture(monkeypatch)
    tr = _tr("v", "live", 0.2)
    tr["role"] = "veto"
    N.send_edge_rule_alert([], [tr], [])
    assert "제외 종목" in box["msg"] and "음수=정상" in box["msg"]


def _ret(name, verdict="discovery_failed"):
    return {"name": name, "family": "f5_supply", "role": "selector", "n": 24,
            "mean_net": 1.349, "ci_low": -0.301, "verdict": verdict,
            "reason": "발견창(첫 10거래일) 성적이 실전 투입 기준에 못 미쳐 종결했습니다"
                      "(신뢰구간 하한 미충족). 다시 도전하려면 '재검증'으로 되돌리세요"}


def test_auto_retirement_is_reported_with_the_way_back(monkeypatch):
    """자동 종결은 사후 보고이고, **재도전 경로**가 줄에 없으면 화면에 '왜 죽었나'만 남는다."""
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [], [], [], [_ret("r")])
    msg = box["msg"]
    assert "자동 종결" in msg and "이미 반영됨" in msg
    assert "재검증" in msg and "표본 리셋" in msg
    # 승인 요청이 아니다
    assert "관리자 승인이 필요합니다" not in msg


def test_auto_retirement_alone_still_sends(monkeypatch):
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [], [], [], [_ret("only")])
    assert "only" in box["msg"]


def test_manual_retire_scope_is_narrowed_not_dropped(monkeypatch):
    """판정 탈락은 자동이지만 그 **외의** 종결은 여전히 사람 몫 — 문구가 둘을 갈라야 한다."""
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [_tr("t", "paused", -0.3)], [], [], [_ret("r")])
    msg = box["msg"]
    assert "판정 탈락 **외의** 종결" in msg and "관리자만 결정" in msg
    # 옛 문구("영구 종결은 여전히 관리자만")가 남아 있으면 자동 종결과 모순된다
    assert "영구 종결(retired)은 여전히 관리자만" not in msg


def test_retirement_and_transition_are_separate_sections(monkeypatch):
    box = _capture(monkeypatch)
    N.send_edge_rule_alert([], [_tr("paused_one", "paused", -0.3)], [], [], [_ret("retired_one")])
    pause_sec, retire_sec = box["msg"].split("🔴")
    assert "paused_one" in pause_sec and "retired_one" not in pause_sec
    assert "retired_one" in retire_sec and "paused_one" not in retire_sec
