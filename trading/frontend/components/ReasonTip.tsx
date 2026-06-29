"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * 미체결 사유 툴팁 — 상태 텍스트("거부"/"스킵")에 붙는다.
 * 데스크탑은 hover, 모바일은 탭으로 연다(터치에서 합성 mouseenter 가 토글을 깨지 않도록 pointerType 으로 분기).
 * 툴팁은 portal 로 body 에 렌더해 거래내역 행의 흐림(opacity/grayscale) 영향을 받지 않고 또렷하게 뜬다.
 */
export default function ReasonTip({ label, reason }: { label: string; reason: string }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const el = triggerRef.current;
    if (el) {
      const r = el.getBoundingClientRect();
      setPos({ top: r.bottom + 6, left: r.left });
    }
    // 바깥 클릭/스크롤/리사이즈 시 닫기 (스크롤 중 위치 어긋남 방지)
    const onDocClick = (e: MouseEvent) => {
      if (triggerRef.current && e.target instanceof Node && triggerRef.current.contains(e.target)) return;
      setOpen(false);
    };
    const close = () => setOpen(false);
    document.addEventListener("click", onDocClick);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("click", onDocClick);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={`사유: ${reason}`}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        onPointerEnter={(e) => {
          if (e.pointerType === "mouse") setOpen(true);
        }}
        onPointerLeave={(e) => {
          if (e.pointerType === "mouse") setOpen(false);
        }}
        className="underline decoration-dotted underline-offset-2"
      >
        {label}
      </button>
      {open &&
        pos &&
        typeof document !== "undefined" &&
        createPortal(
          <span
            role="tooltip"
            style={{ position: "fixed", top: pos.top, left: pos.left, maxWidth: "min(75vw, 320px)" }}
            className="z-50 block w-max rounded-md bg-slate-700 px-2.5 py-1.5 text-xs font-medium leading-snug text-white shadow-lg dark:bg-slate-600"
          >
            {reason}
          </span>,
          document.body,
        )}
    </>
  );
}
