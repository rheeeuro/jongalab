import { Fragment } from "react";
import type { Rich } from "@/lib/report";

/** 줄글 안의 숫자·이름만 굵게 낸다 — 회색 문단이 통째로 '글 덩어리'로 보이지 않게 하는 최소 장치. */
export function RichText({ parts }: { parts: Rich }) {
  return (
    <>
      {parts.map((p, i) => (
        <Fragment key={i}>
          {typeof p === "string" ? (
            p
          ) : (
            <strong className="font-bold text-slate-900 dark:text-slate-100">
              {p.b}
            </strong>
          )}
        </Fragment>
      ))}
    </>
  );
}
