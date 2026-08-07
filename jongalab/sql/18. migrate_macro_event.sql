-- 거시 이벤트 캘린더 — trading macro_gate(종가베팅 보유 창의 예정 이벤트 시드 축소)가 읽기 전용 조회.
-- FOMC·CPI·고용·PPI·금통위 일정은 연 단위로 미리 공개되므로 수동 시드한다(외부 API 불필요).
-- severity: 1 참고 / 2 주의(관찰 전용 — 감액 없음, 진단 기록만) / 3 중대(live 감액).
-- 근거 백테스트(2026-07-15, 4/9~7/10 63거래일): sev3 이벤트 밤 선정종목 일평균 -0.74% vs 평일 +1.04%
--   (Welch t=-2.27, 음수일 62% vs 25%). PPI(sev2)는 +3.6%로 감액 근거 없음 → 관찰 전용.

CREATE TABLE IF NOT EXISTS macro_event (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_time DATETIME NOT NULL COMMENT '발표/결정 시각(KST)',
    name VARCHAR(100) NOT NULL,
    category VARCHAR(20) NOT NULL COMMENT 'rate | inflation | employment | earnings | tariff | other',
    severity TINYINT NOT NULL COMMENT '1 참고 / 2 주의(관찰) / 3 중대(live 감액)',
    source VARCHAR(20) NOT NULL DEFAULT 'manual',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_macro_event (event_time, name),
    KEY idx_macro_event_time (event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── 2026년 시드 (4월~12월) ──
-- 시각은 KST. 미 지표 8:30 ET = 21:30 KST(서머타임) / 22:30 KST(11월 첫 일요일 해제 이후).
-- FOMC 성명 14:00 ET = 익일 03:00 KST(서머타임) / 04:00 KST(해제 이후).
-- 금통위는 발표(~09:50)가 익일 시가 매도 이후라 창 밖 — 감액 무영향, 연구 라벨용.
-- 과거분(4~7월)은 audit·연구 조인용. 재실행 안전(INSERT IGNORE + UNIQUE).

-- FOMC 금리결정 (severity 3)
INSERT IGNORE INTO macro_event (event_time, name, category, severity) VALUES
('2026-04-30 03:00:00', 'FOMC 금리결정', 'rate', 3),
('2026-06-18 03:00:00', 'FOMC 금리결정', 'rate', 3),
('2026-07-30 03:00:00', 'FOMC 금리결정', 'rate', 3),
('2026-09-17 03:00:00', 'FOMC 금리결정', 'rate', 3),
('2026-10-29 03:00:00', 'FOMC 금리결정', 'rate', 3),
('2026-12-10 04:00:00', 'FOMC 금리결정', 'rate', 3);

-- 미 CPI (severity 3)
INSERT IGNORE INTO macro_event (event_time, name, category, severity) VALUES
('2026-04-10 21:30:00', '미 CPI', 'inflation', 3),
('2026-05-12 21:30:00', '미 CPI', 'inflation', 3),
('2026-06-10 21:30:00', '미 CPI', 'inflation', 3),
('2026-07-14 21:30:00', '미 CPI', 'inflation', 3),
('2026-08-12 21:30:00', '미 CPI', 'inflation', 3),
('2026-09-11 21:30:00', '미 CPI', 'inflation', 3),
('2026-10-14 21:30:00', '미 CPI', 'inflation', 3),
('2026-11-10 22:30:00', '미 CPI', 'inflation', 3),
('2026-12-10 22:30:00', '미 CPI', 'inflation', 3);

-- 미 고용보고서 (severity 3)
INSERT IGNORE INTO macro_event (event_time, name, category, severity) VALUES
('2026-04-03 21:30:00', '미 고용보고서', 'employment', 3),
('2026-05-08 21:30:00', '미 고용보고서', 'employment', 3),
('2026-06-05 21:30:00', '미 고용보고서', 'employment', 3),
('2026-07-02 21:30:00', '미 고용보고서', 'employment', 3),
('2026-08-07 21:30:00', '미 고용보고서', 'employment', 3),
('2026-09-04 21:30:00', '미 고용보고서', 'employment', 3),
('2026-10-02 21:30:00', '미 고용보고서', 'employment', 3),
('2026-11-06 22:30:00', '미 고용보고서', 'employment', 3),
('2026-12-04 22:30:00', '미 고용보고서', 'employment', 3);

-- 미 PPI (severity 2 — 백테스트상 감액 근거 없음, 관찰 전용)
INSERT IGNORE INTO macro_event (event_time, name, category, severity) VALUES
('2026-04-14 21:30:00', '미 PPI', 'inflation', 2),
('2026-05-13 21:30:00', '미 PPI', 'inflation', 2),
('2026-06-11 21:30:00', '미 PPI', 'inflation', 2),
('2026-07-15 21:30:00', '미 PPI', 'inflation', 2),
('2026-08-13 21:30:00', '미 PPI', 'inflation', 2),
('2026-09-10 21:30:00', '미 PPI', 'inflation', 2),
('2026-10-15 21:30:00', '미 PPI', 'inflation', 2),
('2026-11-13 22:30:00', '미 PPI', 'inflation', 2),
('2026-12-15 22:30:00', '미 PPI', 'inflation', 2);

-- 한은 금통위 기준금리 결정 (severity 2 — 발표가 시가 매도 후라 창 밖, 연구 라벨용)
INSERT IGNORE INTO macro_event (event_time, name, category, severity) VALUES
('2026-07-16 09:50:00', '한은 금통위', 'rate', 2),
('2026-08-27 09:50:00', '한은 금통위', 'rate', 2),
('2026-10-22 09:50:00', '한은 금통위', 'rate', 2),
('2026-11-26 09:50:00', '한은 금통위', 'rate', 2);
