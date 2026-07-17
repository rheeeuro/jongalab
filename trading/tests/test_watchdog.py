"""watchdog.missing_workers 순수 로직 테스트 — 미실행 감시 판정 고정.

규칙: 마감 시각이 지난 핵심 워커 중 완료 마커가 없는 것만 '미실행'으로 본다.
마감 전 워커는(아직 돌 시간) 누락이어도 경보하지 않는다.
scheduler_stale: jongalab 스케줄러 dead-man's switch — job_run 최신 기록이
없거나(None) 임계 시간 이상 오래되면 중단으로 판정한다.
"""
from datetime import datetime, timedelta

from workers.watchdog import missing_workers, scheduler_stale, CRITICAL_WORKERS

CRIT = [
    ("settle:nxt",      (8, 5),  "NXT"),
    ("settle:krx_open", (9, 5),  "KRX open"),
    ("settle:krx",      (9, 28), "KRX"),
    ("monitor",         (9, 30), "monitor"),
]


def _names(missing):
    return {m[0] for m in missing}


def test_all_done_no_alert():
    done = {"settle:nxt", "settle:krx_open", "settle:krx", "monitor"}
    assert missing_workers((9, 35), done, CRIT) == []


def test_all_missing_after_deadlines_all_reported():
    assert _names(missing_workers((9, 35), set(), CRIT)) == {
        "settle:nxt", "settle:krx_open", "settle:krx", "monitor"}


def test_only_overdue_workers_flagged():
    # 08:30 시점 — settle:nxt(08:05)만 마감 지남. settle:krx_open/krx/monitor 는 아직 마감 전.
    assert _names(missing_workers((8, 30), set(), CRIT)) == {"settle:nxt"}


def test_krx_open_flagged_after_its_deadline():
    # 09:10 시점 — settle:nxt(08:05)·settle:krx_open(09:05) 마감 지남. krx(09:28)/monitor 는 아직.
    assert _names(missing_workers((9, 10), set(), CRIT)) == {"settle:nxt", "settle:krx_open"}


def test_done_marker_excludes_from_missing():
    done = {"settle:nxt", "settle:krx_open"}
    assert _names(missing_workers((9, 35), done, CRIT)) == {"settle:krx", "monitor"}


def test_exactly_at_deadline_counts_as_overdue():
    # 마감 시각 정각이면 '지남'으로 간주(>=).
    assert _names(missing_workers((8, 5), set(), CRIT)) == {"settle:nxt"}


def test_before_any_deadline_empty():
    assert missing_workers((7, 0), set(), CRIT) == []


def test_default_critical_list_shape():
    # 기본 감시 목록은 (name, (h,m), desc) 3-튜플이며 핵심 트리오를 포함한다.
    names = {c[0] for c in CRITICAL_WORKERS}
    assert {"settle:nxt", "settle:krx", "monitor"} <= names
    for name, by, desc in CRITICAL_WORKERS:
        assert isinstance(name, str) and len(by) == 2 and isinstance(desc, str)


NOW = datetime(2026, 7, 17, 9, 35)


def test_scheduler_fresh_not_stale():
    # 15분 전 잡 실행 기록 — 정상.
    assert scheduler_stale(NOW, NOW - timedelta(minutes=15)) is False


def test_scheduler_no_record_is_stale():
    # 기록 자체가 없으면(테이블 비어있음) 중단으로 본다.
    assert scheduler_stale(NOW, None) is True


def test_scheduler_old_record_is_stale():
    # 임계(기본 2시간) 이상 무기록 — 중단 판정 (2026-07-15 사고 시나리오).
    assert scheduler_stale(NOW, NOW - timedelta(hours=2)) is True
    assert scheduler_stale(NOW, NOW - timedelta(days=2)) is True


def test_scheduler_just_under_threshold_not_stale():
    assert scheduler_stale(NOW, NOW - timedelta(minutes=119)) is False


def test_scheduler_custom_threshold():
    assert scheduler_stale(NOW, NOW - timedelta(minutes=40), stale_hours=0.5) is True
    assert scheduler_stale(NOW, NOW - timedelta(minutes=20), stale_hours=0.5) is False
