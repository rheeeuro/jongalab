// 종목 리포트 상세(`/reports/{date}/{ticker}`)의 **서술문 + 종합점수 표시** 공용 모듈.
//
// 화면 본문과 메타 description 이 같은 빌더를 쓴다(`lib/record` 와 같은 이유) — 표·게이지만 있으면
// "{종목명} 분석" 류 질의에 답이 될 본문이 없다(근거: docs/plan/seo/search-visibility.md).
// ⚠️ 여기서 판정·채점을 새로 하지 않는다 — 저장된 리포트 값과 서버가 준 `score_breakdown` 만
// 문장·막대에 끼운다(조건 판정은 서버 단일 소스).
import { hasFinalConsonant } from '@/lib/news';
import type { ScoreBreakdown, StockReport } from '@/types';

/** '은/는', '을/를' 처럼 받침에 따라 갈리는 조사 — 종목명은 받침이 있는 쪽·없는 쪽이 다 온다. */
/** 조사 선택 — 앞말 종성 유무로 갈린다(`삼성전자가` / `하이닉스가` · `삼성전자를` / `종목을`).
 *  화면 문구를 조립할 때 조사를 고정 문자열로 쓰면 종목마다 어색해진다. */
export function josa(word: string, withFinal: string, withoutFinal: string): string {
  const last = word.trim().slice(-1);
  return hasFinalConsonant(last) ? withFinal : withoutFinal;
}

/** 서술용 날짜 — 연도를 포함한다(화면 헤더의 `formatReportDate` 는 요일 중심이라 연도가 없다). */
function longDate(date: string): string {
  const [y, m, d] = date.split('-');
  if (!y || !m || !d) return date;
  return `${y}년 ${Number(m)}월 ${Number(d)}일`;
}

function signed(pct: number, digits = 2): string {
  return `${pct > 0 ? '+' : ''}${pct.toFixed(digits)}%`;
}

export function formatWon(v: number): string {
  return v.toLocaleString('ko-KR');
}

/** 거래대금·순매수 — 억 단위. */
export function formatBillion(v: number, withSign = false): string {
  const b = v / 1e8;
  const sign = withSign && b > 0 ? '+' : '';
  return `${sign}${b.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}억`;
}

/** 큰 원 금액 — 1조 이상은 `조`, 아래는 `억`. 시가총액·거래대금이 같이 놓이는 자리(종목 헤더)에서
 *  한쪽만 억으로 두면 `1,568.3조`와 `56,017억`이 나란히 서 자릿수를 눈으로 비교할 수 없다. */
export function formatWonCompact(v: number): string {
  if (v <= 0) return '-';
  const trillion = v / 1e12;
  if (trillion >= 1) {
    return `${trillion.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}조`;
  }
  return formatBillion(v);
}



/** 무상증자 권리락일(sql/50)의 갭 기준가 — 갭은 배정비율로 낮춰진 **권리락 기준가** 대비로 측정된다.
 *  리포트가를 그대로 쓰면 등락률과 앞뒤가 안 맞으므로 화면·서술문이 같이 이 값을 쓴다. */
export function gapBasePrice(r: StockReport): number {
  const ratio = r.gap_ex_rights_ratio ?? null;
  return ratio ? Math.round(r.current_price / (1 + ratio)) : r.current_price;
}

/** 다음 거래일 아침 결과 — 정규장(KRX)이 있으면 그쪽, 없으면 장 시작 전(NXT).
 *  이 우선순위를 화면마다 다르게 정하면 같은 리포트가 화면마다 다른 결과를 낸다. */
export function morningResult(r: StockReport): { venue: string; pct: number; price: number } | null {
  if (typeof r.gap_krx_pct === 'number' && r.gap_krx_price != null) {
    return { venue: '정규장', pct: r.gap_krx_pct, price: r.gap_krx_price };
  }
  if (typeof r.gap_nxt_pct === 'number' && r.gap_nxt_price != null) {
    return { venue: '장 시작 전(NXT)', pct: r.gap_nxt_pct, price: r.gap_nxt_price };
  }
  return null;
}

const GRADE_WORD: Record<string, string> = {
  S: 'S등급(가장 강한 수급)',
  A: 'A등급(관심권)',
  B: 'B등급(조건부 관찰)',
  C: 'C등급(수급 약함)',
  D: 'D등급(수급 기여 없음)',
};

/** 줄글 조각 — 숫자·이름만 굵게 낸다.
 *  회색 문단을 그대로 흘리면 UI 상 '글 덩어리'가 되고 아무 값도 눈에 걸리지 않는다. */
export type Rich = (string | { b: string })[];

export function richToText(parts: Rich): string {
  return parts.map((p) => (typeof p === 'string' ? p : p.b)).join('');
}

/** '왜 뽑혔나' 카드의 도입 문단 2개 — 어떤 종목인지 / 어떻게 뽑혔고 몇 점인지.
 *
 * 표·게이지가 못 하는 '한 흐름으로 읽기'만 담당한다. 근거 3축은 같은 카드의 아래 칸이 내므로
 * **여기서 근거를 나열하지 않는다**(같은 화면에 같은 말을 두 번 쓰지 않는다는 `/record` 규칙).
 * 다음 거래일 아침 결과는 `morningSentence` 가 결과 카드 안에서 낸다.
 */
export function reportLede(
  r: StockReport,
  date: string,
  ruleLabels: string[] = [],
): Rich[] {
  const name = r.stock_name;
  const sector = r.sector || '기타';

  const picked: Rich =
    ruleLabels.length > 0
      ? [
          '성적 검사를 통과한 전략 ',
          { b: `'${ruleLabels[0]}'` },
          ruleLabels.length > 1 ? ` 외 ${ruleLabels.length - 1}개` : '',
          '가 이 종목을 골랐어요.',
        ]
      : ['실험실 전략이 고른 게 아니라 그 날 종합 점수 순위로 뽑혔어요.'];

  // 문단은 **한 문단 한 가지**로 끊는다(무슨 종목 / 그 날 수치 / 어떤 전략이 골랐나 / 점수·수급).
  // 넓은 화면에서 남는 세로 공간을 문단 사이에 분산해 오른쪽 3축과 높이를 맞추므로,
  // 문단이 적으면 그 공백이 한 군데에 몰려 구멍처럼 보인다.
  return [
    [
      { b: `${name}(${r.stock_code})` },
      `${josa(name, '은', '는')} `,
      { b: longDate(date) },
      ' 종가랩이 종가베팅(장 마감 무렵에 사서 다음 거래일 아침에 파는 매매) 후보로 고른 ',
      `${sector} 종목이에요.`,
    ],
    [
      '리포트를 만든 시각(장 마감 무렵) 가격은 ',
      { b: `${formatWon(r.current_price)}원` },
      ', 당일 등락률은 ',
      { b: signed(r.change_pct) },
      ', 거래대금은 ',
      { b: `${formatBillion(r.trading_value)}원` },
      '이었어요.',
    ],
    picked,
    [
      '종합 점수는 ',
      { b: `${r.score.toFixed(0)}점` },
      '으로 그 날 후보 ',
      { b: `${r.rank_no}위` },
      '였고, 수급(기관·외국인 매수)은 ',
      { b: GRADE_WORD[r.supply_grade] ?? `${r.supply_grade}등급` },
      '이에요.',
    ],
  ];
}

/** 다음 거래일 아침 결과 한 문장 — 결과 카드 안에서 숫자 옆에 붙는다(아직이면 대기 문장). */
export function morningSentence(r: StockReport): Rich {
  const result = morningResult(r);
  if (!result) {
    return [
      '아직 나오지 않았어요. 다음 거래일 장이 열리면 실제 가격이 이 자리에 들어와요.',
    ];
  }
  const base = gapBasePrice(r);
  return [
    `다음 거래일 아침 ${result.venue} 첫 가격은 `,
    { b: `${formatWon(result.price)}원` },
    `으로, 리포트 시각 가격(${formatWon(base)}원)보다 `,
    {
      b: `${Math.abs(result.pct).toFixed(2)}% ${
        result.pct > 0 ? '높았어요' : result.pct < 0 ? '낮았어요' : '같았어요'
      }`,
    },
    '.',
  ];
}

/** 메타 description — 본문 리드와 같은 사실을 쓰되 스니펫 길이(≈150자)로 줄인다. */
export function reportMetaDescription(r: StockReport, date: string): string {
  const name = r.stock_name;
  const result = morningResult(r);
  const tail = result
    ? `다음 거래일 아침 첫 가격은 ${signed(result.pct)}였어요.`
    : '다음 거래일 아침 실제 결과까지 함께 볼 수 있어요.';
  return (
    `${name}${josa(name, '을', '를')} ${date.replace(/-/g, '.')} 종가베팅 후보로 고른 이유를 알려드려요. ` +
    `수급(기관·외국인 매수) ${r.supply_grade}등급, 종합 ${r.score.toFixed(0)}점(점수 ${r.rank_no}위)이었고, ${tail}`
  );
}

// ── 종합점수 게이지 ──────────────────────────────────────────────
// 항목 9~11개를 각각 막대로 내면 색도 줄도 읽히지 않아, **'왜 뽑혔나' 와 같은 3축**으로 묶어
// 게이지 하나에 색 구간으로 낸다. 색은 세 구간이 명도로도 갈리게 고른다 —
// 등락·손익 색(빨강/파랑)과 겹치면 점수 구간이 상승/하락으로 읽힌다.
export const SCORE_AXES = [
  {
    key: 'supply',
    label: '수급',
    hint: '기관·외국인이 얼마나, 며칠 연속 샀나',
    bar: 'bg-purple-800 dark:bg-purple-300',
    text: 'text-purple-800 dark:text-purple-300',
  },
  {
    key: 'technical',
    label: '기술',
    hint: '차트 위치·거래대금·당일 등락 구간',
    bar: 'bg-teal-600 dark:bg-teal-300',
    text: 'text-teal-700 dark:text-teal-300',
  },
  {
    key: 'material',
    label: '재료',
    hint: '테마·뉴스·유튜브 언급',
    bar: 'bg-amber-500 dark:bg-amber-300',
    text: 'text-amber-600 dark:text-amber-300',
  },
] as const;

export type ScoreAxisKey = (typeof SCORE_AXES)[number]['key'];

/** 서버 항목 key → 3축. 새 항목이 생기면 여기에 넣는다(빠지면 '기술'로 떨어진다). */
const AXIS_BY_ITEM: Record<string, ScoreAxisKey> = {
  supply: 'supply',
  supply_days: 'supply',
  prog_buy: 'supply',
  ma_aligned: 'technical',
  near_high: 'technical',
  trading_value: 'technical',
  change_band: 'technical',
  leader: 'technical',
  theme: 'material',
  content: 'material',
  news: 'material',
};

export interface ScoreAxis {
  key: ScoreAxisKey;
  label: string;
  hint: string;
  bar: string;
  text: string;
  points: number;
  maxPoints: number;
  /** 점수를 받은 항목 라벨(내림차순) — 색 구간이 무엇으로 채워졌는지 글로도 낸다. */
  earned: string[];
  /** 점수를 못 받은 항목 라벨 */
  missed: string[];
}

/** 서버가 준 항목별 점수를 3축으로 묶는다. 축 순서는 `SCORE_AXES` 고정(화면마다 바뀌지 않게). */
export function scoreAxes(breakdown: ScoreBreakdown): ScoreAxis[] {
  return SCORE_AXES.map((axis) => {
    const items = breakdown.items.filter(
      (i) => (AXIS_BY_ITEM[i.key] ?? 'technical') === axis.key,
    );
    const earned = items.filter((i) => i.points > 0).sort((a, b) => b.points - a.points);
    return {
      ...axis,
      points: items.reduce((s, i) => s + i.points, 0),
      maxPoints: items.reduce((s, i) => s + i.max_points, 0),
      earned: earned.map((i) => `${i.label} ${i.points.toFixed(0)}`),
      missed: items.filter((i) => i.points <= 0).map((i) => i.label),
    };
  }).filter((axis) => axis.maxPoints > 0);
}

/** 게이지 아래 한 문장 — 색 구간이 각각 몇 점인지 글로도 말한다(막대 색 단독 금지). */
export function scoreSentence(r: StockReport, axes: ScoreAxis[]): string {
  const parts = axes.map((a) => `${a.label} ${a.points.toFixed(0)}점`);
  return (
    `종합 ${r.score.toFixed(0)}점은 ${parts.join(' · ')}을 더해 100점 기준으로 바꾼 값이에요. ` +
    `점수는 순위를 매기는 데만 쓰고, 높다고 오른다는 뜻은 아니에요.`
  );
}
