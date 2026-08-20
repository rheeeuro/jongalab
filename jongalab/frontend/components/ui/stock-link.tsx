import Link from "next/link";
import type { ReactNode } from "react";

const KR_CODE = /^\d{6}$/;

/** 화면에 온 종목코드를 링크에 쓸 6자리 코드로 정규화.
 *
 * 테마 구성종목은 `005930_AL`, 일부 응답은 `005930.KS` 처럼 접미사가 붙어 온다. 국장 6자리가
 * 아니면 **null** 이다 — 상시 페이지는 키움(국장 6자리) 조회라 해외 심볼로는 빈 화면이 된다.
 */
export function stockCode(raw?: string | null): string | null {
  const code = (raw ?? "").split("_")[0].split(".")[0].trim();
  return KR_CODE.test(code) ? code : null;
}

/** 종목명·종목코드 → 종목 상시 페이지(`/stocks/{code}`) 링크.
 *
 * **규칙**: 화면에 뜬 종목명·코드는 어디서든 눌러 종목 페이지로 갈 수 있다. 단
 * **날짜 문맥이 있는 자리**(그 날 리포트 목록·룰 매칭 이력)는 그 날짜 리포트 상세로 가고,
 * 거기서 다시 헤더 칩으로 상시 페이지로 넘어간다 — 한 자리에 목적지 둘을 두면 어디로 갈지 모른다.
 *
 * 코드가 국장 6자리가 아니면 링크를 만들지 않고 텍스트 그대로 둔다(깨진 링크를 만들지 않는다).
 * 밑줄은 점선이다 — 본문 링크(실선)와 구분되고, 표·칩 안에서도 글자 크기를 밀지 않는다.
 */
export function StockLink({
  code,
  children,
  className = "",
  title,
}: {
  code?: string | null;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  const resolved = stockCode(code);
  if (!resolved) return <span className={className}>{children}</span>;

  return (
    <Link
      href={`/stocks/${resolved}`}
      title={title ?? "종목 페이지 보기"}
      className={`underline decoration-slate-300 decoration-dotted underline-offset-2 transition-colors hover:text-indigo-600 dark:decoration-slate-600 dark:hover:text-indigo-400 ${className}`}
    >
      {children}
    </Link>
  );
}
