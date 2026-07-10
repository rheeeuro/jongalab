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
