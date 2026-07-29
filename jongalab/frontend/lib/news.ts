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
