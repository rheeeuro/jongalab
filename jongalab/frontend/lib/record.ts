// `/record` 누적 성적을 **문장**으로 서술하는 공용 텍스트 빌더.
//
// 화면 본문과 메타 description 이 같은 문장을 쓴다. 숫자·차트만 있으면 "종가베팅 승률" 같은
// 질의에 답이 될 본문이 없어서 둔 것이다(근거: docs/plan/seo/search-visibility.md).
// ⚠️ 여기서 성적을 새로 계산하지 않는다 — `RecordSummary` 가 내려준 값만 문장에 끼운다.
import type { RecordSummary } from '@/types';

function signed(pct: number, digits = 2): string {
  return `${pct > 0 ? '+' : ''}${pct.toFixed(digits)}%`;
}

/** 본문 서술용 날짜 — 연도를 포함한다(`formatReportDate` 는 요일 중심이라 연도가 없다). */
function longDate(date: string): string {
  const [y, m, d] = date.split('-');
  if (!y || !m || !d) return date;
  return `${y}년 ${Number(m)}월 ${Number(d)}일`;
}

/** 화면 본문용 문단. 성적이 없으면 빈 배열(호출부가 섹션 자체를 렌더하지 않는다). */
export function recordNarrative(summary: RecordSummary | null): string[] {
  if (!summary || summary.picks === 0) return [];

  const paragraphs: string[] = [];

  paragraphs.push(
    `${longDate(summary.from_date ?? '')}부터 ${longDate(summary.to_date ?? '')}까지 ${summary.days}거래일 동안 고른 ` +
      `${summary.picks}종목의 종가베팅 승률은 ${summary.win_rate.toFixed(1)}%` +
      `(${summary.wins}승 ${summary.losses}패${summary.flats ? ` ${summary.flats}보합` : ''})예요. ` +
      `장 마감 가격에 사서 다음 거래일 아침 첫 가격에 팔았다고 하면 평균 수익률은 ${signed(summary.avg_gap_pct)}였어요.`,
  );

  // ⚠️ 실체결은 매매 경로 가동 이후 구간에만 있어 갭과 창이 다르다 — 같은 창인 것처럼 쓰면
  //    성적이 부풀려 읽힌다(RecordSummaryPanel 의 부제 규칙과 같은 이유).
  if (summary.avg_exec_ret !== null) {
    const windowDiffers = summary.exec_days !== summary.days;
    const window = windowDiffers
      ? `(${longDate(summary.exec_from_date ?? '')}~${longDate(summary.exec_to_date ?? '')}, ${summary.exec_days}거래일 ${summary.exec_samples}건)`
      : `(${summary.exec_samples}건)`;
    paragraphs.push(
      `실제로 사고팔았던 기간${window}의 평균 손익률은 ${signed(summary.avg_exec_ret)}예요` +
        `(수수료·세금을 빼기 전 값이에요).` +
        `${windowDiffers ? ' 자동 매매를 켠 뒤 기간만 세기 때문에 위 승률·평균 수익률과 기간이 달라요.' : ''}`,
    );
  }

  if (summary.best_day && summary.worst_day) {
    paragraphs.push(
      `가장 좋았던 날은 ${longDate(summary.best_day.date)} ${signed(summary.best_day.pct)}, ` +
        `가장 나빴던 날은 ${longDate(summary.worst_day.date)} ${signed(summary.worst_day.pct)}였어요. ` +
        `아래 달력에서 날짜마다 이겼는지 졌는지, 그날 고른 종목이 무엇인지 하나씩 볼 수 있어요.`,
    );
  }

  return paragraphs;
}

/** 메타 description — 성적이 없으면 고정 문구로 폴백한다. */
export function recordMetaDescription(summary: RecordSummary | null): string {
  if (!summary || summary.picks === 0) {
    return '종가랩이 매 거래일 고른 종목이 실제로 어땠는지 보여줘요. 날짜별 승패와 누적 승률·평균 수익률을 그대로 공개해요.';
  }
  return (
    `최근 ${summary.days}거래일 종가베팅 승률 ${summary.win_rate.toFixed(1)}%, ` +
    `평균 수익률 ${signed(summary.avg_gap_pct)}. 고른 ${summary.picks}종목을 장 마감 가격에 사서 ` +
    `다음 거래일 아침 첫 가격에 팔았다면 어땠을지, 날짜별로 전부 공개해요.`
  );
}
