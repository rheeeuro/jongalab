/**
 * 뉴스 헤드라인 표시 유틸.
 * 속보 채널 헤드라인은 "제목  https://기사URL" 형태가 많아,
 * 기사 URL은 링크로 쓰고 표시 텍스트에서는 제거한다 (모바일 가독성).
 */
const URL_RE = /https?:\/\/\S+/g;

export function splitHeadlineUrl(raw: string): {
  text: string;
  url: string | null;
} {
  const url = raw?.match(URL_RE)?.[0] ?? null;
  const text = (raw ?? "").replace(URL_RE, "").replace(/\s+/g, " ").trim();
  return { text: text || raw, url };
}

// 속보 채널 헤드라인은 발행처를 대괄호 말머리로 단다 — "[뉴시스] 현대차·기아, 美서…".
// 채널명(`단독 & 속보 뉴스 콜렉터`)은 어느 언론사인지 알려주지 않으므로, 말머리가 있으면
// 그쪽을 발행처로 쓴다. 네이버 소스는 말머리가 없고 channel_name 이 곧 언론사다.
const PUBLISHER_RE = /^\s*[[【]\s*([^\]】]{1,20})\s*[\]】]\s*/;

/** 헤드라인 1건을 표시 단위로 분해 — 발행처 / 제목 / 기사 URL. */
export function splitHeadlineMeta(
  raw: string,
  channelName?: string | null,
): { publisher: string | null; title: string; url: string | null } {
  const { text, url } = splitHeadlineUrl(raw ?? "");
  const m = text.match(PUBLISHER_RE);
  if (m) return { publisher: m[1].trim(), title: text.slice(m[0].length).trim(), url };
  return { publisher: channelName?.trim() || null, title: text, url };
}

/**
 * 뉴스량 배수 — 그 날 언급 건수 ÷ 직전 7일 일평균(하한 1).
 * 백엔드 `get_news_heat` 의 surprise 와 같은 식이다. 재료 목록(`/api/news/materials`)은
 * 배수를 미리 계산해 주지 않으므로 화면에서 같은 공식으로 맞춘다 — 식이 갈리면
 * 같은 종목이 목록과 사이드 랭킹에서 다른 배수로 보인다.
 */
export function newsSurprise(count: number, priorAvg?: number | null): number {
  return Math.round((count / Math.max(priorAvg ?? 0, 1)) * 10) / 10;
}

/** 뉴스량 배수의 화면 표기 — 강조 라벨 + 근거 한 줄. */
export type NewsHeatLabel = {
  /** 우측 강조 자리 — "뉴스 4배" · "첫 등장" · "평소 수준" */
  headline: string;
  /** 보조줄 근거 — "뉴스 41건 · 평소 10.0건/일" */
  detail: string;
  /** 색을 입힐 값인가(평소 수준·뉴스 없음은 회색으로 눕힌다) */
  emphasis: boolean;
};

/**
 * 배수를 사람이 읽는 문구로 — 세 화면(홈 카드·뉴스 랭킹·재료 목록)이 같은 말을 쓰게 한다.
 *
 * 표기 규칙이 셋으로 갈려 있던 걸(`평소의 5.0배`·`×5.0`·`평소 대비 ×5.0`) 하나로 모으면서
 * 두 가지를 고친다.
 *   1. **목적어를 붙인다** — "평소의 5배"는 주가·거래량으로도 읽힌다. "뉴스 5배"로 못 박는다.
 *   2. **기저가 없는 종목은 배수로 말하지 않는다** — 분모 하한이 1이라(백엔드 `_SURPRISE_FLOOR`)
 *      직전 7일 언급이 0건이면 배수가 곧 오늘 건수다. "3배 늘었다"가 아니라 "처음 떴다"이고,
 *      정렬이 배수순이라 이런 종목이 오히려 상단에 몰린다 — 가장 먼저 읽히는 줄이 가장 틀렸었다.
 *
 * 0 < 기저 < 1 구간은 하한 때문에 배수가 **실제보다 작게** 나오는데, 그대로 둔다.
 * 정렬(백엔드 surprise)과 같은 값을 써야 순위와 라벨이 어긋나지 않는다 — 보조줄의
 * `평소 0.3건/일` 이 실제 기저를 보여주므로 과장 방향으로 틀리는 일은 없다.
 *
 * 배수는 정수로 반올림한다. 하루 건수의 비율에 소수점 한 자리는 없는 정밀도다.
 */
export function newsHeatLabel(count: number, priorAvg?: number | null): NewsHeatLabel {
  const prior = priorAvg ?? 0;
  if (!count) return { headline: "뉴스 없음", detail: "뉴스 0건", emphasis: false };

  const base = `뉴스 ${count}건`;
  if (prior <= 0) {
    return { headline: "첫 등장", detail: `${base} · 최근 7일 없음`, emphasis: true };
  }

  const detail = `${base} · 평소 ${prior.toFixed(1)}건/일`;
  const m = newsSurprise(count, prior);
  if (m >= 9.5) return { headline: "뉴스 10배+", detail, emphasis: true };
  if (m >= 1.5) return { headline: `뉴스 ${Math.round(m)}배`, detail, emphasis: true };
  return { headline: "평소 수준", detail, emphasis: false };
}

/**
 * 재료 판정 근거를 사이트 사용자의 말로 — 저장된 문장에 섞인 내부 필드명을 치환한다.
 *
 * 이 문장은 리포트 상세에 그대로 노출되는데, 초기 판정 프롬프트가 근거를 '감사용'으로만
 * 규정해서 LLM 이 `next_milestone=0`·`amount_locked를 null로` 같은 내부 용어를 문장에 그대로
 * 썼다. 2026-07-29 프롬프트를 고쳐 신규 판정은 처음부터 한글로 오지만, **이미 저장된 행**은
 * 소급이 불가능하므로(LLM 재호출 비용·판정 재현성) 화면에서 읽을 수 있게 바꿔준다.
 *
 * 새 필드를 판정에 추가하면 이 표에도 넣는다 — 빠지면 사용자 화면에 영문 필드명이 샌다.
 */
const REASON_TERMS: [RegExp, string][] = [
  // 값이 붙은 형태를 먼저 — 필드명만 치환하면 '=0' 같은 꼬리가 남는다
  [/next_milestone\s*[=:]\s*(?:1|true)\b/gi, "다음 예정 사건 있음"],
  [/next_milestone\s*[=:]\s*(?:0|false)\b/gi, "다음 예정 사건 없음"],
  [/amount_locked\s*[=:]\s*(?:1|true)\b/gi, "수치 확정"],
  [/amount_locked\s*[=:]\s*(?:0|false)\b/gi, "수치 미확정"],
  // 값 없이 필드명만 언급한 경우
  [/next_milestone/gi, "다음 예정 사건"],
  [/amount_locked/gi, "수치 확정 여부"],
  [/driver_scope/gi, "재료 동인"],
  [/catalyst_type/gi, "재료 유형"],
  [/sentiment_score/gi, "재료 방향"],
  [/\bstage\b/gi, "진행 단계"],
  [/\bnull\b/gi, "판정 보류"],
];

/** 치환으로 앞말의 종성이 바뀌면 조사가 틀어진다("수치 확정를 판정 보류로"). 한국어 규칙대로 고친다. */
function hasFinalConsonant(syllable: string): boolean {
  const code = syllable.charCodeAt(0) - 0xac00;
  return code >= 0 && code <= 11171 && code % 28 !== 0;
}

function fixParticles(text: string): string {
  // 목적격(를→을)과 부사격(로→으로)만 고친다. '은/는' 은 건드리지 않는다 — 종성 없는 용언
  // 활용형('모은', '이은')까지 오작동시키는데, 치환으로 생기는 조사 오류에는 해당이 없다.
  return text
    .replace(/([가-힣])를/g, (m, ch) => (hasFinalConsonant(ch) ? `${ch}을` : m))
    // '로/으로' — 종성이 있으면 '으로'(단 ㄹ 종성은 '로')
    .replace(/([가-힣])로/g, (m, ch) =>
      hasFinalConsonant(ch) && (ch.charCodeAt(0) - 0xac00) % 28 !== 8 ? `${ch}으로` : m,
    );
}

export function humanizeMaterialReason(raw?: string | null): string | null {
  if (!raw) return null;
  const replaced = REASON_TERMS.reduce(
    (acc, [re, ko]) => acc.replace(re, ko),
    raw,
  );
  return replaced === raw ? raw : fixParticles(replaced);
}
