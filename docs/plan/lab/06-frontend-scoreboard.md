# Phase 5 — 가설 스코어보드 (대시보드 중심 화면 전환)

> 목표: 매일 보는 질문을 "오늘 뭘 샀나"에서 **"어떤 가설이 검증되고 있나"**로 바꾼다.
> 대상: `jongalab/frontend`(:3000). Phase 3 API 가 뜨면 병행 착수 가능.

## 1. 화면 설계 (모바일 우선 — 이 대시보드는 폰에서 본다)

### `/edge` 페이지 (신규)

```
[요약 스트립]  live N개 · candidate M개 · 이번 주 승격후보 K개        ← 가로 스크롤 스탯 타일
[Rule 카드 목록]  status 별 그룹(live → candidate → retired 접힘)
  ┌──────────────────────────────────────┐
  │ f3_nxt_gap_quality        [LIVE]     │  ← name + status 뱃지
  │ NXT 괴리 1~6% + 섹터 동조             │  ← description 요약
  │ n=52  기대값 +0.41%  승률 58%         │  ← 비용 차감 기준 명시
  │ CI하한 +0.08%  ▁▂▄▃▅▆▄▇  (60일)      │  ← 스파크라인(recharts)
  │ 표본 진행  ████████░░ 52/40           │  ← candidate 는 승격까지 진행바
  └──────────────────────────────────────┘
[카드 탭 → 상세 바텀시트]
  일별 성적 차트(막대: mean_net_ret, n 라벨) · predicate 조건 목록 ·
  최근 매칭 종목 목록(matched) · (admin) 승격/은퇴 버튼
```

- 카드 1열(모바일) → `sm:` 2열 → `lg:` 3열.
- **candidate 와 live 의 시각 구분을 강하게**: candidate 는 회색조+진행바(아직 돈 아님),
  live 는 컬러+실현손익 병기. "페이퍼 성적 ≠ 실탄 성적"이 UI 에서 헷갈리면 안 된다.
- Phase 4 이후: live 카드에 페이퍼 기대값 vs 실현 손익(rule 귀속) 병렬 표시 —
  둘의 괴리가 곧 슬리피지/집행 품질 지표다.

### 기존 화면 연결

- 홈의 종가베팅 카드: 선정 종목에 rule 뱃지(`f3` 등) 표시 (Phase 4 이후, rule_names 기반).
- 승격 후보 발생 시 기존 텔레그램 알림에 `/edge` 링크 포함.

## 2. 구현 항목

| 항목 | 파일 | 비고 |
|---|---|---|
| 타입 | `types/index.ts` — `EdgeRule`, `EdgeRuleDaily`, `EdgeRuleStats` | 백엔드 응답 shape 과 1:1 |
| API 래퍼 | `lib/api.ts` — `getEdgeRules()`, `getEdgeRuleDaily(id)`, admin `promoteRule/retireRule` | 기존 fetch 래퍼 패턴 |
| 페이지 | `app/edge/page.tsx` | 서버 컴포넌트 + 카드 목록 |
| 컴포넌트 | `components/EdgeRuleCard.tsx`, `EdgeRuleDetail.tsx`(바텀시트), `EdgeSummaryStrip.tsx` | recharts 스파크라인·막대, lucide 아이콘 |
| 내비게이션 | 기존 헤더/탭에 `/edge` 추가 | |

admin 버튼은 기존 admin 인증 흐름(쿠키) 재사용. 승격 실패(409) 시 서버가 주는 사유
(표본 부족 등)를 토스트로 그대로 표시 — 조건은 백엔드가 단일 소스.

## 3. 검증

1. `npx tsc --noEmit && npm run lint` 통과.
2. `:3000/edge` 200 + **모바일 뷰포트(375px) 우선** 확인: 카드 접힘·가로 스크롤 없음·
   바텀시트 동작.
3. rule 0개/통계 NULL(초기 상태) 빈 화면 처리 확인 — 배포 첫날은 데이터가 없다.
4. admin 승격 버튼: 조건 미충족 409 사유 표시, 성공 시 카드 상태 즉시 반영.

## 4. 완료 기준 (DoD)

- [ ] 폰에서 가설별 표본·기대값·상태·추이가 한 화면에 읽힌다.
- [ ] 승격/은퇴가 대시보드에서 수행 가능하고 조건 위반은 차단된다.
- [ ] 초기 빈 상태·결측이 깨지지 않는다.
- [ ] `frontend` 관련 README 갱신.
