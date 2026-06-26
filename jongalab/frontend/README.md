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

## 개발 / 검증
```bash
npm run dev                       # :3000 dev 서버
npx tsc --noEmit && npm run lint  # 변경 후 필수 검증 (+ 모바일 폭 ≈375px 레이아웃 점검)
```
> 턴 종료 시 변경분은 `npm run build` 후 `jongalab-fe`(PM2)로 자동 반영된다(빌드 실패 시 알림).
> 작업 규칙·가드레일은 루트 [`AGENTS.md`](../../AGENTS.md) 참고.
