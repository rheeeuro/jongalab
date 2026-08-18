// Edge Ledger UI 공용 헬퍼 — 카드·스트립·상세·관리 페이지가 공유하는 용어 사전/포맷/색.
//
// 화면 용어 원칙: 코드 용어(rule/candidate/predicate/CI)를 그대로 노출하지 않는다.
// 로직을 모르는 사용자도 읽을 수 있는 한국어 라벨 + 짧은 도움말을 여기서 일괄 관리한다
// (라벨을 바꿀 땐 이 파일만 고치면 모든 화면에 반영).
import type { EdgeRule } from '@/types';

// ── 상태: candidate/live/retired → 쉬운 한국어 ──
export const STATUS_LABEL: Record<string, string> = {
  live: '적용 중',
  candidate: '검증 중',
  retired: '종료',
};

export const STATUS_BADGE: Record<string, string> = {
  live: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  candidate: 'bg-slate-100 text-slate-600 dark:bg-slate-700/60 dark:text-slate-300',
  retired: 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500',
};

export const STATUS_HELP: Record<string, string> = {
  live: '성적 검사를 통과해서, 지금 종목을 고를 때 실제로 쓰고 있는 전략이에요.',
  candidate: '아직 실제로는 쓰지 않고, 성적만 따로 매겨보는 중이에요.',
  retired: '성적이 좋지 않거나 이제 잘 통하지 않아서, 더는 쓰지 않는 전략이에요.',
};

// ── 전략 유형(family = 도메인: 어떤 데이터를 보는가) ──
export const FAMILY_META: Record<string, { label: string; hint: string }> = {
  f1_news: { label: '뉴스 전략', hint: '새 뉴스가 나왔는데 주가는 아직 덜 오른 종목을 찾아요' },
  f2_global: { label: '해외 연동 전략', hint: '밤사이 미국 시장이 오른 만큼 아직 못 따라온 종목을 찾아요' },
  f3_nxt: { label: '야간시장 전략', hint: '저녁에 열리는 NXT 시장에서 생긴 가격 차이를 노려요' },
  f4_laggard: { label: '후발주 전략', hint: '업종 1등이 크게 오른 뒤, 같은 업종에서 아직 덜 오른 종목을 찾아요' },
  f5_supply: { label: '수급 전략', hint: '기관·외국인이 사 모으는 흐름과 차트 모양이 다음 날까지 이어질지 봐요' },
  f6_ah: { label: '시간외 전략', hint: '장이 끝난 뒤 시간외 거래 반응이 다음 날까지 이어질지 봐요' },
  f8_value: { label: '가치·재무 전략', hint: '회사가 돈을 잘 버는지, 주가가 싼지 같은 기초 체력으로 걸러요' },
  control: { label: '기준선', hint: '지금 쓰는 점수 방식 — 새 전략이 이겨야 하는 비교 상대예요' },
  veto: { label: '위험 회피', hint: '돈을 벌기 위한 게 아니라, 위험한 종목을 매수에서 빼는 용도예요' }, // 구 데이터 폴백
};

export function familyMeta(family: string) {
  return FAMILY_META[family] ?? { label: family, hint: '' };
}

// ── 역할(role: 매매에서 어떻게 쓰이는가) — family(도메인)와 별개 축 ──
export const ROLE_META: Record<string, { label: string; badge: string; hint: string }> = {
  selector: {
    label: '매수',
    badge: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300',
    hint: '조건에 걸린 종목을 매수 후보로 뽑아요',
  },
  veto: {
    label: '위험 회피',
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
    hint: '돈을 벌기 위한 게 아니라, 위험한 종목을 매수에서 빼요',
  },
  benchmark: {
    label: '측정용',
    badge: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
    hint: '종목을 고르는 데는 쓰지 않고, 성적을 비교하는 자로만 써요',
  },
};

export function roleMeta(role: string) {
  return ROLE_META[role] ?? ROLE_META.selector;
}

// ── 성적 지표: 쉬운 라벨 + 도움말 ──
// 승격 게이트의 최소 거래일 수 — core/edge_policy.PROMO_MIN_DAYS 미러(단일 소스는 백엔드).
// 같은 날 종목들은 시장 무브로 상관되므로, 검증 횟수(n)와 별개로 서로 다른 거래일이 이만큼
// 쌓여야 '검증 통과' 후보가 된다. 화면 진행 표기용(자격 판정은 stats.promo_eligible).
export const PROMO_MIN_DAYS = 10;

export const STAT_META = {
  n: { label: '검증 횟수', help: '이 전략에 걸린 종목의 성적을 매겨 본 총 횟수예요(종목 수 × 날짜 수). 참고용으로만 봐요 — 같은 날 뽑힌 종목들은 같이 오르고 같이 내리기 때문에, 실제 판단은 아래 검증 거래일로 해요.' },
  n_days: { label: '검증 거래일', help: '성적을 매긴 날이 며칠인지예요. 같은 날 종목 10개는 사실 하루치나 마찬가지라서, 서로 다른 날이 10일 넘게 모여야 실제로 쓸지 검토해요.' },
  mean_net: { label: '평균 수익', help: '조건에 걸린 종목을 다음 날 팔았다고 치면 한 번에 평균 몇 % 벌었는지예요. 세금·수수료(0.25%)는 이미 뺐어요.' },
  win_rate: { label: '성공률', help: '이익이 난 횟수의 비율이에요. 그래도 성공률보다 평균 수익이 더 중요해요 — 크게 한 번 잃으면 작게 여러 번 번 걸 다 지울 수 있으니까요.' },
  ci_low: { label: '보수적 수익', help: '운이 나빴을 경우까지 감안해서 위 평균 수익을 낮춰 잡은 값이에요. 이 값이 0%보다 커야 "운이 좋아서 번 게 아니다"라고 보고 실제로 쓸 수 있어요.' },
  t_days: { label: '날짜별 신뢰도', help: '이 성적을 얼마나 믿을 수 있는지 점수로 나타낸 거예요. 하루를 한 판으로 세서 계산해요 — 같은 날 걸린 종목들은 장이 좋으면 다 같이 오르니까, 종목 수로 세면 실제보다 훨씬 믿을 만해 보이기 때문이에요. 1.65 이상이어야 실제로 쓸지 검토해요(매수 전략만 봐요 — 위험 회피 전략은 큰 사고를 막는 게 목적이라 빼요).' },
  // ── 아래 초과 계열은 **적용 조건이 아니다**(2026-08-04). 상세 화면에서 "장이 좋아서 오른 건
  // 아닌지" 눈으로 확인하는 참고값이다 — 평균보다 덜 벌어도 안정적으로 수익이 나면 통과다.
  mean_exc: { label: '초과 수익(참고)', help: '같은 날 다른 후보 종목들의 평균보다 얼마나 더 벌었는지예요(그 전략이 고른 종목은 빼고 계산해요). 장이 좋아서 다 같이 오른 몫을 걷어낸 값이라, 종목을 고르는 실력을 보는 참고용이에요. 실제로 쓸지 정하는 조건에는 넣지 않아요.' },
  ci_low_exc: { label: '보수적 초과수익(참고)', help: '위 초과 수익도 운이 나빴을 경우까지 감안해 낮춰 잡은 값이에요. 참고용이고 실제로 쓸지 정하는 조건에는 넣지 않아요.' },
  t_days_exc: { label: '날짜별 신뢰도(초과, 참고)', help: '초과 수익을 하루 한 판으로 세서 계산한 신뢰도 점수예요. 참고용이고 실제로 쓸지 정하는 조건에는 넣지 않아요.' },
  worst_low_ret: { label: '최악 하락', help: '조건에 걸린 종목이 다음 날 장중에 가장 많이 떨어졌던 폭이에요 — 이 전략이 겪은 최악의 날이에요.' },
} as const;

// ── 성과 측정 기준(exit_label) ──
export const EXIT_LABEL_TEXT: Record<string, string> = {
  next_open_ret: '다음 날 아침 첫 가격(시가)에 팔았다고 계산',
  next_high_ret: '다음 날 가장 높았던 가격에 팔았다고 계산(가장 잘된 경우)',
  next_low_ret: '다음 날 가장 낮았던 가격에 팔았다고 계산(가장 나쁜 경우)',
  next_close_ret: '다음 날 장 끝날 때까지 들고 있었다고 계산',
  nxt_open_ret: '다음 날 아침 8시(NXT 시장)에 팔았다고 계산',
  gap_nxt_pct: 'NXT 시장에서 파는 시각 기준',
  gap_krx_pct: '한국거래소에서 파는 시각 기준',
  exec_leg_ret: '실제로 파는 시각 기준(NXT 19:50→08:03 / KRX 15:20→09:03)',
};

export function exitLabelText(label: string): string {
  return EXIT_LABEL_TEXT[label] ?? label;
}

// ── 선정 조건(predicate)을 사람이 읽는 문장으로 ──
const COL_LABELS: Record<string, string> = {
  change_pct: '당일 등락률(%)',
  trading_value: '거래대금',
  market_cap: '시가총액',
  supply_score: '수급 점수',
  supply_days: '연속 수급일',
  inst_net_buy: '기관 순매수(원)',
  frgn_net_buy: '외국인 순매수(원)',
  indv_net_buy: '개인 순매수(원)',
  prog_net_buy: '프로그램 순매수(원)',
  ma_aligned: '정배열',
  near_high: '신고가 근처',
  is_leader: '섹터 대장주',
  is_theme_stock: '테마주',
  sector: '업종',
  sector_rel_ret: '섹터 평균 대비 등락(%p)',
  sector_leader_chg: '섹터 1등 등락률(%)',
  news_count: '오늘 뉴스 수',
  news_unique_count: '고유 기사 수',
  news_pm_count: '오후 뉴스 수',
  news_first_today: '2주 만에 첫 뉴스',
  news_prior_avg: '평소 하루 뉴스 수',
  news_sentiment: '뉴스 호재 점수(0~100)',
  news_catalyst: '뉴스 재료 유형',
  nxt_gap_pct: '저녁 NXT 프리미엄(%)',
  nxt_listed: 'NXT 거래 가능',
  nxt_after_value: 'NXT 저녁 거래대금',
  selected: '점수 상위 10 선정',
  score: '종합점수',
  rank_no: '점수 순위',
  foreign_brokers_buying: '외국계 창구 매수 우위',
  afternoon_ret: '오후장(13시~) 상승률(%)',
  vol_ratio: '거래량 배율(÷20일 평균)',
  prog_buy_days: '최근 5일 중 프로그램 순매수일',
  first_seen: '2주 만에 첫 등장',
  theme_strength: '소속 테마 당일 등락률(%)',
  frgn_exhaust_rate: '외인 소진율(%)',
  frgn_exhaust_chg: '외인 소진율 변화(%p)',
  'market.sox_ret': '미국 반도체지수 등락(%)',
  'market.nq_fut_ret': '나스닥 선물 등락(%)',
  'market.spx_ret': 'S&P500 등락(%)',
  'market.vix': 'VIX(공포지수)',
  'market.usdkrw_ret': '원/달러 등락(%)',
  'market.kospi_ret': '코스피 등락(%)',
  'market.kosdaq_ret': '코스닥 등락(%)',
};

function colText(col: string): string {
  return COL_LABELS[col] ?? col;
}

export function condText(c: { col: string; op: string; value?: unknown }): string {
  const col = colText(c.col);
  const v = c.value;
  // 예/아니오형(0/1) 컬럼은 자연어로
  const isBoolCol = ['news_first_today', 'is_leader', 'nxt_listed', 'ma_aligned', 'near_high', 'is_theme_stock', 'selected', 'foreign_brokers_buying', 'first_seen'].includes(c.col);
  if (c.op === 'not_null') return `${col} 있음`;
  if (c.op === 'between' && Array.isArray(v)) return `${col} ${v[0]}~${v[1]}`;
  if (c.op === 'in' && Array.isArray(v)) return `${col}: ${v.join(', ')} 중 하나`;
  if (c.op === '==' && isBoolCol) return v ? col : `${col} 아님`;
  const OP_TEXT: Record<string, string> = { '>=': '≥', '<=': '≤', '>': '>', '<': '<', '==': '=', '!=': '≠' };
  return `${col} ${OP_TEXT[c.op] ?? c.op} ${v}`;
}

// ── 포맷/색 ──
export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;
}

export type Tone = 'up' | 'down' | 'flat';

export function retTone(v: number | null | undefined): Tone {
  if (v === null || v === undefined || v === 0) return 'flat';
  return v > 0 ? 'up' : 'down';
}

// 일 클러스터 t 문턱 — 백엔드 core/edge_policy.PROMO_MIN_DAY_T 와 같은 값(표기 전용).
export const PROMO_MIN_DAY_T = 1.65;

export function fmtT(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return v.toFixed(2);
}

// t 는 수익률이 아니라 신뢰도 점수 — 부호가 아니라 **문턱 통과 여부**로 색을 준다
// (retTone 을 쓰면 문턱에 못 미친 양수 t 가 '상승 빨강'으로 보여 통과한 것처럼 읽힌다).
export function dayTTone(v: number | null | undefined): Tone {
  if (v === null || v === undefined) return 'flat';
  return v >= PROMO_MIN_DAY_T ? 'up' : 'flat';
}

// 등락 색(한국 관례: 상승=빨강, 하락=파랑). Sparkline tone 과 일치.
export const TONE_TEXT: Record<Tone, string> = {
  up: 'text-rose-600 dark:text-rose-400',
  down: 'text-blue-600 dark:text-blue-400',
  flat: 'text-slate-500 dark:text-slate-400',
};

// recharts 막대 채움색(hex — Cell fill 은 클래스 불가).
export const TONE_FILL: Record<Tone, string> = {
  up: '#e11d48',
  down: '#2563eb',
  flat: '#94a3b8',
};

// 검증 진행도 — **표본 축적**만 나타낸다(거래일 기준). 게이트 통과 여부와 혼동하면 안 된다.
//
// 진행바에 게이트 조건을 섞지 않는다 — 게이트는 표본 외에 평균수익·유의성도 보고 그 조건은
// 백엔드만 안다. 섞으면 **"진행바는 꽉 찼는데 여전히 검증 중"** 이 된다
// (실제 오독 사고: docs/history/frontend-ui.md).
// → 진행바는 "언제 심사 대상이 되는가"(거래일 10일)만 보여주고, **무엇이 막고 있는지는 서버가
//   내려주는 stats.promo_blockers 를 그대로 렌더링**한다(프론트에서 재계산 금지).
export function verifyProgress(rule: EdgeRule): { n: number; nDays: number; progress: number } {
  const n = rule.stats?.n ?? 0;
  const nDays = rule.stats?.n_days ?? 0;
  return { n, nDays, progress: Math.min(100, Math.round((nDays / PROMO_MIN_DAYS) * 100)) };
}

// 게이트를 막고 있는 항목 — 서버(stats.promo_blockers)가 계산한 라벨을 화면 문구로 옮긴다.
// **판정은 서버가 하고 프론트는 표기만 바꾼다**(조건 재계산 금지). 매핑에 없는 값은 그대로 통과시켜
// 백엔드에 새 조건이 생겨도 화면이 조용히 빠뜨리지 않게 한다.
const BLOCKER_LABEL: Record<string, string> = {
  '거래일 부족': '검증 거래일 부족',
  '평균수익 미충족': '회당 평균 수익이 0% 이하',
  '신뢰구간 하한 미충족': '보수적 수익이 0% 이하',
  '일 클러스터 t 미충족': '날짜별 신뢰도 부족',
  '실익 미입증': '제외 효과 미입증',
  '선정 시점 실행 불가': '매수 시점에 못 쓰는 조건',
  '실행 불가': '매수 시점에 못 쓰는 조건',
  '표본 부족': '검증 횟수 부족',
  // 지금 게이트가 쓰지 않는 조건 — stats 는 평가기(평일 09:40)가 다시 구울 때까지 옛 값을
  // 담고 있을 수 있어, 그 값을 읽는 화면을 위해 라벨 매핑만 남긴다.
  '초과수익 미충족': '같은 날 다른 후보보다 못함(옛 조건)',
  '대조군 우위 미충족': '기준선보다 못함(옛 조건)',
};

export function promoBlockers(rule: EdgeRule): string[] {
  return (rule.stats?.promo_blockers ?? []).map((b) => BLOCKER_LABEL[b] ?? b);
}

// 적용 중인 승격 정책. experimental 은 통계 유의성·판정 일정을 면제한 실험 모드이므로
// 화면에 반드시 표시한다 — 유의성이 약한 rule 이 '적용 중'인 이유가 화면에 없으면 오해를 준다.
export function promoPolicy(rule: EdgeRule): 'strict' | 'experimental' | null {
  return rule.stats?.promo_policy ?? null;
}

export const POLICY_META: Record<'strict' | 'experimental', { label: string; help: string }> = {
  strict: {
    label: '엄격 심사',
    help: '성적이 운이 아니라는 걸 숫자로 확인하고, 다른 기간에서도 다시 되는지 본 다음에만 실제로 써요.',
  },
  experimental: {
    label: '실험 적용',
    help:
      '지금 쓰는 점수 방식이 종목을 아무렇게나 고르는 것보다도 못하다는 결과가 나와서, ' +
      '확실해질 때까지 기다리지 않고 벌 것 같은 전략을 먼저 써 보는 모드예요. ' +
      '성적이 나빠지면 바로 내려요. 그래도 한 번에 평균 수익이 0%보다 큰지, ' +
      '운이 나빴을 경우까지 감안한 수익도 0%보다 큰지, 성적을 매긴 날이 10일 넘게 쌓였는지는 똑같이 확인해요.',
  },
};

// ── 측정용(benchmark) 룰: '검증 → 실전 투입' 파이프라인 밖 ──
// 선정에 쓰지 않는 대조군·계측 도구라 승격 게이트가 전면 면제되고(promo_eligible 이 늘 true),
// rule_evaluator 도 승격/강등 알림에서 제외한다. 따라서 상태(검증 중/적용 중)·검증 진행도·
// '검증 통과' 표기를 화면에서 모두 숨긴다 — 통과할 관문이 없는데 진행률을 보여주면 오해만 준다.
// 이 판정을 쓰는 곳: 카드/상세/요약 타일/관리 페이지(모두 이 헬퍼 경유).
export function isMeasurementOnly(rule: EdgeRule): boolean {
  return rule.role === 'benchmark';
}

export const MEASURE_HELP =
  '성적을 비교하기 위한 기준선이에요. 종목을 고르는 데는 쓰지 않아서, 검사를 통과하거나 실제로 적용할 일도 없어요.';

// 검증 통과 신호: 서버(core/edge_policy 게이트)가 계산해 stats.promo_eligible 에 저장한 값을
// 렌더링만 한다. 조건을 프론트에서 재계산하지 않는다(단일 소스).
// **판정 일정(verdict) 조건을 프론트에서 따로 걸지 않는다** — 그 규율은 정책에 따라 적용 여부가
// 달라지고(experimental 은 면제) 서버의 promo_eligible 에 이미 반영돼 있다. 프론트에서 한 번 더
// 걸었더니 experimental 에서는 verdict 가 없어 **어떤 rule 도 '검증 통과'로 표시되지 않았다.**
export function isPromotionCandidate(rule: EdgeRule): boolean {
  return (
    rule.status === 'candidate' &&
    rule.stats?.promo_eligible === true &&
    !isMeasurementOnly(rule)
  );
}

// 판정 진행 상태 — "아직 심사 중"과 "이미 종결"을 구분하는 라벨. 종결된 candidate 를 그냥
// 'candidate' 로만 두면 계속 심사 중인 것처럼 읽힌다.
// **판정 기록(decision)이 있을 때만 표시한다.** 평가기(rule_evaluator)는 **정책과 무관하게**
// 판정 일정을 실행해 종결까지 기록하므로, 정책으로 표시 여부를 가르면 experimental 에서
// 종결된 rule 이 '심사 중'으로 보인다(게이지는 꽉 찬 채 목록 맨 위 = 승격을 기다리게 만드는
// 오해). 기록이 없으면 null 을 돌려 '발견 단계'가 영구 고정되는 것도 함께 피한다.
export const DECISION_LABEL: Record<string, { text: string; tone: 'wait' | 'pass' | 'fail' }> = {
  discovery: { text: '발견 단계', tone: 'wait' },
  confirming: { text: '확인창 진행', tone: 'wait' },
  // experimental 은 승격에서 확인창이 면제된다(백엔드 routers/edge_rule.py) — 그 정책에서
  // '확인창 진행'을 찍으면 아직 기다릴 게 남은 것처럼 읽힌다(실제론 바로 승격 가능).
  discovery_passed: { text: '발견 통과', tone: 'pass' },
  confirmed: { text: '확증 완료', tone: 'pass' },
  discovery_failed: { text: '판정 탈락', tone: 'fail' },
  confirm_failed: { text: '재현 실패', tone: 'fail' },
  exec_blocked: { text: '적용 불가', tone: 'fail' },
};

// 종료 사유 — '종료(retired)' 는 이유가 여러 가지다(통계 탈락 / 성적 붕괴 / **적용 불가**).
// 기본 문구(STATUS_HELP.retired)는 "검증에 실패했거나 수명이 다해"라 적용 불가 건에는 틀리다
// (통계는 멀쩡한데 매수 시점에 평가할 방법이 없어 내린 것). 기록된 사유가 있으면 그걸 쓴다.
export function retireReason(rule: EdgeRule): string | null {
  return rule.status === 'retired' ? (rule.decision?.retire_reason ?? null) : null;
}

export function decisionLabel(rule: EdgeRule): { text: string; tone: 'wait' | 'pass' | 'fail' } | null {
  if (rule.status !== 'candidate' || isMeasurementOnly(rule)) return null;
  const v = rule.decision?.verdict;
  if (v && DECISION_LABEL[v]) return DECISION_LABEL[v];
  if (rule.decision?.discovery?.pass) {
    // 정책은 서버가 stats.promo_policy 로 내려준 값을 읽기만 한다(조건 재계산 아님).
    return promoPolicy(rule) === 'experimental'
      ? DECISION_LABEL.discovery_passed
      : DECISION_LABEL.confirming;
  }
  return null;   // 판정 기록 없음 = 아직 아무 판정도 안 된 상태(표기 없음)
}

// 판정이 끝난(종결) candidate — 더 이상 심사하지 않으므로 목록에서 맨 아래로 내리고 카드에도
// '심사 중' 대신 판정 결과를 찍는다. 전이(retire)는 관리자 판단이라 status 는 candidate 그대로다.
export function isDecided(rule: EdgeRule): boolean {
  return (
    rule.status === 'candidate' &&
    !isMeasurementOnly(rule) &&
    Boolean(rule.decision?.decided_at || rule.decision?.verdict)
  );
}
