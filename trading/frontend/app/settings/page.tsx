"use client";

import { useState, useEffect } from "react";
import { Save, RotateCcw, Loader2, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

interface RiskConfig {
  MAX_ORDERS_PER_DAY: number;
  MAX_NOTIONAL_PER_NAME: number;
  MAX_DAILY_LOSS: number;
  MAX_POSITIONS: number;
}

const FIELDS: {
  key: keyof RiskConfig;
  label: string;
  unit: string;
  currency?: boolean;
}[] = [
  { key: "MAX_ORDERS_PER_DAY", label: "일일 최대 주문수", unit: "건" },
  { key: "MAX_NOTIONAL_PER_NAME", label: "종목당 최대 금액", unit: "원", currency: true },
  { key: "MAX_DAILY_LOSS", label: "일일 최대 손실", unit: "원", currency: true },
  { key: "MAX_POSITIONS", label: "동시 보유 종목수", unit: "개" },
];

function formatCurrency(value: number): string {
  if (value >= 100_000_000) return `${(value / 100_000_000).toLocaleString()}억`;
  if (value >= 10_000) return `${(value / 10_000).toLocaleString()}만`;
  return value.toLocaleString();
}

interface BlockItem {
  stk_cd: string;
  reason: string | null;
}

export default function RiskSettingsPage() {
  const [config, setConfig] = useState<RiskConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [blocklist, setBlocklist] = useState<BlockItem[]>([]);
  const [blockText, setBlockText] = useState("");
  const [blockSaving, setBlockSaving] = useState(false);

  useEffect(() => {
    fetchConfig();
    fetchBlocklist();
  }, []);

  async function fetchConfig() {
    setLoading(true);
    try {
      const res = await fetch("/api/risk-config");
      if (res.ok) setConfig(await res.json());
    } catch (e) {
      console.error("설정 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  }

  async function fetchBlocklist() {
    try {
      const res = await fetch("/api/blocklist");
      if (res.ok) {
        const items: BlockItem[] = await res.json();
        setBlocklist(items);
        setBlockText(items.map((i) => i.stk_cd).join(", "));
      }
    } catch (e) {
      console.error("blocklist 로드 실패:", e);
    }
  }

  async function handleBlockSave() {
    setBlockSaving(true);
    setMessage(null);
    // 기존 사유 보존: 코드별 reason 맵
    const reasons = new Map(blocklist.map((i) => [i.stk_cd, i.reason]));
    const codes = blockText
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const items = codes.map((stk_cd) => ({ stk_cd, reason: reasons.get(stk_cd) ?? null }));
    try {
      const res = await fetch("/api/blocklist", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      if (res.ok) {
        const updated: BlockItem[] = await res.json();
        setBlocklist(updated);
        setBlockText(updated.map((i) => i.stk_cd).join(", "));
        setMessage({ type: "success", text: "제외 목록이 저장되었습니다." });
      } else {
        setMessage({ type: "error", text: "제외 목록 저장 실패." });
      }
    } catch {
      setMessage({ type: "error", text: "서버에 연결할 수 없습니다." });
    } finally {
      setBlockSaving(false);
      setTimeout(() => setMessage(null), 3000);
    }
  }

  async function handleSave() {
    if (!config) return;
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/risk-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        setConfig(await res.json());
        setMessage({ type: "success", text: "저장되었습니다. 다음 집행부터 적용됩니다." });
      } else {
        setMessage({ type: "error", text: "저장에 실패했습니다." });
      }
    } catch {
      setMessage({ type: "error", text: "서버에 연결할 수 없습니다." });
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(null), 3000);
    }
  }

  function updateField(key: keyof RiskConfig, value: number) {
    if (!config) return;
    setConfig({ ...config, [key]: value });
  }

  if (loading || !config) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      {/* 헤더 */}
      <div className="mb-5">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
        >
          <ArrowLeft className="h-4 w-4" />
          대시보드
        </Link>
        <h1 className="mt-2 text-xl font-bold sm:text-2xl">리스크 설정</h1>
        <p className="mt-1 text-sm text-slate-500">한도 초과 시 주문이 차단됩니다.</p>
      </div>

      {/* 화면 테마 */}
      <div className="mb-5 overflow-hidden rounded-xl border border-slate-200 bg-white p-1.5 dark:border-slate-800 dark:bg-slate-900">
        <ThemeToggle variant="row" />
      </div>

      {/* 토스트 */}
      {message && (
        <div
          className={`mb-4 rounded-lg px-4 py-3 text-sm font-medium ${
            message.type === "success"
              ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
              : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
          }`}
        >
          {message.text}
        </div>
      )}

      {/* 폼 카드 — 모바일 우선 세로 배치 */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {FIELDS.map((f) => (
            <div key={f.key} className="flex flex-col gap-2 px-4 py-4 sm:flex-row sm:items-center">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 sm:w-48 sm:shrink-0">
                {f.label}
              </label>
              <div className="flex flex-1 items-center gap-2">
                <input
                  type="number"
                  inputMode="numeric"
                  value={config[f.key]}
                  onChange={(e) => updateField(f.key, Number(e.target.value))}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
                <span className="w-20 shrink-0 text-right text-xs text-slate-400">
                  {f.currency ? formatCurrency(config[f.key]) : f.unit}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 액션 — 모바일에서 풀폭 터치 타깃 */}
      <div className="mt-5 flex gap-2">
        <button
          onClick={fetchConfig}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800"
        >
          <RotateCcw className="h-4 w-4" />
          되돌리기
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          저장
        </button>
      </div>

      {/* 매수 제외 목록 (blocklist) */}
      <div className="mt-8">
        <h2 className="text-base font-semibold">매수 제외 종목</h2>
        <p className="mt-1 mb-2 text-sm text-slate-500">
          여기 등록한 종목은 자동매매가 매수하지 않습니다 (예: 자동매매 이전 보유 종목). 6자리 코드를 쉼표/공백으로 구분.
        </p>
        <textarea
          value={blockText}
          onChange={(e) => setBlockText(e.target.value)}
          rows={2}
          inputMode="numeric"
          placeholder="476830, 005930"
          className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        {blocklist.length > 0 && (
          <ul className="mt-2 space-y-1">
            {blocklist.map((b) => (
              <li key={b.stk_cd} className="text-xs text-slate-500">
                <span className="font-medium text-slate-700 dark:text-slate-300">{b.stk_cd}</span>
                {b.reason ? ` — ${b.reason}` : ""}
              </li>
            ))}
          </ul>
        )}
        <button
          onClick={handleBlockSave}
          disabled={blockSaving}
          className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {blockSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          제외 목록 저장
        </button>
      </div>
    </main>
  );
}
