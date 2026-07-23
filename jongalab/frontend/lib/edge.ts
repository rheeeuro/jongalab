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
  live: '검증을 통과해 종목 선정에 반영되는 전략입니다.',
  candidate: '모의 채점으로만 성적을 쌓는 검증 단계입니다.',
  retired: '검증에 실패했거나 수명이 다해 더는 쓰지 않는 전략입니다.',
};

// ── 전략 유형(family = 도메인: 어떤 데이터를 보는가) ──
export const FAMILY_META: Record<string, { label: string; hint: string }> = {
  f1_news: { label: '뉴스 전략', hint: '새 뉴스가 아직 주가에 덜 반영된 종목을 노립니다' },
  f2_global: { label: '해외 연동 전략', hint: '밤사이 미국 시장 움직임을 아직 못 따라간 종목을 노립니다' },
  f3_nxt: { label: '야간시장 전략', hint: '저녁 NXT 거래에서 생긴 가격 차이를 노립니다' },
  f4_laggard: { label: '후발주 전략', hint: '섹터 1등이 급등한 뒤 아직 덜 오른 동종 종목을 노립니다' },
  f5_supply: { label: '수급 전략', hint: '기관·외국인 매수 흐름과 차트 구조에서 익일 연속성을 노립니다' },
  f6_ah: { label: '시간외 전략', hint: '장 마감 후 시간외단일가 반응에서 익일 연속성을 노립니다' },
  f8_value: { label: '가치·재무 전략', hint: '영업이익·밸류에이션 등 기업 재무 체력으로 종목을 거릅니다' },
  control: { label: '기준선', hint: '현행 점수 방식 — 새 전략이 이겨야 할 비교 기준입니다' },
  veto: { label: '위험 회피', hint: '수익용이 아니라 위험한 종목을 매수에서 빼는 용도입니다' }, // 구 데이터 폴백
};

export function familyMeta(family: string) {
  return FAMILY_META[family] ?? { label: family, hint: '' };
}

// ── 역할(role: 매매에서 어떻게 쓰이는가) — family(도메인)와 별개 축 ──
export const ROLE_META: Record<string, { label: string; badge: string; hint: string }> = {
  selector: {
    label: '매수',
    badge: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300',
    hint: '조건에 걸린 종목을 매수 후보로 고르는 수익 가설입니다',
  },
  veto: {
    label: '위험 회피',
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
    hint: '수익용이 아니라 위험한 종목을 매수에서 빼는 용도입니다',
  },
  benchmark: {
    label: '측정용',
    badge: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
    hint: '종목 선정에 쓰지 않고 성적 비교·측정에만 쓰는 기준선입니다',
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
  n: { label: '검증 횟수', help: '이 전략 조건에 걸린 종목을 채점한 누적 횟수(종목×일). 40회를 넘어야 적용을 검토합니다.' },
  n_days: { label: '검증 거래일', help: '검증 횟수가 쌓인 서로 다른 거래일 수. 같은 날 여러 종목은 시장 흐름에 함께 움직여 우연을 걸러내기 어렵기 때문에, 횟수와 별개로 서로 다른 거래일이 10일 이상 쌓여야 적용을 검토합니다.' },
  mean_net: { label: '평균 수익', help: '조건에 걸린 종목을 다음날 팔았다고 가정한 회당 평균 수익률. 세금·수수료 등 거래비용(0.25%)을 뺀 값입니다.' },
  win_rate: { label: '성공률', help: '수익이 난 비율. 단, 성공률보다 평균 수익이 더 중요합니다(한 번의 큰 손실이 여러 번의 작은 수익을 지울 수 있음).' },
  ci_low: { label: '보수적 수익', help: '운이 나쁜 경우까지 감안한 수익 하한 추정치(통계적 신뢰구간). 이 값이 0%보다 커야 "우연이 아니다"라고 보고 적용 조건을 충족합니다.' },
  worst_low_ret: { label: '최악 하락', help: '조건에 걸렸던 종목이 다음날 장중 기록한 가장 큰 하락률 — 이 전략의 최악의 날입니다.' },
} as const;

// ── 성과 측정 기준(exit_label) ──
export const EXIT_LABEL_TEXT: Record<string, string> = {
  next_open_ret: '다음날 시가에 판다고 가정',
  next_high_ret: '다음날 최고가 기준(이론상 최대)',
  next_low_ret: '다음날 최저가 기준(최악 가정)',
  next_close_ret: '다음날 종가까지 들고간다고 가정',
  nxt_open_ret: '다음날 아침 8시(NXT 프리마켓)에 판다고 가정',
  gap_nxt_pct: 'NXT 청산창 시각 기준',
  gap_krx_pct: 'KRX 청산창 시각 기준',
  exec_leg_ret: '청산창 시각 기준(NXT 19:50→08:03 / KRX 15:20→09:03)',
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

// 검증 통과 신호: 서버(core/edge_policy 게이트)가 계산해 stats.promo_eligible 에 저장한 값을
// 렌더링만 한다. 조건을 프론트에서 재계산하지 않는다(단일 소스).
export function isPromotionCandidate(rule: EdgeRule): boolean {
  // benchmark(측정용)는 게이트 전면 면제라 promo_eligible 이 늘 true — 실전 투입 대상이
  // 아니므로 '검증 통과' 배지·투입 대기 목록에서 제외한다(기준선 교체는 API 로 수동 수행).
  return rule.status === 'candidate' && rule.stats?.promo_eligible === true && rule.role !== 'benchmark';
}
