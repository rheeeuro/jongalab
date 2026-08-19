"""Edge Ledger 텔레그램 알림(core/notifications.send_edge_rule_alert) 계약 고정.

알림은 **두 축이 섞인 화면**이다 — 승격은 '승인해 달라', 운용 전이(live↔paused)는 '이미
바꿨다'. 이 둘이 한 메시지에서 구분되지 않으면 자동 전이가 승인 대기로 읽혀(반대도 마찬가지)
사람이 잘못 판단한다. 전송은 하지 않고 조립된 본문만 검사한다.
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
    # 영구 종결과 헷갈리지 않게 못 박는다
    assert "retired" in msg and "관리자만 결정" in msg


def test_promotion_keeps_its_approval_wording(monkeypatch):
    # 반대 방향 — 승격만 온 날에 전이 안내가 붙으면 '이미 승격됐다'로 읽힌다.
    box = _capture(monkeypatch)
    N.send_edge_rule_alert(
        [{"name": "p", "family": "f1_news", "role": "selector", "n": 30,
          "mean_net": 1.2, "ci_low": 0.3, "stage": "discovery"}], [], [])
    msg = box["msg"]
    assert "승격은 관리자 승인이 필요합니다" in msg
    assert "자동 반영된 결과 보고" not in msg


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
