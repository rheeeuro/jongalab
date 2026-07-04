# jongalab/frontend — 대시보드 (Next.js)

jongalab 백엔드(`:8000`)의 리포트·종목·수급·테마·콘텐츠를 보여 주는 **모바일 우선** 웹 대시보드.
Next.js 16 App Router + React 19 + Tailwind 4 + recharts.

> **모바일 우선이 1순위 규칙이다.** 이 대시보드는 모바일에서 자주 쓰인다. 모든 UI 는 작은 화면을
> 먼저 만족시키고 `sm:`/`md:` 로 확장한다. 데스크탑만 보고 끝내지 말 것.

## 코드 구조
```
frontend/
├── app/             # App Router 페이지 (라우트 = 폴더)
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

## 주요 화면
- `/edge` — **전략 실험실**(Edge Ledger, 네비 라벨 "실험실"). **읽기 전용 공개 화면** — 서버
  컴포넌트가 `getEdgeRules()`+각 rule 일별 시계열(+최신 매칭 1일치)을 실어 `EdgeBoard`(클라)로
  내려준다. 상태 그룹(실전 적용→검증 중→종료 접힘) 카드 + 요약 스트립 + 상세 바텀시트(일별
  막대차트·선정 조건·최근 매칭) + 접이식 도움말("이 화면은 어떻게 보나요?").
  검증 중은 회색조+진행바(모의), 실전 적용은 컬러 — "모의 성적 ≠ 실탄"을 시각 구분.
  **용어 원칙**: 코드 용어(rule/candidate/predicate/CI)를 노출하지 않는다 — 한국어 라벨·도움말은
  전부 `lib/edge.ts`(STATUS_LABEL·STAT_META·FAMILY_META·condText 컬럼 사전)에서 일괄 관리.
  컴포넌트: `EdgeSummaryStrip`·`EdgeRuleCard`·`EdgeRuleDetail`.
- `/admin/edge-rules` — **전략 관리**(admin 탭). 실전 투입(promote)/종료(retire)는 **여기서만**
  한다(공개 화면엔 버튼 없음). 섹션: 검증 통과 대기 → 실전 적용 중 → 검증 중 → 종료(접힘).
  확인 다이얼로그 후 `app/api/edge-rules/[id]`(admin 프록시, httpOnly 쿠키 주입) 호출 —
  조건 미충족 409 사유를 그대로 표시(게이트는 백엔드 단일 소스). 목록은 `app/api/edge-rules`
  GET 프록시로 조회.

## 개발 / 검증
```bash
npm run dev                       # :3000 dev 서버
npx tsc --noEmit && npm run lint  # 변경 후 필수 검증 (+ 모바일 폭 ≈375px 레이아웃 점검)
```
> 턴 종료 시 변경분은 `npm run build` 후 `jongalab-fe`(PM2)로 자동 반영된다(빌드 실패 시 알림).
> 작업 규칙·가드레일은 루트 [`AGENTS.md`](../../AGENTS.md) 참고.
