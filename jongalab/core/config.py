"""
공통 설정 모듈 - DB 설정, 환경변수, 상수를 한 곳에서 관리
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# cwd 가 jongalab/ 이므로 리포지토리 루트(.env)를 절대경로로 명시 로드한다.
# jongalab/core/config.py → parents[2] == 리포지토리 루트
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# DB 설정
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'user': os.getenv('DB_USER', 'stock_user'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('JONGALAB_DB_NAME', 'jongalab'),
    'port': int(os.getenv('DB_PORT', '3307')),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'use_unicode': True,
}

# trading DB 설정 — closing_bet 이 매수 시그널(trade_signal)을 적재하는 대상.
# (같은 MariaDB 서버, 스키마만 분리. trading 도메인이 소비한다.)
TRADING_DB_CONFIG = {**DB_CONFIG, 'database': os.getenv('TRADING_DB_NAME', 'trading')}

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# 텔레그램 API (Telethon)
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')

# AI 모델 설정 (Ollama)
OLLAMA_HOST = 'http://127.0.0.1:11434'
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'exaone3.5:7.8b')
# Ollama 호출 상한(초). 콘텐츠 1건 분석이 이 시간을 넘기면 httpx 가 읽기 타임아웃을 던진다
# (무한정 늘어지는 분석이 잡 전체를 타임아웃시키는 것을 막는 백스톱). 관측 최대 ~435s 위 + 잡
# 타임아웃(840s) 아래로 잡는다 — youtube_collector 소프트 데드라인과 합쳐 하드킬을 원천 차단.
OLLAMA_TIMEOUT = int(os.getenv('OLLAMA_TIMEOUT', '480'))

# OpenAI 설정 (일간 리포트용)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-5.4-nano')

# ── 뉴스 베토 감시 (workers/news_guard.py) ──
# 보유 종목의 밤사이 중대 악재를 OpenAI 로 판정해 news_veto_verdict 에 기록 →
# trading monitor 가 severe=1 종목을 개장 즉시 전량 매도한다.
NEWS_GUARD_POLL_SEC = int(os.getenv('NEWS_GUARD_POLL_SEC', '300'))            # 판정 폴링 주기(초)
# severe 발동 최소 확신도(0~100) — 미만이면 severe=0 으로 기록만(오탐 완충)
NEWS_GUARD_MIN_CONFIDENCE = int(os.getenv('NEWS_GUARD_MIN_CONFIDENCE', '85'))
NEWS_GUARD_MAX_HEADLINES = int(os.getenv('NEWS_GUARD_MAX_HEADLINES', '30'))   # 종목당 판정 헤드라인 상한

# ── 뉴스 재료 지속성 라벨 (core/news_material_judge.py, closing_bet 이 호출) ──
# 뉴스가 있는 유니버스 전건을 OpenAI 로 벌크 판정해 daily_stock_report 에 적재(점수 무영향).
# 끄면 라벨이 NULL 로 남고 선정은 그대로 동작한다(rule 은 NULL=매칭 실패로 미개입).
NEWS_JUDGE_ENABLED = os.getenv('NEWS_JUDGE_ENABLED', '1') == '1'
NEWS_JUDGE_BATCH_SIZE = int(os.getenv('NEWS_JUDGE_BATCH_SIZE', '8'))          # 1회 호출 종목 수
NEWS_JUDGE_LOOKBACK_DAYS = int(os.getenv('NEWS_JUDGE_LOOKBACK_DAYS', '5'))    # 헤드라인 룩백(재료 stage 판정 근거)
NEWS_JUDGE_MAX_HEADLINES = int(os.getenv('NEWS_JUDGE_MAX_HEADLINES', '20'))   # 종목당 헤드라인 상한(최신 우선)
# 후속 재료 실현 채점 창(거래일 아닌 달력일) — outcome_backfill 이 news_followup_days 를 채운다.
# news_mention 보존(NEWS_RETENTION_DAYS)보다 창 + 백필 지연이 크면 표본이 잘린다.
NEWS_FOLLOWUP_WINDOW_DAYS = int(os.getenv('NEWS_FOLLOWUP_WINDOW_DAYS', '10'))
# news_mention 원자료 보존일(cleanup_content 가 사용). 14 → 30 상향(2026-07-31): 네이버 수집
# 병행 검증이 "같은 날 텔레그램만 vs 네이버 포함" 을 원자료에서 소급 재계산하는 방식이라,
# 14일이면 검증 창이 앞에서 잘린다. 승격 판정이 끝나면 14로 되돌려도 된다.
NEWS_RETENTION_DAYS = int(os.getenv('NEWS_RETENTION_DAYS', '30'))

# ── 뉴스 소스 게이트 (news_mention.source) ──
# **뉴스 원자료의 어느 소스를 소비할지**를 한 곳에서 정한다. repository/news.py 의 모든 조회가
# 이 집합으로 필터하므로, 새 소스를 수집만 해두고 라벨·룰·veto·LLM 판정에는 일절 반영하지 않는
# '관측 전용' 기간을 둘 수 있다(승격은 .env 한 줄).
#   왜 필요한가: 소스를 늘리면 news_count·news_prior_avg·surprise 배수가 도입일에 계단식으로
#   튄다. 실측(2026-07-31 프로브) 네이버 당일 562행 vs 텔레그램 273행이고 **헤드라인 중복은
#   2%뿐**이라 상쇄 없이 3배로 순증한다. news_unique_count 를 쓰는 rule 3종(그중
#   `veto_bad_news` 는 **live = 자금 경로**)의 표본이 중간에 성질이 바뀌므로, 검증 전 유입을
#   막는 게이트가 없으면 도입 자체가 실탄 변경이 된다.
# 값은 쉼표 구분(예: 'telegram,naver'). 순서는 무관.
NEWS_ACTIVE_SOURCES = tuple(
    s.strip() for s in os.getenv('NEWS_ACTIVE_SOURCES', 'telegram').split(',') if s.strip()
) or ('telegram',)

# ── 네이버 증권 종목별 뉴스 수집 (workers/naver_news_collector.py) ──
# 유니버스 종목의 재료 라벨 커버리지가 47%(2026-07-31 실측 18/38)뿐인 것을 메우기 위한 소스.
# 종목코드로 조회하므로 사명 사전매칭이 필요 없다(텔레그램 경로의 no_match 55% 문제를 우회).
NAVER_NEWS_ENABLED = os.getenv('NAVER_NEWS_ENABLED', '1') == '1'
NAVER_NEWS_BASE_URL = os.getenv('NAVER_NEWS_BASE_URL', 'https://m.stock.naver.com')
# 종목당 1페이지만 조회한다. 40건이면 30분 주기 증분에는 충분하고, 첫 사이클에 대형주가
# 잘리는 정도는 감수한다(실측 삼성전자·SK하이닉스는 20건이 전부 당일 기사였다).
NAVER_NEWS_PAGE_SIZE = int(os.getenv('NAVER_NEWS_PAGE_SIZE', '40'))
NAVER_NEWS_SLEEP_SEC = float(os.getenv('NAVER_NEWS_SLEEP_SEC', '0.3'))   # 종목 간 간격
NAVER_NEWS_TIMEOUT = int(os.getenv('NAVER_NEWS_TIMEOUT', '10'))

# ── 증권 섹션 뉴스 수집 (workers/sec_news_collector.py) — 뉴스 탭 표시 전용 ──
# 종합 속보 채널(텔레그램)을 화면 소스에서 걷어내기 위한 경로다. 적재처가 sec_news 라
# 라벨·rule·veto 와 완전히 분리돼 있고(sql/49), 그래서 NEWS_ACTIVE_SOURCES 게이트의
# 대상이 아니다 — 끄면 뉴스 탭 헤드라인만 비고 나머지 파이프라인은 무영향.
SEC_NEWS_ENABLED = os.getenv('SEC_NEWS_ENABLED', '1') == '1'
# 한 사이클에 넘길 최대 페이지 수(1페이지 20건). 실측 증권 섹션은 하루 56페이지(~1,120건)라
# 30분 증분은 2~3페이지면 덮인다. 상한을 두는 이유는 파서가 깨져 '신규 0건'을 못 만들 때
# 56페이지를 끝까지 두드리는 폭주를 막기 위해서다(장 시작 직후 몰림은 8페이지로 충분).
SEC_NEWS_MAX_PAGES = int(os.getenv('SEC_NEWS_MAX_PAGES', '8'))
SEC_NEWS_SLEEP_SEC = float(os.getenv('SEC_NEWS_SLEEP_SEC', '0.3'))       # 페이지 간 간격

# ── 미매칭 뉴스 섹터·거시 라벨 (workers/sector_news_labeler.py) — 관측 전용 ──
# 사명이 안 잡혀 버려진 뉴스(content_skip no_match, 실측 수집률 34%)에 섹터·방향 라벨을 붙여
# 검정 표본을 만든다. **소비 경로 없음** — 점수·시드·veto 어디에도 들어가지 않는다(sql/45 주석).
# 끄면 라벨 축적만 멈추고 나머지 파이프라인은 무영향(이 라벨을 읽는 live 코드가 없다).
NEWS_SECTOR_ENABLED = os.getenv('NEWS_SECTOR_ENABLED', '1') == '1'
# 1회 LLM 호출에 넣는 헤드라인 수. 재료 지속성 판정(8종목)보다 크게 잡는 이유는 항목당 입력이
# 헤드라인 한 줄뿐이라서다(그쪽은 종목당 5일치 묶음). 너무 키우면 JSON 항목 누락이 는다.
NEWS_SECTOR_BATCH_SIZE = int(os.getenv('NEWS_SECTOR_BATCH_SIZE', '40'))
# 1회 실행 처리 상한. 하루 신규 유입이 ~800건(주말 포함)이라 여유를 두되, 백로그 일괄 소화는
# 수동 `--limit` 로 한다(스케줄 실행이 예상치 못하게 길어지지 않도록).
NEWS_SECTOR_MAX_ROWS = int(os.getenv('NEWS_SECTOR_MAX_ROWS', '1200'))

# 스코어/선정 로직 유효 시작일(YYYY-MM-DD, inclusive) — 이 날짜 이전은 구 로직이라
# 가중치 튜닝 백테스트 표본에서 제외한다. weight_tuner 가 분석 주 시작을 이 날짜로 클램프.
# (trading 쪽 레짐 게이트의 REGIME_MIN_DATE 와 같은 로직 변경을 가리킴 — 도메인 분리라 값만 맞춘다.)
# 2026-07-07: 거래대금 후보 풀 30→50 확대 + 테마 보너스 거래대금 상위 50 교집합 조건 반영.
SCORE_LOGIC_MIN_DATE = os.getenv('SCORE_LOGIC_MIN_DATE', '2026-07-07')

# Edge Ledger 왕복 거래비용(%) — 모든 가설 기대값은 이 값 차감 후로만 비교한다(README §5-2 비용 차감 원칙).
# 기본 0.25 = 세금 0.15 + 수수료 + 슬리피지 보수 추정. trading `fill` 실측치로 분기별 보정하고
# 보정 이력은 docs/plan/03-edge-ledger.md 에 기록한다.
EDGE_COST_PCT = float(os.getenv('EDGE_COST_PCT', '0.25'))

# 선정 레이어 모드(Phase 4). closing_bet 의 selected 판정·trade_signal 핸드오프에만 영향 —
# 점수 계산·저장·rank_no 는 모든 모드에서 불변(대조군 평가·프론트 표시용). trading 도메인 무변경.
#   legacy : 현행 점수 rank_no ≤ TRADED_TOP_N (기본값 — 데이터 게이트 통과 전까지 유지)
#   hybrid : live rule 매칭 우선 + 잔여 슬롯 점수순 (총 상한 TRADED_TOP_N)
#   rules  : live rule 매칭 합집합만(상한 초과 시 rule 기대값 순). 매칭 0 = 그날 무거래
# veto(감액·제외) rule 은 모드와 무관하게 선정 직전 적용. 롤백: 이 값을 legacy 로 되돌리면 즉시 원복.
EDGE_SELECTION_MODE = os.getenv('EDGE_SELECTION_MODE', 'legacy')

# 승격 게이트 정책 (2026-07-28 사용자 결정) — core.edge_policy.check_promotion 이 읽는다.
#   strict       : 유의성 2종 요구(ci_low>0 + t_days≥t분포임계값) + 판정 일정(발견→확인창)
#                  강제. 오탐 2.4% 이지만 **현재 44종 중 통과 0종**.
#   experimental : **t_days·판정 일정만** 면제. 남는 조건은 거래일≥10 · 평균수익>0 ·
#                  **ci_low>0**(안정성 하한) · 실행 가능성.
# 2026-08-04(사용자 결정): 자를 **절대 평균수익(mean_net) 하나로 통일**하고 같은 날 상대 비교
# 조건 2개(**초과수익·대조군 우위**)를 게이트에서 **제거**했다 — "평균보다 수익이 크지 않더라도
# 안정적으로 수익이 나면 그만". 초과수익은 계속 계산해 룰 상세 화면에만 표기한다.
# ⚠️ 그 결과 "그 기간 장이 오른 몫"을 걸러내는 자동 장치가 게이트에 없다(상승장에 등록된 rule 이
# 유리). 남은 방어선: 평균수익>0 · 거래일≥10 · 강등 감시 · 승격 시 관리자 승인(그때 상세 화면의
# 초과수익을 눈으로 확인) · 월 승격 상한.
# 같은 날 후속 결정(2026-08-04): 그렇게 두면 실효 조건이 '10거래일+ 평균 양수'뿐이고 **무엣지 룰의
# 통과 확률이 약 50%**(원래 22% 오탐을 막으려 월 상한을 둔 판에 문턱이 더 낮아짐)라, 과적합 방어가
# 월 상한 하나에 걸린다 → **ci_low>0(안정성 하한)을 experimental 면제에서 빼내 항상 요구**한다.
# 월 상한을 올리는 대안 대신 이쪽을 택했다("안정적으로 수익이 나면 그만"을 게이트가 직접 묻게).
# experimental 을 택한 근거: 현행 legacy(점수 top-N) 선정이 **무엣지가 아니라 실제로 나쁘다** —
# 실측(14거래일) 무작위 10종목이 legacy 를 이긴 비율 82.8%, 유니버스 평균 +0.071% vs legacy
# -0.150%, 점수 최하위 10종이 legacy 보다 +0.556%p. 챔피언이 마이너스면 도전자 오탐의 기대
# 비용이 0 에 가까우므로, 통계적 확신을 기다리는 것보다 올려보고 강등하는 편이 낫다는 판단.
# ⚠️ 대가: 사전등록 규율이 약해진다(탈락한 rule 을 기준 완화로 되살리는 셈). 강등 감지가
# 안전망이므로 최근 창 성적을 반드시 함께 감시한다(edge_policy.check_demotion, 최소 5거래일).
# 롤백: 이 값을 strict 로 되돌리면 게이트가 즉시 원복된다(이미 live 인 rule 은 강등 API 로 별도 처리).
EDGE_PROMO_POLICY = os.getenv('EDGE_PROMO_POLICY', 'experimental')

# 키움 데이터 서버 (별도 FastAPI, localhost) — core.kiwoom_client 가 호출
KIWOOM_BASE_URL = os.getenv('KIWOOM_BASE_URL', 'http://127.0.0.1:8001')

# 한국투자증권(KIS) Open API — 시장 탭 선물 시세(코스피200 야간선물) 조회용.
# core.kis_client.KisRestClient 가 사용하며, 토큰은 kis_token 테이블에 단일행 보관.
KIS_APP_KEY = os.getenv('KIS_APP_KEY', '')
KIS_SECRET_KEY = os.getenv('KIS_SECRET_KEY', '')
KIS_BASE_URL = os.getenv('KIS_BASE_URL', 'https://openapi.koreainvestment.com:9443')
# 코스피200 선물 근월물 단축코드(예: 'A01609' = 2026년 9월물). 보통은 비워두면
# kis_client.kospi200_front_month_code() 가 분기 만기 기준으로 근월물을 자동 산출한다.
# 강제 지정이 필요할 때만 .env 로 설정. 야간세션(KRX 야간거래)도 동일 근월물 코드를 쓴다.
KIS_KOSPI200_FUT_CODE = os.getenv('KIS_KOSPI200_FUT_CODE', '')
# KIS 실시간 WebSocket 접속 주소 (야간선물 실시간체결 H0MFCNT0 구독용).
KIS_WS_URL = os.getenv('KIS_WS_URL', 'ws://ops.koreainvestment.com:21000')

# DART 전자공시 OpenAPI — core.dart_client 가 공시검색(list.json)에 사용.
# 키 발급: https://opendart.fss.or.kr 회원가입 → 인증키 신청(무료, 일 20,000콜).
# 미설정이면 workers/disclosure_collector 가 조용히 종료하고, disc_* 라벨은 NULL 로 남는다
# (공시 veto rule 은 NULL=매칭 실패라 미개입 — 수집이 멎어도 선정이 망가지지 않는다).
DART_API_KEY = os.getenv('DART_API_KEY', '')
DART_BASE_URL = os.getenv('DART_BASE_URL', 'https://opendart.fss.or.kr')
