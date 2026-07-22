-- 레버리지 ETF 대체매수 매핑 테이블 (2026-07-23)
-- 레버리지 사용(risk_config LEVERAGE_ENABLED=1)이 켜지면 signal_executor 가 매수 직전
-- 원종목을 매핑된 레버리지 ETF 로 치환한다. 토글 기본값은 0(off)이라 시드만 넣어도 무영향.
CREATE TABLE IF NOT EXISTS leverage_map (
    src_stk_cd  VARCHAR(20) PRIMARY KEY,   -- 원종목코드 (신호에 나오는 코드)
    src_stk_nm  VARCHAR(64),
    etf_stk_cd  VARCHAR(20) NOT NULL,      -- 대체 매수할 레버리지 ETF 코드
    etf_stk_nm  VARCHAR(64),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 기본 매핑: 삼성전자·SK하이닉스 → 각 단일종목 레버리지 ETF (대시보드에서 편집 가능)
INSERT INTO leverage_map (src_stk_cd, src_stk_nm, etf_stk_cd, etf_stk_nm) VALUES
    ('005930', '삼성전자',   '0193W0', 'KODEX 삼성전자단일종목레버리지'),
    ('000660', 'SK하이닉스', '0193T0', 'KODEX SK하이닉스단일종목레버리지')
ON DUPLICATE KEY UPDATE
    src_stk_nm = VALUES(src_stk_nm),
    etf_stk_cd = VALUES(etf_stk_cd),
    etf_stk_nm = VALUES(etf_stk_nm);
