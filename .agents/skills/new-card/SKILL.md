---
name: new-card
description: 기존 디자인 패턴을 재사용해 모바일 우선 Recharts 대시보드 카드 컴포넌트를 만든다. 사용자가 새 카드, 차트 카드, 대시보드 위젯, 또는 Claude의 /new-card 작업을 요청할 때 사용한다.
---

# 대시보드 카드 생성

입력 이름은 PascalCase로 정규화하고 `jongalab/frontend/components/<Name>.tsx`에 만든다.

1. `StockReportCard.tsx`, `MentionTreemapCard.tsx`, `DailySummaryCard.tsx` 중 관련 카드 1~2개를 읽어 현재 컨테이너·패딩·다크모드 패턴을 파악한다.
2. 필요한 props 타입을 `jongalab/frontend/types/index.ts`에 추가하고 백엔드 응답 shape와 일치시킨다.
3. 작은 화면을 기본으로 구현하고 `sm:`·`md:`에서만 확장한다.
4. 데이터 없음, 로딩, 긴 텍스트와 좁은 폭을 처리한다.
5. 차트는 `recharts`, 아이콘은 `lucide-react`, 데이터 요청은 기존 `lib/api.ts` 래퍼를 사용한다.
6. 사용할 `app/*/page.tsx`에 연결하거나 정확한 연결 지점을 안내한다.
7. `cd jongalab/frontend && npx tsc --noEmit && npm run lint`를 실행하고 모바일 폭을 우선 확인한다.
