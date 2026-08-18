// `/record` 누적 성적을 **문장**으로 서술하는 공용 텍스트 빌더.
//
// 화면 본문과 메타 description 이 같은 문장을 쓴다. 숫자·차트만 있으면 "종가베팅 승률" 같은
// 질의에 답이 될 본문이 없어서 둔 것이다(근거: docs/plan/seo/search-visibility.md).
// 본문은 **한 문장**이다 — 요약 타일이 이미 같은 숫자를 보여주므로, 여러 문단을 쓰면 화면에서
// 중복이 되고 감춰 두면 검색엔진 전용 텍스트가 된다. 최고·최악일과 실체결 구간은 타일이 갖는다.
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

/** 화면 본문용 한 문장. 성적이 없으면 null(호출부가 문장 자체를 렌더하지 않는다). */
export function recordSentence(summary: RecordSummary | null): string | null {
  if (!summary || summary.picks === 0) return null;

  return (
    `${longDate(summary.from_date ?? '')}부터 ${longDate(summary.to_date ?? '')}까지 ${summary.days}거래일 동안 고른 ` +
    `${summary.picks}종목의 종가베팅 승률은 ${summary.win_rate.toFixed(1)}%` +
    `(${summary.wins}승 ${summary.losses}패${summary.flats ? ` ${summary.flats}보합` : ''}), ` +
    `장 마감 가격에 사서 다음 거래일 아침 첫 가격에 팔았다면 평균 수익률은 ${signed(summary.avg_gap_pct)}였어요.`
  );
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
