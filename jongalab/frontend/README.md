# jongalab/frontend — 대시보드 (Next.js)

jongalab 백엔드(`:8000`)의 리포트·종목·수급·테마·뉴스·콘텐츠를 보여 주는 **모바일 우선** 웹 대시보드.
Next.js 16 App Router + React 19 + Tailwind 4 + recharts.

> **모바일 우선이 1순위 규칙이다.** 이 대시보드는 모바일에서 자주 쓰인다. 모든 UI 는 작은 화면을
> 먼저 만족시키고 `sm:`/`md:` 로 확장한다. 데스크탑만 보고 끝내지 말 것.
>
> 이 README 는 **현재 화면 구성과 규칙**만 적는다. 재설계 경위·실측 수치·오독 사고는
> [`docs/history/frontend-ui.md`](../../docs/history/frontend-ui.md) 에 있다.
> 작업 규칙·가드레일은 루트 [`AGENTS.md`](../../AGENTS.md) 참고.

## 코드 구조
```
frontend/
├── app/             # App Router 페이지 (라우트 = 폴더) + app/api/* 로컬 라우트 핸들러
├── components/      # 재사용 UI·차트 카드 (recharts)
├── lib/api.ts       # fetch 래퍼 (API_BASE = :8000)
└── types/index.ts   # 타입 정의 — 백엔드 응답 shape 과 일치시킨다
```

## 규칙
- 차트는 recharts, 아이콘은 lucide-react, 스타일은 Tailwind 4 유틸리티.
- 새 카드 컴포넌트는 `/new-card` 스캐폴드를 사용한다.
- 타입은 `types/index.ts` 에 정의하고 백엔드 응답과 어긋나지 않게 유지한다.
- admin 변경(POST)은 클라이언트에서 직접 백엔드를 부르지 않고 **로컬 라우트 핸들러**(`app/api/*`)를
  거친다 — 서버에서 httpOnly 세션 쿠키를 백엔드 인증 헤더로 주입한다(`lib/api.adminAuthHeaders`).
- **조건 판정은 서버만 한다.** 화면은 백엔드가 준 판정값(`promo_eligible`·`promo_blockers`·
  `decision_stage` 등)을 렌더링만 한다 — 프론트에서 게이트 조건을 재추정하면 서버와 어긋난다.
- **용어 원칙**: 코드 용어(rule/candidate/predicate/CI)와 내부 식별자(`f5_prog_persistent` 류)를
  사용자 화면에 노출하지 않는다. 한국어 라벨·도움말은 `lib/edge.ts`(STATUS_LABEL·STAT_META·
  FAMILY_META·condText 컬럼 사전)에서 일괄 관리한다.
- **미검증 라벨에 손익 색(빨강/파랑)을 쓰지 않는다.** 관찰 전용 라벨이 매수 신호로 읽히면 안 된다 —
  배경은 중립 회색, 방향은 화살표로만 표시하고 title 에 '미검증'을 남긴다.

## 주요 화면

### `/news` — 뉴스 탭
**요약 타일 → 종목별 재료 → 헤드라인 스트림** 3층 + 사이드 '뉴스가 몰린 종목' 랭킹.
상단에서 **날짜를 이동**한다(`?date=YYYY-MM-DD`, 기본값은 **가장 최근 리포트일**).
- `news/MaterialBoard` — 단일 목록 + 필터(등급·선정·재료 유형 칩) / 정렬(뉴스 많은 순·등락률·후보 순위)
  / 검색. 기본 정렬은 뉴스 많은 순(배수). 행을 누르면 판정 근거가 있는 `/reports/{date}/{code}` 로.
- `news/NewsBuzzRail` — 후보 밖 종목까지 덮는 랭킹. 후보인 종목엔 '후보' 배지.
- `news/NewsStream` — 헤드라인 스트림(40건씩 '더 보기'). 기사 단위로 접히고 시세 기사는 기본 숨김.
- 지속성 라벨은 **candidate 표본(관찰 전용·미검증)** 이라는 안내를 접이식으로 두되, 핵심 문구는
  닫힌 상태에서도 보이게 남긴다.
- 데이터: `/api/news/materials` · `/api/news/heat?date=` · `/api/news/stream`(로컬 프록시 경유) ·
  `/api/stock-report/dates`(날짜 이동은 영업일 목록 위를 걷는다).

### 리포트 상세 / 종목 상세
- **뉴스 재료 섹션** — 등급 칩 + 사실 4축 + **판정 근거 문장**(`news_label_reason`) + 후속 재료 실현 일수.
  등급만 보여주면 화면에서 오탐 감사가 안 되므로 근거 문장을 반드시 노출한다.
  근거 문장은 `lib/news.humanizeMaterialReason` 가 내부 항목명을 한글로 치환한다(조사 교정 포함) —
  ⚠️ **판정 항목을 추가하면 이 치환표에도 넣는다**(빠지면 영문 필드명이 화면에 샌다).
- `TodayNews` — 시세보도 기사는 `details/summary` 로 접는다(서버 컴포넌트 유지, CSS-only 토글).
- **'룰 선정' 배지**(`StockReportCard` + 상세 헤더) — `rule_names` 가 있으면 실험실 룰이 **점수 순위와
  무관하게** 뽑은 종목이므로 배지 + `점수 N위` 를 함께 낸다. 룰로 가는 링크는 **리포트 상세에만**
  둔다(카드는 전체가 이미 `Link`).
- `components/MaterialBadge.tsx` — 연속/중립/소진/미판정 공통 칩 + `materialAxisLabels`(사실 축을
  사람 말로). `/news`·리포트 상세가 공유한다.

### `/lab` — 전략 실험실 (읽기 전용 공개)
서버 컴포넌트가 `getEdgeRules()` + rule 별 일별 시계열(+최신 매칭 1일치)을 실어 `EdgeBoard`(클라)로 내린다.
- 상태 그룹: 실전 적용 → 검증 중 → **측정용 기준선** → 판정 종결(접힘) → 종료(접힘).
  + 요약 스트립(`EdgeSummaryStrip`) + 접이식 도움말.
- **검증 중은 회색조+진행바(모의), 실전 적용은 컬러** — "모의 성적 ≠ 실탄"을 시각으로 구분한다.
- **판정 종결**(`lib/edge.isDecided`)은 최하단 접힘 섹션으로 모으고, 카드에 판정 결과(판정 탈락·재현
  실패)와 사유를 찍는다. '검증 중'·'검증 통과' 집계에서 제외한다.
- **측정용**(`lib/edge.isMeasurementOnly`, role=benchmark)은 검증→투입 파이프라인 밖이라 상태 배지·
  진행바·'검증 통과' 배지를 숨기고 별도 섹션·타일로 뺀다. 단 '종료'는 수명 정보라 표시한다.
- 카드 높이 통일: 검증 상태 슬롯(상태·진행바·설명 3줄)은 **항상** 렌더한다(설명 없으면 공백 한 줄).
- 카드를 누르면 `/lab/[name]` 상세(일별 막대차트·선정 조건·최근 매칭). 매칭 종목명은 **그 날짜의
  리포트 상세**로 링크하고, 반대 방향은 '룰 선정' 배지가 `/lab/[name]` 으로 되돌린다.
- 컴포넌트: `EdgeSummaryStrip` · `EdgeRuleCard` · `EdgeRuleDetailContent`.

### `/admin/edge-rules` — 전략 관리 (admin)
실전 투입(promote)/종료(retire)는 **여기서만** 한다(공개 화면엔 버튼 없음).
섹션: 검증 통과 대기 → 실전 적용 중 → 검증 중 → **측정용 기준선**(종료만 가능 — 기준선 교체는 의도적
수동 작업) → 종료(접힘). 확인 다이얼로그 후 `app/api/edge-rules/[id]`(admin 프록시) 호출 —
조건 미충족 409 사유를 그대로 표시한다(**게이트는 백엔드 단일 소스**).

## 개발 / 검증
```bash
npm run dev                       # :3000 dev 서버
npx tsc --noEmit && npm run lint  # 변경 후 필수 검증 (+ 모바일 폭 ≈375px 레이아웃 점검)
```
> 턴 종료 시 변경분은 `npm run build` 후 `jongalab-fe`(PM2)로 자동 반영된다(빌드 실패 시 알림).
