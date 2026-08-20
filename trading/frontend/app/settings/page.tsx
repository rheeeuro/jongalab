"use client";

import { useState, useEffect } from "react";
import { Save, RotateCcw, Loader2, ArrowLeft, Clock } from "lucide-react";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

// 리스크 한도(주문수/금액/손실/보유수)는 UI 에서 편집하지 않지만, 저장 시 값 유실을
// 막기 위해 GET 응답을 그대로 담아 PUT 으로 되돌려 보낸다(백엔드 DB 값 보존).
interface RiskConfig {
  MAX_ORDERS_PER_DAY: number;
  MAX_NOTIONAL_PER_NAME: number;
  MAX_DAILY_LOSS: number;
  MAX_POSITIONS: number;
  SEED_INIT_MULT: number;
  LEVERAGE_ENABLED: number; // 0/1 — 레버리지 ETF 대체매수 토글
}

interface BlockItem {
  stk_cd: string;
  reason: string | null;
}

interface LeverageItem {
  src_stk_cd: string;
  src_stk_nm: string | null;
  etf_stk_cd: string;
  etf_stk_nm: string | null;
}

export default function RiskSettingsPage() {
  const [config, setConfig] = useState<RiskConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [blocklist, setBlocklist] = useState<BlockItem[]>([]);
  const [blockText, setBlockText] = useState("");
  const [blockSaving, setBlockSaving] = useState(false);

  const [leverage, setLeverage] = useState<LeverageItem[]>([]);
  const [levText, setLevText] = useState("");
  const [levSaving, setLevSaving] = useState(false);

  useEffect(() => {
    fetchConfig();
    fetchBlocklist();
    fetchLeverage();
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

  async function fetchLeverage() {
    try {
      const res = await fetch("/api/leverage-map");
      if (res.ok) {
        const items: LeverageItem[] = await res.json();
        setLeverage(items);
        setLevText(items.map((i) => `${i.src_stk_cd} ${i.etf_stk_cd}`).join("\n"));
      }
    } catch (e) {
      console.error("leverage-map 로드 실패:", e);
    }
  }

  async function handleLeverageSave() {
    if (!config) return;
    setLevSaving(true);
    setMessage(null);
    // 기존 이름 보존: 코드 조합별 이름 맵 (원종목·ETF)
    const srcNames = new Map(leverage.map((i) => [i.src_stk_cd, i.src_stk_nm]));
    const etfNames = new Map(leverage.map((i) => [i.etf_stk_cd, i.etf_stk_nm]));
    // 한 줄당 "원종목코드 ETF코드" (공백/쉼표/화살표 구분). 앞 두 토큰만 사용.
    const items = levText
      .split("\n")
      .map((line) => line.split(/[\s,>→=]+/).map((t) => t.trim()).filter(Boolean))
      .filter((toks) => toks.length >= 2)
      .map(([src_stk_cd, etf_stk_cd]) => ({
        src_stk_cd,
        etf_stk_cd,
        src_stk_nm: srcNames.get(src_stk_cd) ?? null,
        etf_stk_nm: etfNames.get(etf_stk_cd) ?? null,
      }));
    try {
      // 매핑 저장 + 토글(LEVERAGE_ENABLED) 저장을 함께 반영
      const [levRes, cfgRes] = await Promise.all([
        fetch("/api/leverage-map", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items }),
        }),
        fetch("/api/risk-config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config),
        }),
      ]);
      if (levRes.ok && cfgRes.ok) {
        const updated: LeverageItem[] = await levRes.json();
        setLeverage(updated);
        setLevText(updated.map((i) => `${i.src_stk_cd} ${i.etf_stk_cd}`).join("\n"));
        setConfig(await cfgRes.json());
        setMessage({ type: "success", text: "레버리지 설정이 저장되었습니다." });
      } else {
        setMessage({ type: "error", text: "레버리지 설정 저장 실패." });
      }
    } catch {
      setMessage({ type: "error", text: "서버에 연결할 수 없습니다." });
    } finally {
      setLevSaving(false);
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

  function updateSeedMult(value: number) {
    if (!config) return;
    // 5% 단위로 스냅 후 0.0~1.0 클램프 (float 드리프트 방지, 백엔드도 클램프)
    const snapped = Math.round(value / 0.05) * 0.05;
    const clamped = Math.max(0, Math.min(1, Math.round(snapped * 100) / 100));
    setConfig({ ...config, SEED_INIT_MULT: clamped });
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
        <h1 className="mt-2 text-xl font-bold sm:text-2xl">자동매매 설정</h1>
        <p className="mt-1 text-sm text-slate-500">
          다음 집행부터 적용됩니다. 시드 배율은 마감 시각이 있습니다(아래 참고).
        </p>
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
        <div className="flex flex-col gap-2 px-4 py-4 sm:flex-row sm:items-center">
          <label
            htmlFor="seed-init-mult"
            className="text-sm font-medium text-slate-700 dark:text-slate-300 sm:w-48 sm:shrink-0"
          >
            최초 시드 배율
          </label>
          <div className="flex flex-1 items-center gap-3">
            <input
              id="seed-init-mult"
              type="range"
              step={0.05}
              min={0}
              max={1}
              value={config.SEED_INIT_MULT}
              onChange={(e) => updateSeedMult(Number(e.target.value))}
              className="h-2 w-full flex-1 cursor-pointer appearance-none rounded-full bg-slate-200 accent-indigo-600 dark:bg-slate-700"
            />
            <span className="w-16 shrink-0 text-right text-sm font-semibold tabular-nums text-slate-700 dark:text-slate-300">
              {Math.round(config.SEED_INIT_MULT * 100)}%
            </span>
          </div>
        </div>
      </div>
      <p className="mt-2 px-1 text-xs text-slate-500">
        가용현금 기준 최초 시드에 곱하는 배율입니다(5% 단위, 0~100%). 레짐·거시·선물 감액보다 먼저 적용됩니다.
        예: 50% → 시드의 절반만 최초 투입. 100% 는 현행 동작(감액 없음).
      </p>

      {/* 마감 시각 안내 — 배분 시점(창 시작)과 데드라인 재조회 사이에 창이 5분뿐이라
          "언제까지 바꿔야 하나"를 값 바로 아래에서 알려준다. 시각은 signal_executor.VENUES 와 짝. */}
      <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 dark:border-amber-900/50 dark:bg-amber-900/20">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-800 dark:text-amber-300">
          <Clock className="h-3.5 w-3.5 shrink-0" />
          언제까지 바꿔야 하나
        </p>
        <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-amber-800/90 dark:text-amber-200/80">
          <li>
            <b>올릴 때</b> — KRX <b className="tabular-nums">15:10</b> / NXT{" "}
            <b className="tabular-nums">19:40</b> 이전. 그 뒤엔 반영되지 않습니다(축소만 가능).
          </li>
          <li>
            <b>줄일 때</b> — KRX <b className="tabular-nums">15:18</b> / NXT{" "}
            <b className="tabular-nums">19:48</b> 까지. 확정된 수량을 비율만큼 깎습니다.
          </li>
          <li>
            KRX <b className="tabular-nums">15:13~15:15</b> / NXT{" "}
            <b className="tabular-nums">19:43~19:45</b> 는 피하세요 — 수량을 확정하는 중이라 반영
            결과가 갈립니다.
          </li>
        </ul>
        <p className="mt-1.5 text-[11px] leading-relaxed text-amber-700/80 dark:text-amber-200/60">
          줄이는 비율은 <b>배분 시점 대비</b>입니다. 이미 50% 로 배분됐으면 50% 로 다시 저장해도
          변화가 없고, 절반 더 줄이려면 25% 로 내려야 합니다.
        </p>
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

      {/* 레버리지 ETF 대체매수 */}
      <div className="mt-8">
        <h2 className="text-base font-semibold">레버리지 ETF 대체매수</h2>
        <p className="mt-1 mb-3 text-sm text-slate-500">
          켜면 아래 원종목이 신호에 선정될 때 그 종목 대신 매핑된 레버리지 ETF를 매수합니다. 종가랩
          리포트에는 원종목으로, 이 대시보드(매수 예정·보유)에는 ETF로 표시됩니다.
        </p>

        {/* 토글 — 모바일 풀폭 터치 타깃 */}
        <label className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
          <input
            type="checkbox"
            checked={config.LEVERAGE_ENABLED === 1}
            onChange={(e) => setConfig({ ...config, LEVERAGE_ENABLED: e.target.checked ? 1 : 0 })}
            className="h-5 w-5 rounded accent-indigo-600"
          />
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">레버리지 사용</span>
        </label>

        <p className="mt-3 mb-2 text-sm text-slate-500">
          매핑은 한 줄에 하나씩 <span className="font-medium">원종목코드 ETF코드</span> 형식으로
          입력합니다(공백/쉼표 구분).
        </p>
        <textarea
          value={levText}
          onChange={(e) => setLevText(e.target.value)}
          rows={3}
          placeholder={"005930 0193W0\n000660 0193T0"}
          className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 font-mono text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        {leverage.length > 0 && (
          <ul className="mt-2 space-y-1">
            {leverage.map((l) => (
              <li key={l.src_stk_cd} className="text-xs text-slate-500">
                <span className="font-medium text-slate-700 dark:text-slate-300">
                  {l.src_stk_nm ?? l.src_stk_cd}
                </span>{" "}
                → <span className="text-indigo-600 dark:text-indigo-400">{l.etf_stk_nm ?? l.etf_stk_cd}</span>
                <span className="ml-1 text-slate-400">
                  ({l.src_stk_cd} → {l.etf_stk_cd})
                </span>
              </li>
            ))}
          </ul>
        )}
        <button
          onClick={handleLeverageSave}
          disabled={levSaving}
          className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {levSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          레버리지 설정 저장
        </button>
      </div>
    </main>
  );
}
