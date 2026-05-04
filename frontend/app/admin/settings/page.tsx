"use client";

import { useState, useEffect } from "react";
import { Save, RotateCcw, Loader2 } from "lucide-react";
import Link from "next/link";

interface StrategyConfig {
  MIN_TRADING_VALUE: number;
  PREFERRED_TRADING_VALUE: number;
  MIN_MARKET_CAP: number;
  TOP_N_BY_VALUE: number;
  MA_PERIODS: number[];
  MIN_INST_NET_BUY_AMT: number;
  MIN_FRGN_NET_BUY_AMT: number;
  SUPPLY_CHECK_DAYS: number;
  SUPPLY_RECENCY_WEIGHTS: number[];
  SUPPLY_DOUBLE_BUY_BASE_SCORE: number;
  SUPPLY_DOUBLE_BUY_AMOUNT_SCORE: number;
  SUPPLY_INST_BUY_BASE_SCORE: number;
  SUPPLY_INST_BUY_AMOUNT_SCORE: number;
  SUPPLY_FRGN_BUY_BASE_SCORE: number;
  SUPPLY_FRGN_BUY_AMOUNT_SCORE: number;
  SUPPLY_PERSONAL_SELL_SCORE: number;
  SUPPLY_PERSONAL_BUY_PENALTY: number;
  SUPPLY_SMART_PERSONAL_SELL_SCORE: number;
  SUPPLY_SMART_PERSONAL_BUY_PENALTY: number;
  SUPPLY_DOUBLE_STREAK_BONUS: number[];
  SUPPLY_INST_STREAK_BONUS: number[];
  SUPPLY_FRGN_STREAK_BONUS: number[];
  SUPPLY_CUMULATIVE_FRGN_INST_SCORE: number;
  SUPPLY_CUMULATIVE_INST_SCORE: number;
  SUPPLY_CUMULATIVE_SMART_PERSONAL_SELL_SCORE: number;
  SUPPLY_CUMULATIVE_SMART_PERSONAL_BUY_PENALTY: number;
  SUPPLY_RECENT_DOUBLE_BUY_SCORE: number;
  SUPPLY_TODAY_DOUBLE_BUY_SCORE: number;
  SUPPLY_TODAY_INST_BUY_SCORE: number;
  SUPPLY_TODAY_SMART_PERSONAL_SELL_SCORE: number;
  SUPPLY_TODAY_DOUBLE_SELL_PENALTY: number;
  SUPPLY_FOREIGN_SIGNAL_BOOST_MARGIN: number;
  TOP_THEME_COUNT: number;
  THEME_PERIOD_DAYS: string;
  THEME_STOCK_BONUS: number;
  CONTENT_SCORE_MAX: number;
  EXCLUDE_KEYWORDS: string[];
}

const SECTIONS = [
  {
    title: "필터 임계값",
    fields: [
      { key: "MIN_TRADING_VALUE", label: "최소 거래대금", unit: "원", type: "currency" as const },
      { key: "PREFERRED_TRADING_VALUE", label: "우선 거래대금", unit: "원", type: "currency" as const },
      { key: "MIN_MARKET_CAP", label: "최소 시가총액", unit: "원", type: "currency" as const },
      { key: "TOP_N_BY_VALUE", label: "거래대금 상위 N종목", unit: "개", type: "number" as const },
    ],
  },
  {
    title: "이동평균 정배열",
    fields: [
      { key: "MA_PERIODS", label: "이동평균 기간", unit: "일", type: "array" as const },
    ],
  },
  {
    title: "수급 기준",
    fields: [
      { key: "MIN_INST_NET_BUY_AMT", label: "기관 순매수 최소 금액", unit: "원", type: "currency" as const },
      { key: "MIN_FRGN_NET_BUY_AMT", label: "외국인 순매수 최소 금액", unit: "원", type: "currency" as const },
      { key: "SUPPLY_CHECK_DAYS", label: "수급 확인 기간", unit: "일", type: "number" as const },
      { key: "SUPPLY_RECENCY_WEIGHTS", label: "수급 최신 가중치", unit: "과거→최신", type: "array" as const },
    ],
  },
  {
    title: "수급 점수 - 일별",
    fields: [
      { key: "SUPPLY_DOUBLE_BUY_BASE_SCORE", label: "외국인+기관 양매수 기본점", unit: "점", type: "number" as const },
      { key: "SUPPLY_DOUBLE_BUY_AMOUNT_SCORE", label: "외국인+기관 금액점", unit: "점", type: "number" as const },
      { key: "SUPPLY_INST_BUY_BASE_SCORE", label: "기관 순매수 기본점", unit: "점", type: "number" as const },
      { key: "SUPPLY_INST_BUY_AMOUNT_SCORE", label: "기관 순매수 금액점", unit: "점", type: "number" as const },
      { key: "SUPPLY_FRGN_BUY_BASE_SCORE", label: "외국인 순매수 기본점", unit: "점", type: "number" as const },
      { key: "SUPPLY_FRGN_BUY_AMOUNT_SCORE", label: "외국인 순매수 금액점", unit: "점", type: "number" as const },
      { key: "SUPPLY_PERSONAL_SELL_SCORE", label: "개인 순매도 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_PERSONAL_BUY_PENALTY", label: "개인 순매수 감점", unit: "점", type: "number" as const },
      { key: "SUPPLY_SMART_PERSONAL_SELL_SCORE", label: "스마트머니+개인매도 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_SMART_PERSONAL_BUY_PENALTY", label: "스마트머니매도+개인매수 감점", unit: "점", type: "number" as const },
    ],
  },
  {
    title: "수급 점수 - 연속/누적",
    fields: [
      { key: "SUPPLY_DOUBLE_STREAK_BONUS", label: "양매수 연속 보너스", unit: "0~5일", type: "array" as const },
      { key: "SUPPLY_INST_STREAK_BONUS", label: "기관 연속 보너스", unit: "0~5일", type: "array" as const },
      { key: "SUPPLY_FRGN_STREAK_BONUS", label: "외국인 연속 보너스", unit: "0~5일", type: "array" as const },
      { key: "SUPPLY_CUMULATIVE_FRGN_INST_SCORE", label: "누적 외국인+기관 양수 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_CUMULATIVE_INST_SCORE", label: "누적 기관 양수 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_CUMULATIVE_SMART_PERSONAL_SELL_SCORE", label: "누적 스마트머니+개인매도 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_CUMULATIVE_SMART_PERSONAL_BUY_PENALTY", label: "누적 스마트머니매도+개인매수 감점", unit: "점", type: "number" as const },
    ],
  },
  {
    title: "수급 점수 - 최신/보정",
    fields: [
      { key: "SUPPLY_RECENT_DOUBLE_BUY_SCORE", label: "최근 2일 양매수 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_TODAY_DOUBLE_BUY_SCORE", label: "오늘 양매수 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_TODAY_INST_BUY_SCORE", label: "오늘 기관 순매수 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_TODAY_SMART_PERSONAL_SELL_SCORE", label: "오늘 스마트머니+개인매도 가점", unit: "점", type: "number" as const },
      { key: "SUPPLY_TODAY_DOUBLE_SELL_PENALTY", label: "오늘 외국인+기관 동반매도 감점", unit: "점", type: "number" as const },
      { key: "SUPPLY_FOREIGN_SIGNAL_BOOST_MARGIN", label: "외국계 신호 등급 보정폭", unit: "점", type: "number" as const },
    ],
  },
  {
    title: "테마 / 콘텐츠",
    fields: [
      { key: "TOP_THEME_COUNT", label: "상위 테마 수", unit: "개", type: "number" as const },
      { key: "THEME_PERIOD_DAYS", label: "테마 수익률 기간", unit: "일", type: "text" as const },
      { key: "THEME_STOCK_BONUS", label: "테마주 가산점", unit: "점", type: "number" as const },
      { key: "CONTENT_SCORE_MAX", label: "콘텐츠 분석 최대 점수", unit: "점", type: "number" as const },
    ],
  },
  {
    title: "제외 키워드",
    fields: [
      { key: "EXCLUDE_KEYWORDS", label: "종목명에 포함 시 제외", unit: "", type: "keywords" as const },
    ],
  },
];

function formatCurrency(value: number): string {
  if (value >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toLocaleString()}조`;
  if (value >= 100_000_000) return `${(value / 100_000_000).toLocaleString()}억`;
  return value.toLocaleString();
}

export default function SettingsPage() {
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    fetchConfig();
  }, []);

  async function fetchConfig() {
    try {
      const res = await fetch("/api/strategy-config");
      if (res.ok) {
        setConfig(await res.json());
      }
    } catch (e) {
      console.error("설정 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!config) return;
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/strategy-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        const updated = await res.json();
        setConfig(updated);
        setMessage({ type: "success", text: "설정이 저장되었습니다." });
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

  async function handleReset() {
    setLoading(true);
    await fetchConfig();
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const configRecord = config as any as Record<string, unknown>;

  function updateField(key: string, value: unknown) {
    if (!config) return;
    setConfig({ ...config, [key]: value } as StrategyConfig);
  }

  if (loading || !config) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="mx-auto max-w-3xl px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <Link
                href="/admin/tickers"
                className="text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
              >
                티커 관리
              </Link>
              <span className="text-slate-300 dark:text-slate-600">/</span>
              <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                전략 설정
              </span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
              종가베팅 전략 설정
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              다음 종가베팅 실행 시 적용됩니다.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <RotateCcw className="h-4 w-4" />
              <span className="hidden sm:inline">되돌리기</span>
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              저장
            </button>
          </div>
        </div>

        {/* Toast */}
        {message && (
          <div
            className={`rounded-lg px-4 py-3 text-sm font-medium ${
              message.type === "success"
                ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Sections */}
        {SECTIONS.map((section) => (
          <div
            key={section.title}
            className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden"
          >
            <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800">
              <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200">
                {section.title}
              </h2>
            </div>
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {section.fields.map((field) => (
                <div
                  key={field.key}
                  className="flex flex-col sm:flex-row sm:items-center gap-2 px-5 py-4"
                >
                  <div className="sm:w-52 shrink-0">
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                      {field.label}
                    </label>
                  </div>
                  <div className="flex-1">
                    <FieldInput
                      field={field}
                      value={configRecord[field.key]}
                      onChange={(v) => updateField(field.key, v)}
                    />
                  </div>
                  {field.type === "currency" && (
                    <span className="text-xs text-slate-400 sm:w-24 text-right">
                      {formatCurrency(configRecord[field.key] as number)}
                    </span>
                  )}
                  {field.unit && field.type !== "currency" && (
                    <span className="text-xs text-slate-400 sm:w-16 text-right">
                      {field.unit}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: { key: string; type: string };
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const inputClass =
    "w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50";

  switch (field.type) {
    case "currency":
    case "number":
      return (
        <input
          type="number"
          value={value as number}
          onChange={(e) => onChange(Number(e.target.value))}
          className={inputClass}
        />
      );
    case "text":
      return (
        <input
          type="text"
          value={value as string}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
        />
      );
    case "array":
      return (
        <input
          type="text"
          value={(value as number[]).join(", ")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((s) => Number(s.trim()))
                .filter((n) => !isNaN(n))
            )
          }
          placeholder="5, 10, 20"
          className={inputClass}
        />
      );
    case "keywords":
      return (
        <input
          type="text"
          value={(value as string[]).join(", ")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            )
          }
          placeholder="ETF, ETN, KODEX"
          className={inputClass}
        />
      );
    default:
      return null;
  }
}
