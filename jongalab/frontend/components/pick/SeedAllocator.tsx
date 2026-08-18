"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Wallet } from "lucide-react";
import { StockReport } from "@/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const LS_KEY_SEED = "seedAllocator_seed";
const PREVIEW_COUNT = 8;
// 아래 상수는 전부 `trading/core/seed_allocator.py` 의 **기본값 미러**다.
// 프론트는 trading .env 를 못 읽으므로 기본값으로 고정한다 — 실거래가 .env 로 튜닝돼 있으면
// 그만큼 미리보기와 달라진다(이 미리보기는 '기본 설정에서의 수량'이다).
const TOP_N = 10;
// 종목당 최대 투입 비율(trading `SEED_MAX_NAME_PCT`) — 하한가 1방이 포트를 깨지 않게 묶는 값.
const MAX_NAME_PCT = 0.25;
// 확신도(선정 근거 표) 가중 상한(SEED_CONVICTION_MAX_MULT). 1.0 이면 순수 등가중.
const CONVICTION_MAX_MULT = 3;
// 고가주 첫 1주는 캡을 넘어도 cap×이 배수 이내면 허용(1주가 최소 매매 단위라서).
const FIRST_SHARE_CAP_MULT = 2;

const QUICK_AMOUNTS = [
  { label: "100만", value: 1_000_000 },
  { label: "500만", value: 5_000_000 },
  { label: "1,000만", value: 10_000_000 },
  { label: "5,000만", value: 50_000_000 },
];

/** 선정 근거 표 수 — `trading/core/seed_allocator.conviction_from_signal` 미러.
 *  매칭 규칙 수(중복 태그는 1표) + 점수 top-N 에도 들었으면 1표, 최소 1.
 *  `scoreTopN` 은 그날 선정 종목 수(백엔드 `get_selected_count` 와 같은 값). */
function votes(r: StockReport, scoreTopN: number): number {
  const tags = new Set(
    (r.rule_names ?? "")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
  );
  const n = tags.size + (r.rank_no > 0 && r.rank_no <= scoreTopN ? 1 : 0);
  return Math.max(1, n);
}

/** 표 수를 1 ~ CONVICTION_MAX_MULT 로 클램프한 가중치 (`seed_allocator._weight` 미러). */
function weightOf(r: StockReport, scoreTopN: number): number {
  return Math.min(votes(r, scoreTopN), Math.max(CONVICTION_MAX_MULT, 1));
}

type Allocation = {
  report: StockReport;
  weight: number;
  allocAmount: number;
  shares: number;
  cost: number;
};

export function SeedAllocator({ reports }: { reports: StockReport[] }) {
  const [seed, setSeed] = useState("");
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(LS_KEY_SEED);
    if (stored) setSeed(stored);
  }, []);

  useEffect(() => {
    if (seed) localStorage.setItem(LS_KEY_SEED, seed);
    else localStorage.removeItem(LS_KEY_SEED);
  }, [seed]);

  const seedNum = Number(seed.replace(/[^0-9]/g, "")) || 0;

  const allocations = useMemo<Allocation[]>(() => {
    if (seedNum <= 0 || reports.length === 0) return [];

    // 그날 선정 종목 수 = 확신도의 '점수 top-N' 판정 N (백엔드 get_selected_count 와 같은 값).
    const scoreTopN = reports.length;

    // 유효가(>0) 후보를 **표 수 내림차순 → 점수 내림차순**으로 정렬해 상위 TOP_N 개만
    // 배분 대상으로 삼는다(선정 컷).
    const ranked = reports
      .filter((r) => r.current_price > 0)
      .sort(
        (a, b) =>
          weightOf(b, scoreTopN) - weightOf(a, scoreTopN) ||
          Math.max(b.score, 0) - Math.max(a.score, 0),
      )
      .slice(0, TOP_N);

    // 등가중의 단위는 '종목'이 아니라 **선정 근거 1표**다 — 목표금액 = seed × 표/Σ표.
    // 점수 '크기' tilt 는 쓰지 않는다(점수는 익일 손익을 예측하지 못한다). 표가 전원 1이면 등가중.
    const items = ranked.map((r) => ({
      report: r,
      price: r.current_price,
      w: weightOf(r, scoreTopN),
      shares: 0,
      cost: 0,
    }));
    const n = items.length;
    if (n === 0) return [];
    const wsum = items.reduce((s, it) => s + it.w, 0);

    // 종목당 최대 투입금액 — 시드 대비 비율 캡(이 금액을 넘게는 배분하지 않는다).
    // 확신도가 높아도 이 캡은 그대로다 — 하한가 1방 손실 봉쇄는 캡만이 하는 일이다.
    const cap = seedNum * MAX_NAME_PCT;
    const firstShareCap = cap * FIRST_SHARE_CAP_MULT;

    // 1차: 표 비례 목표금액(캡 적용) → 정수 주식으로 내림 배분
    for (const it of items) {
      const target = Math.min((seedNum * it.w) / wsum, cap);
      it.shares = Math.floor(target / it.price);
      it.cost = it.shares * it.price;
    }

    // 2차: 잔여 현금을 그리디로 재투입 — **확신도 대비** 투입액(cost/w)이 가장 적은 종목부터
    // 한 주씩 추가 매수해 배분을 표 비례로 채운다. 한 주 더 사면 캡을 넘는 종목은 제외하되,
    // 고가주의 **첫 1주**만 cap×FIRST_SHARE_CAP_MULT 이내면 허용한다.
    let leftover = seedNum - items.reduce((s, it) => s + it.cost, 0);
    for (;;) {
      let best: (typeof items)[number] | null = null;
      let bestNorm = Infinity;
      for (const it of items) {
        if (it.price <= 0 || it.price > leftover) continue;
        if (
          it.cost + it.price > cap &&
          !(it.shares === 0 && it.price <= firstShareCap)
        )
          continue;
        const norm = it.cost / it.w;
        if (norm < bestNorm) {
          bestNorm = norm;
          best = it;
        }
      }
      if (!best) break;
      best.shares += 1;
      best.cost += best.price;
      leftover -= best.price;
    }

    return items
      .map((it) => ({
        report: it.report,
        weight: it.w / wsum,
        allocAmount: Math.min((seedNum * it.w) / wsum, cap),
        shares: it.shares,
        cost: it.cost,
      }))
      .sort((a, b) => b.cost - a.cost);
  }, [reports, seedNum]);

  const buyable = allocations.filter((a) => a.shares > 0);
  const totalInvested = buyable.reduce((s, a) => s + a.cost, 0);
  const leftover = Math.max(seedNum - totalInvested, 0);
  const utilizationPct = seedNum > 0 ? (totalInvested / seedNum) * 100 : 0;

  function handleSeedChange(e: ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value.replace(/[^0-9]/g, "");
    setSeed(raw ? Number(raw).toLocaleString("ko-KR") : "");
  }

  function quickSet(value: number) {
    setSeed(value.toLocaleString("ko-KR"));
  }

  const showResults = seedNum > 0 && reports.length > 0;
  const displayList = expanded ? buyable : buyable.slice(0, PREVIEW_COUNT);

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-center gap-1.5 sm:w-auto"
          disabled={reports.length === 0}
        >
          <Wallet className="h-4 w-4" />
          시드 배분 계산
        </Button>
      </DialogTrigger>

      {/* 본문 대신 모달로 — 홈·리포트 화면에서 세로 공간을 크게 먹던 섹션이었다.
          모바일에서 내용이 길어지므로 뷰포트 높이로 잘라 안쪽만 스크롤시킨다. */}
      <DialogContent className="max-h-[85vh] gap-0 overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
            시드 배분
          </DialogTitle>
          <DialogDescription>
            고른 이유가 많은 순으로 {Math.min(reports.length, TOP_N)}개 종목에
            <b> 이유가 많을수록 더 많이</b> 나눠 담으면 몇 주가 되는지 계산해 봤어요(한 종목에
            최대 전체 돈의 {MAX_NAME_PCT * 100}%까지만).
          </DialogDescription>
        </DialogHeader>

      <div className="mt-4">
        <div className="relative">
          <input
            inputMode="numeric"
            value={seed}
            onChange={handleSeedChange}
            placeholder="총 시드 금액"
            className="w-full rounded-2xl bg-slate-50 px-4 py-3 pr-10 text-lg font-extrabold tabular-nums text-slate-900 placeholder:text-base placeholder:font-medium placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 dark:bg-slate-800/60 dark:text-slate-100"
          />
          <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-sm font-bold text-slate-400">
            원
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {QUICK_AMOUNTS.map((q) => (
            <button
              key={q.value}
              type="button"
              onClick={() => quickSet(q.value)}
              className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600 transition-colors hover:bg-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {q.label}
            </button>
          ))}
          {seed && (
            <button
              type="button"
              onClick={() => setSeed("")}
              className="rounded-full px-3 py-1 text-xs font-bold text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              초기화
            </button>
          )}
        </div>
      </div>

      {showResults && (
        <>
          <div className="mt-5 grid grid-cols-3 gap-2 rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/40">
            <Stat label="활용률" value={`${utilizationPct.toFixed(1)}%`} />
            <Stat
              label="매수금"
              value={`${totalInvested.toLocaleString("ko-KR")}원`}
            />
            <Stat
              label="잔여 현금"
              value={`${leftover.toLocaleString("ko-KR")}원`}
            />
          </div>

          <div className="mt-4">
            <p className="text-xs font-extrabold text-slate-600 dark:text-slate-300">
              매수 가능 종목 {buyable.length}개
            </p>
            {buyable.length === 0 ? (
              <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
                금액이 적어서 살 수 있는 종목이 없어요. 금액을 늘리거나 검색으로 종목 수를
                줄여 보세요.
              </p>
            ) : (
              <>
                <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800/60">
                  {displayList.map((a) => (
                    <AllocationRow
                      key={a.report.stock_code}
                      alloc={a}
                      totalInvested={totalInvested}
                    />
                  ))}
                </ul>
                {buyable.length > PREVIEW_COUNT && (
                  <button
                    type="button"
                    onClick={() => setExpanded((v) => !v)}
                    className="mt-3 flex w-full items-center justify-center gap-1 rounded-xl py-2 text-xs font-bold text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-950/30"
                  >
                    {expanded ? (
                      <>
                        접기 <ChevronUp className="h-3.5 w-3.5" />
                      </>
                    ) : (
                      <>
                        {buyable.length - PREVIEW_COUNT}개 더 보기{" "}
                        <ChevronDown className="h-3.5 w-3.5" />
                      </>
                    )}
                  </button>
                )}
              </>
            )}
          </div>
        </>
      )}
      </DialogContent>
    </Dialog>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-0.5 truncate text-sm font-extrabold tabular-nums text-slate-900 dark:text-slate-100">
        {value}
      </p>
    </div>
  );
}

function AllocationRow({
  alloc,
  totalInvested,
}: {
  alloc: Allocation;
  totalInvested: number;
}) {
  const { report: r, shares, cost } = alloc;
  const actualPct = totalInvested > 0 ? (cost / totalInvested) * 100 : 0;
  return (
    <li className="flex items-center justify-between gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-extrabold text-slate-900 dark:text-slate-100">
            {r.stock_name}
          </span>
          <span className="shrink-0 text-[10px] font-bold text-slate-400">
            {r.stock_code}
          </span>
        </div>
        <p className="mt-0.5 text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
          {r.current_price.toLocaleString("ko-KR")}원 · 비중{" "}
          {actualPct.toFixed(1)}%
        </p>
      </div>
      <div className="shrink-0 text-right tabular-nums">
        <p className="text-sm font-extrabold text-indigo-600 dark:text-indigo-400">
          {shares}주
        </p>
        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          {cost.toLocaleString("ko-KR")}원
        </p>
      </div>
    </li>
  );
}
