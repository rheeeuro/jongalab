-- 공시 veto 재등록 — 희석 계열을 live 에서 내리고 candidate 로 측정 (2026-07-28, 같은 날 정정)
--
-- [왜]
-- sql/37 의 veto_disclosure_bad 는 희석(유상증자·CB·BW·EB·감자)까지 live veto 로 묶었다.
-- 같은 날 첫 실수집 데이터가 그 전제를 반증했다:
--   · 6거래일 비정정·당사자 유상증자 8건이 **전부 제3자배정**(주주배정·일반공모 0건).
--     제3자배정은 희석이 아니라 전략적 투자 유치라 방향이 반대일 수 있다.
--   · 실제로 2026-07-27 NAVER 가 NVIDIA 대상 제3자배정(1.48조, 희석 4.6%)을 냈고 주가가
--     올랐는데, 제목 기반 분류는 이를 악재로 보고 **그날 rank 1 종목을 제외할 뻔했다**.
-- CB·BW·EB 도 대부분 사모 제3자배정이라 같은 의심이 든다("희석=악재"는 통설이지 검증 결과가
-- 아니다). → 존속 위험처럼 **사실로 확실한 것만 live**, 희석은 **candidate 로 측정**한다.
--
-- [사전 등록 원칙]
-- 등록 후 predicate 를 조용히 좁히는 것은 '같은 rule 몰래 튜닝'이라 금지다(sql/8 머리말).
-- 그래서 veto_disclosure_bad 는 **retire** 하고 좁힌 조건을 **새 rule 로 재등록**한다.
-- (등록 당일·표본 0 이라 실손은 없지만, 원장에 '무엇을 시도했고 왜 좁혔는지'를 남긴다.)
--
-- [두 rule 의 역할 분담]
--   veto_disclosure_severe   live      — 실매매 제외. 존속위험·불성실공시·횡령배임·계약해지.
--   veto_disclosure_dilution candidate — 실매매 미개입. rule_evaluator 가 매일 채점해
--                                        "제외했으면 이득이었나"(mean_net<0)를 재고,
--                                        edge_policy veto 게이트(n_days>=10 + mean_net<0)를
--                                        통과하면 관리자 승인으로 live 승격.
-- candidate 가 표본을 쌓으려면 disc_bad_type 에 희석 타입도 **써져야** 하므로,
-- core.disclosure_events.summarize 는 live veto 대상이 아니라 **악재 전체(direction=-1)**
-- 에서 disc_bad_type 을 고른다(veto_bad_news 가 라벨 부재로 n=0 에 갇힌 실패의 교훈).

-- is_veto_type 컬럼 의미 축소: '악재 여부'가 아니라 'live veto 대상 여부'.
ALTER TABLE stock_event
    MODIFY COLUMN is_veto_type TINYINT NOT NULL DEFAULT 0
        COMMENT '1 = live veto(veto_disclosure_severe) 대상. 악재 기록 여부는 direction=-1 로 판단';

UPDATE edge_rule
   SET status = 'retired', retired_at = NOW()
 WHERE name = 'veto_disclosure_bad';

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES
('veto_disclosure_severe', '중대 악재 공시 제외', 'f9_disc', 'veto',
 '전자공시(DART)에 회사 존속이 위태롭다는 공시가 뜬 종목을 매수 대상에서 빼는 규칙입니다. 상장폐지·상장적격성 실질심사, 회생절차·파산 신청, 횡령·배임 혐의, 불성실공시법인 지정, 감사의견 거절, 그리고 따놓은 계약이 깨졌다는 공시가 대상입니다. 이런 공시는 다음 날 아침 시초가가 크게 밀리는 것이 거의 확실해서, 하루만 들고 가는 종가베팅에서는 피할 방법이 사지 않는 것뿐입니다. 특히 장이 끝난 뒤 저녁(15:30~18:00)에 나온 공시까지 잡아내 저녁 NXT 매수를 취소하는 것이 이 규칙의 핵심입니다. 유상증자·전환사채 같은 지분 희석 공시는 실제로 손해인지 아직 검증되지 않아 이 규칙에서 빼고 따로 관찰 중입니다.',
 '[{"col":"disc_bad_type","op":"in","value":["상장위험","회생파산","횡령배임","불성실공시","감사의견","계약해지"]}]',
 'exec_leg_ret', 'live', 40, CURDATE()),

('veto_disclosure_dilution', '지분 희석 공시 제외(관찰)', 'f9_disc', 'veto',
 '주식 수가 늘어 내 지분 가치가 희석되는 공시(주주배정·일반공모 유상증자, 전환사채, 신주인수권부사채, 교환사채, 감자)가 뜬 종목을 제외하면 이득인지 확인하는 관찰용 규칙입니다. 흔히 "증자는 악재"라고 하지만 실제 데이터로는 아직 검증되지 않았습니다 — 첫 수집에서 유상증자 8건이 전부 제3자배정(전략적 투자 유치)이었고, 그중 NAVER는 엔비디아 대상 증자 후 주가가 올랐습니다. 그래서 실매매에는 적용하지 않고(관찰 상태), 제외했을 경우의 성적만 매일 기록합니다. 제외 대상들의 평균 수익이 실제로 마이너스로 쌓이면 그때 실매매에 반영합니다. 참고로 제3자배정 유상증자는 방향이 갈려 이 목록에서 빠져 있습니다.',
 '[{"col":"disc_bad_type","op":"in","value":["유상증자","전환사채","신주인수권부사채","교환사채","감자"]}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());
