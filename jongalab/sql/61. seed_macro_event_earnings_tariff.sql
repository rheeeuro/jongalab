-- 2026-08-07 macro_event 시드 확장 — 해외 실적 발표 + 관세 발효일 (모두 severity 2 = 관찰 전용)
--
-- 배경: 기존 캘린더(sql/18)는 **정기 거시 지표**(FOMC·CPI·고용·PPI·금통위)만 담는다. 그래서
--   "샌디스크 실적, 관세, 전쟁 합의" 같은 시황 이벤트는 캘린더 축에서 통째로 빠져 있었다.
--   그중 **미리 일정이 잡히는 것**(해외 실적, 관세 발효일)은 이 캘린더로 바로 잡을 수 있고,
--   돌발성(행정명령·지정학)은 원리상 캘린더로 못 잡아 뉴스 축 몫이다(news_sector_label 관찰 중).
--
-- ⚠️ severity 2 = **감액 없음**. macro_gate 는 sev3 만 시드를 깎고(keep 0.5), sev2 는 진단에만
--    기록한다. 의도된 것이다 — 이 축의 익일 성적 영향은 측정된 바 없고, 같은 계열에서 미검증 축을
--    live 로 켰다 실패한 전례가 있다(regime_gate 상시컷, macro VIX 프록시 부호 반대 —
--    docs/history/gates-sizing.md). 표본이 쌓이면 audit_log('macro_gate').events 로 채점 후 판단한다.
--
-- 반도체 실적을 고른 이유: 유니버스 상위 섹터가 전기/전자이고, 갭 경로의 실측 채널이 미 기술주
--   축(NQ 선물 당일 t=+3.69, 2026-08-03 검정)이라 개별 실적 중 전이 가능성이 가장 큰 계열이다.
--
-- 시각은 KST 변환값이고 원 시각을 주석에 남긴다. 실적 일정은 **확정 전 추정치가 섞이므로**
--   (source='yfinance', 2026-08-07 조회) 분기마다 재확인이 필요하다. 정기 지표와 달리 연 단위로
--   미리 확정되지 않는다는 점이 이 시드의 약점이다.
-- 재실행 안전(INSERT IGNORE + UNIQUE(event_time, name)) — 날짜가 바뀌면 새 행이 생기므로
--   변경 시 옛 행을 지우고 다시 넣는다(중복 경보가 아니라 캘린더 오염을 막기 위해).

-- category 어휘 확장 — 기존 rate|inflation|employment|other 에 earnings·tariff 추가.
ALTER TABLE macro_event
    MODIFY COLUMN category VARCHAR(20) NOT NULL
        COMMENT 'rate | inflation | employment | earnings | tariff | other';

-- ── 미 반도체 실적 (severity 2, 관찰) ──
INSERT IGNORE INTO macro_event (event_time, name, category, severity, source) VALUES
    ('2026-08-27 05:00:00', '엔비디아 실적',  'earnings', 2, 'yfinance'),  -- NVDA 2026-08-26 16:00 EDT
    ('2026-09-03 05:00:00', '브로드컴 실적',  'earnings', 2, 'yfinance'),  -- AVGO 2026-09-02 16:00 EDT
    ('2026-09-24 05:00:00', '마이크론 실적',  'earnings', 2, 'yfinance'),  -- MU   2026-09-23 16:00 EDT
    ('2026-10-15 21:00:00', 'TSMC 실적',     'earnings', 2, 'yfinance'),  -- TSM  2026-10-15 08:00 EDT
    ('2026-11-07 05:00:00', '샌디스크 실적',  'earnings', 2, 'yfinance');  -- SNDK 2026-11-06 15:00 EST

-- ── 관세 발효일 (severity 2, 관찰) ──
-- 2026-08-07 트럼프 폴리실리콘 파생제품 15% 관세 행정명령 서명 → 120일 뒤 발효(= 2026-12-05).
-- 발효일은 그 자체로 예정된 이진 이벤트라 캘린더 축에 맞는다. 발표(돌발)는 이미 지나갔으므로
-- 여기 담는 건 발효일뿐이다. 시각은 미 동부 자정 발효 가정 → KST 14:00 로 둔다(창 판정용 근사).
INSERT IGNORE INTO macro_event (event_time, name, category, severity, source) VALUES
    ('2026-12-05 14:00:00', '美 폴리실리콘 파생제품 15% 관세 발효', 'tariff', 2, 'manual');
