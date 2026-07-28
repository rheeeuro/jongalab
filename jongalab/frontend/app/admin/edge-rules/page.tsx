"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, Rocket, Archive, ShieldCheck, Info } from "lucide-react";
import type { EdgeRule } from "@/types";
import {
  familyMeta,
  roleMeta,
  fmtPct,
  retTone,
  TONE_TEXT,
  STATUS_LABEL,
  STATUS_BADGE,
  STAT_META,
  isPromotionCandidate,
  isMeasurementOnly,
  ROLE_META,
  fmtT,
  dayTTone,
  decisionLabel,
} from "@/lib/edge";

/**
 * 전략 관리(admin) — 실전 투입/종료는 여기서만 한다.
 * 공개 화면(/lab)은 읽기 전용이고, 이 페이지는 admin 레이아웃(로그인) 뒤에 있으며
 * 실제 권한 검증은 백엔드가 한다(조건 미충족 승격은 서버가 409+사유로 거부, 강제 불가).
 */
export default function EdgeRulesAdminPage() {
  const [rules, setRules] = useState<EdgeRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/edge-rules", { cache: "no-store" });
      if (res.ok) setRules(await res.json());
    } catch (e) {
      console.error("전략 목록 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(rule: EdgeRule, action: "promote" | "retire") {
    const confirmText =
      action === "promote"
        ? `'${rule.title ?? rule.name}' 전략을 실전 매매에 투입합니다.\n다음 매수 사이클부터 실제 주문에 반영됩니다. 진행할까요?`
        : `'${rule.title ?? rule.name}' 전략을 종료합니다.\n${rule.status === "live" ? "실전 매매에서 즉시 빠집니다. " : ""}진행할까요?`;
    if (!window.confirm(confirmText)) return;

    setActing(rule.id);
    setMsg(null);
    try {
      const res = await fetch(`/api/edge-rules/${rule.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg({ type: "error", text: data.detail || "처리에 실패했습니다." });
      } else {
        setMsg({
          type: "success",
          text:
            action === "promote"
              ? `실전 투입 완료. ${data.worst_low_ret !== null && data.worst_low_ret !== undefined ? `참고 — 이 전략의 ${STAT_META.worst_low_ret.label}: ${fmtPct(data.worst_low_ret)} (손절 정책과 비교해 보세요)` : ""}`
              : "전략을 종료했습니다.",
        });
        load();
      }
    } catch {
      setMsg({ type: "error", text: "서버에 연결할 수 없습니다." });
    } finally {
      setActing(null);
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </main>
    );
  }

  // 측정용(기준선)은 검증→투입 파이프라인 밖 — 투입 대기/적용 중/검증 중 어디에도 넣지 않고
  // 별도 섹션에서 종료만 가능하게 한다(기준선 교체는 의도적 수동 작업).
  const measured = rules.filter((r) => isMeasurementOnly(r) && r.status !== "retired");
  const pipeline = rules.filter((r) => !isMeasurementOnly(r));
  const ready = pipeline.filter(isPromotionCandidate);
  const live = pipeline.filter((r) => r.status === "live");
  const verifying = pipeline.filter((r) => r.status === "candidate" && !isPromotionCandidate(r));
  const retired = rules.filter((r) => r.status === "retired");

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      <header className="space-y-1">
        <h1 className="text-lg font-extrabold text-slate-900 sm:text-xl dark:text-slate-100">전략 관리</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          검증을 통과한 전략을 실전에 투입하거나, 성적이 나빠진 전략을 종료합니다.
        </p>
      </header>

      {/* 규율 안내 */}
      <div className="flex items-start gap-2 rounded-2xl border border-slate-100 bg-slate-50/60 px-4 py-3 text-xs leading-relaxed text-slate-500 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-400">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          실전 투입 조건(검증 40회 이상 · 보수적 수익 &gt; 0% · 기준선보다 좋은 성적 · 매수 시점에
          실행 가능한 조건)은 <b>서버가 검증</b>하며, 미충족 시 사유와 함께 거부됩니다(강제 불가).
          과도한 투입을 막기 위해 실전 투입은 <b>월 2개까지</b>입니다.
        </span>
      </div>

      {msg && (
        <p
          className={`rounded-xl px-4 py-2.5 text-sm ${
            msg.type === "error"
              ? "bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400"
              : "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
          }`}
        >
          {msg.text}
        </p>
      )}

      {/* ① 검증 통과 — 실전 투입 대기 */}
      <Section
        title="검증 통과 — 실전 투입 대기"
        icon={<ShieldCheck className="h-4 w-4 text-rose-500" />}
        empty="아직 검증을 통과한 전략이 없습니다. 검증 중 전략이 조건을 충족하면 텔레그램으로 알려드립니다."
        rules={ready}
        render={(r) => (
          <ActionButton
            label="실전 투입"
            icon={<Rocket className="h-3.5 w-3.5" />}
            busy={acting === r.id}
            onClick={() => act(r, "promote")}
            variant="primary"
          />
        )}
      />

      {/* ② 실전 적용 중 */}
      <Section
        title="실전 적용 중"
        empty="실전 적용 중인 전략이 없습니다."
        rules={live}
        render={(r) => (
          <ActionButton
            label="종료"
            icon={<Archive className="h-3.5 w-3.5" />}
            busy={acting === r.id}
            onClick={() => act(r, "retire")}
            variant="danger"
          />
        )}
      />

      {/* ③ 검증 중 */}
      <Section
        title="검증 중 (모의 채점)"
        empty="검증 중인 전략이 없습니다."
        rules={verifying}
        render={(r) => (
          <ActionButton
            label="종료"
            icon={<Archive className="h-3.5 w-3.5" />}
            busy={acting === r.id}
            onClick={() => act(r, "retire")}
            variant="ghost"
          />
        )}
      />

      {/* ④ 측정용 기준선 — 검증/투입 대상이 아니라 성적만 보고, 교체 시에만 종료 */}
      {measured.length > 0 && (
        <Section
          title={`${ROLE_META.benchmark.label} 기준선 (선정에 미반영)`}
          empty=""
          rules={measured}
          render={(r) => (
            <ActionButton
              label="종료"
              icon={<Archive className="h-3.5 w-3.5" />}
              busy={acting === r.id}
              onClick={() => act(r, "retire")}
              variant="ghost"
            />
          )}
        />
      )}

      {/* ⑤ 종료됨 (접힘) */}
      {retired.length > 0 && (
        <details>
          <summary className="cursor-pointer list-none text-sm font-bold text-slate-400">
            종료된 전략 ({retired.length})
          </summary>
          <div className="mt-3 space-y-2">
            {retired.map((r) => (
              <RuleRow key={r.id} rule={r} />
            ))}
          </div>
        </details>
      )}
    </main>
  );
}

function Section({
  title,
  icon,
  empty,
  rules,
  render,
}: {
  title: string;
  icon?: React.ReactNode;
  empty: string;
  rules: EdgeRule[];
  render: (r: EdgeRule) => React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-2.5 flex items-center gap-1.5 text-sm font-bold text-slate-700 dark:text-slate-200">
        {icon}
        {title}
        <span className="rounded-full bg-slate-100 px-1.5 text-xs text-slate-500 dark:bg-slate-800">
          {rules.length}
        </span>
      </h2>
      {rules.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-5 text-center text-xs text-slate-400 dark:border-slate-800">
          {empty}
        </p>
      ) : (
        <div className="space-y-2">
          {rules.map((r) => (
            <RuleRow key={r.id} rule={r} action={render(r)} />
          ))}
        </div>
      )}
    </section>
  );
}

function RuleRow({ rule, action }: { rule: EdgeRule; action?: React.ReactNode }) {
  const s = rule.stats;
  const fam = familyMeta(rule.family);
  const role = roleMeta(rule.role);
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-slate-100 bg-white p-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800 dark:bg-[#1c1c22]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-slate-900 dark:text-slate-100">{rule.title ?? rule.name}</span>
          {/* 측정용은 검증/투입 대상이 아니라 상태를 숨긴다(단, '종료'는 수명 정보라 유지) */}
          {(!isMeasurementOnly(rule) || rule.status === "retired") && (
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${STATUS_BADGE[rule.status]}`}>
              {STATUS_LABEL[rule.status]}
            </span>
          )}
          <span className="text-[10px] font-semibold text-slate-400">{fam.label}</span>
          <span className={`rounded-full px-1.5 py-px text-[10px] font-bold ${role.badge}`} title={role.hint}>
            {role.label}
          </span>
          {/* 판정 단계 — '아직 심사 중'과 '이미 탈락'을 구분한다. 탈락 rule 을 candidate 로만
              두면 계속 심사 중인 것처럼 읽혀 승격을 기다리게 된다(sql/39 판정 일정). */}
          {(() => {
            const d = decisionLabel(rule);
            if (!d) return null;
            const tone = d.tone === "pass"
              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
              : d.tone === "fail"
              ? "bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
              : "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300";
            return (
              <span className={`rounded-full px-1.5 py-px text-[10px] font-bold ${tone}`}
                    title={rule.decision?.confirm?.reasons?.[0] ?? rule.decision?.discovery?.reasons?.[0] ?? undefined}>
                {d.text}
              </span>
            );
          })()}
          <span className="font-mono text-[10px] text-slate-400">{rule.name}</span>
        </div>
        <p className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{rule.description}</p>
        {s && s.n > 0 ? (
          <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
            {STAT_META.n.label} <b className="tabular-nums text-slate-700 dark:text-slate-200">{s.n}</b>
            {" · "}
            {STAT_META.mean_net.label}{" "}
            <b className={`tabular-nums ${TONE_TEXT[retTone(s.mean_net)]}`}>{fmtPct(s.mean_net)}</b>
            {" · "}
            {STAT_META.ci_low_exc.label}{" "}
            <b className={`tabular-nums ${TONE_TEXT[retTone(s.ci_low_exc)]}`}>{fmtPct(s.ci_low_exc)}</b>
            {/* 초과 계열(유니버스 자기제외) — selector 승격 게이트가 보는 값. 원시 평균만
                보면 통과처럼 보이는 후보를 걸러내므로 승격 판단 화면에는 반드시 함께 뜬다
                (제외 규칙은 이 게이트가 면제라 미표기). */}
            {rule.role !== "veto" && (
              <>
                {" · "}
                {STAT_META.t_days_exc.label}{" "}
                <b className={`tabular-nums ${TONE_TEXT[dayTTone(s.t_days_exc)]}`}>{fmtT(s.t_days_exc)}</b>
              </>
            )}
            {s.worst_low_ret !== null && (
              <>
                {" · "}
                {STAT_META.worst_low_ret.label}{" "}
                <b className={`tabular-nums ${TONE_TEXT[retTone(s.worst_low_ret)]}`}>{fmtPct(s.worst_low_ret)}</b>
              </>
            )}
          </p>
        ) : (
          <p className="mt-1.5 text-xs text-slate-400">아직 검증 기록 없음</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

function ActionButton({
  label,
  icon,
  busy,
  onClick,
  variant,
}: {
  label: string;
  icon: React.ReactNode;
  busy: boolean;
  onClick: () => void;
  variant: "primary" | "danger" | "ghost";
}) {
  const styles = {
    primary: "bg-emerald-600 text-white hover:bg-emerald-700",
    danger: "border border-rose-200 text-rose-600 hover:bg-rose-50 dark:border-rose-500/30 dark:hover:bg-rose-500/10",
    ghost: "border border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800",
  } as const;
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`flex w-full items-center justify-center gap-1.5 rounded-xl px-4 py-2.5 text-xs font-bold transition-colors disabled:opacity-50 sm:w-auto ${styles[variant]}`}
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
      {label}
    </button>
  );
}
